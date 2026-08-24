"""OpenDART HTTP 호출, 상태 검증 및 corpCode ZIP parsing을 담당한다."""

from __future__ import annotations

from dataclasses import dataclass
import io
import logging
import time
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

import requests

logger = logging.getLogger(__name__)


class OpenDartError(RuntimeError):
    """OpenDART 호출 또는 응답 검증 실패의 공통 예외다."""


class OpenDartNotConfiguredError(OpenDartError):
    """API key가 설정되지 않았을 때 발생한다."""


class OpenDartApiError(OpenDartError):
    """OpenDART가 성공이 아닌 status를 반환했음을 나타낸다."""

    def __init__(self, status: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(f"OpenDART status={status}: {message}")
        self.status = status
        self.retryable = retryable


@dataclass(frozen=True)
class CorpCodeRecord:
    """corpCode.xml의 기업 행을 leading zero 손실 없이 표현한다."""

    corp_code: str
    corp_name: str
    corp_name_eng: str | None
    stock_code: str | None
    modify_date: str | None


def parse_corp_code_zip(content: bytes) -> list[CorpCodeRecord]:
    """OpenDART ZIP에서 CORPCODE.xml을 찾아 안전하게 기업 목록을 parsing한다."""

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = [name for name in archive.namelist() if name.rsplit("/", 1)[-1].lower() == "corpcode.xml"]
            if len(names) != 1:
                raise OpenDartError("corpCode ZIP must contain exactly one CORPCODE.xml")
            xml_bytes = archive.read(names[0])
        root = ET.fromstring(xml_bytes)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise OpenDartError("invalid OpenDART corpCode ZIP/XML") from exc

    records: list[CorpCodeRecord] = []
    for item in root.findall("list"):
        corp_code = (item.findtext("corp_code") or "").strip()
        corp_name = (item.findtext("corp_name") or "").strip()
        if not corp_code or not corp_name:
            continue
        # 숫자 변환을 하지 않아 '005930' 같은 거래소 코드의 선행 0을 보존한다.
        stock_code = (item.findtext("stock_code") or "").strip() or None
        records.append(CorpCodeRecord(
            corp_code=corp_code,
            corp_name=corp_name,
            corp_name_eng=(item.findtext("corp_eng_name") or "").strip() or None,
            stock_code=stock_code,
            modify_date=(item.findtext("modify_date") or "").strip() or None,
        ))
    return records


class OpenDartClient:
    """제한된 재시도와 호출 간격을 적용하는 OpenDART 동기 client다."""

    RETRYABLE_STATUSES = {"020", "800", "900", "901"}

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://opendart.fss.or.kr/api",
        timeout_seconds: float = 10,
        max_attempts: int = 3,
        min_interval_seconds: float = 0.2,
        session: requests.Session | None = None,
    ) -> None:
        if not api_key.strip():
            raise OpenDartNotConfiguredError("OPENDART_API_KEY is not configured")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.min_interval_seconds = max(0, min_interval_seconds)
        self.session = session or requests.Session()
        self._last_request_at = 0.0

    def _wait_for_rate_limit(self) -> None:
        remaining = self.min_interval_seconds - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def _request(self, endpoint: str, params: dict[str, Any], *, expect_json: bool = True) -> Any:
        safe_params = {**params, "crtfc_key": self.api_key}
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._wait_for_rate_limit()
            try:
                response = self.session.get(
                    f"{self.base_url}/{endpoint}", params=safe_params, timeout=self.timeout_seconds
                )
                self._last_request_at = time.monotonic()
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(f"retryable HTTP {response.status_code}", response=response)
                response.raise_for_status()
                if not expect_json:
                    return response.content
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("OpenDART JSON response must be an object")
                status = str(payload.get("status", ""))
                if status not in {"000", "013"}:
                    raise OpenDartApiError(
                        status or "UNKNOWN",
                        str(payload.get("message", "invalid response")),
                        retryable=status in self.RETRYABLE_STATUSES,
                    )
                return payload
            except OpenDartApiError as exc:
                if not exc.retryable or attempt == self.max_attempts:
                    raise
                last_error = exc
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
            logger.warning("OpenDART request retry endpoint=%s attempt=%s error=%s", endpoint, attempt, type(last_error).__name__)
            time.sleep(min(2 ** (attempt - 1), 8))
        raise OpenDartError(f"OpenDART request failed endpoint={endpoint}") from last_error

    def download_corp_codes(self) -> bytes:
        """corpCode XML ZIP 원문을 반환한다."""

        return self._request("corpCode.xml", {}, expect_json=False)

    def company(self, corp_code: str) -> dict[str, Any]:
        """기업개황 응답을 반환한다."""

        return self._request("company.json", {"corp_code": corp_code})

    def financials(self, corp_code: str, business_year: str, report_code: str, fs_div: str = "CFS") -> dict[str, Any]:
        """단일회사 전체 재무제표 응답을 반환한다."""

        return self._request("fnlttSinglAcntAll.json", {
            "corp_code": corp_code, "bsns_year": business_year, "reprt_code": report_code, "fs_div": fs_div,
        })

    def disclosures(
        self,
        corp_code: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        disclosure_type: str | None = None,
        page_count: int = 100,
    ) -> dict[str, Any]:
        """기업별 공시검색 첫 페이지를 반환한다."""

        params: dict[str, Any] = {"corp_code": corp_code, "page_count": min(max(page_count, 1), 100)}
        if start_date:
            params["bgn_de"] = start_date
        if end_date:
            params["end_de"] = end_date
        if disclosure_type:
            params["pblntf_ty"] = disclosure_type
        return self._request("list.json", params)
