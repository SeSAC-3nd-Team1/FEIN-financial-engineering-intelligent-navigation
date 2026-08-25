"""OpenDART HTTP 호출, 상태 검증 및 corpCode ZIP parsing을 담당한다."""

from __future__ import annotations

from dataclasses import dataclass
import io
import logging
import random
import time
from collections.abc import Iterator
from typing import Any, Callable
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


@dataclass(frozen=True)
class OpenDartJsonResponse:
    """HTTP 원문 bytes와 검증을 마친 JSON payload를 함께 보존한다."""

    content: bytes
    payload: dict[str, Any]


def parse_corp_code_zip(content: bytes) -> list[CorpCodeRecord]:
    """OpenDART ZIP에서 CORPCODE.xml을 찾아 안전하게 기업 목록을 parsing한다."""

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = [
                name
                for name in archive.namelist()
                if name.rsplit("/", 1)[-1].lower() == "corpcode.xml"
            ]
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
        records.append(
            CorpCodeRecord(
                corp_code=corp_code,
                corp_name=corp_name,
                corp_name_eng=(item.findtext("corp_eng_name") or "").strip() or None,
                stock_code=stock_code,
                modify_date=(item.findtext("modify_date") or "").strip() or None,
            )
        )
    return records


class OpenDartClient:
    """제한된 재시도와 호출 간격을 적용하는 OpenDART 동기 client다."""

    # 020(요청 제한)과 901(계정/키 상태)은 같은 실행 안의 backoff로 해소되지 않는다.
    RETRYABLE_STATUSES = {"800", "900"}

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://opendart.fss.or.kr/api",
        timeout_seconds: float = 10,
        max_attempts: int = 3,
        min_interval_seconds: float = 0.2,
        session: requests.Session | None = None,
        rate_limiter: Callable[[], None] | None = None,
    ) -> None:
        if not api_key.strip():
            raise OpenDartNotConfiguredError("OPENDART_API_KEY is not configured")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.min_interval_seconds = max(0, min_interval_seconds)
        self.session = session or requests.Session()
        self.rate_limiter = rate_limiter
        self._last_request_at = 0.0

    def _wait_for_rate_limit(self) -> None:
        if self.rate_limiter is not None:
            self.rate_limiter()
            return
        remaining = self.min_interval_seconds - (time.monotonic() - self._last_request_at)
        if remaining > 0:
            time.sleep(remaining)

    def _request(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        expect_json: bool = True,
    ) -> Any:
        safe_params = {**params, "crtfc_key": self.api_key}
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._wait_for_rate_limit()
            try:
                response = self.session.get(
                    f"{self.base_url}/{endpoint}",
                    params=safe_params,
                    timeout=self.timeout_seconds,
                )
                self._last_request_at = time.monotonic()
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(
                        f"retryable HTTP {response.status_code}", response=response
                    )
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
                return OpenDartJsonResponse(content=response.content, payload=payload)
            except OpenDartApiError as exc:
                if not exc.retryable or attempt == self.max_attempts:
                    raise
                last_error = exc
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
            logger.warning(
                "OpenDART request retry endpoint=%s attempt=%s error=%s",
                endpoint,
                attempt,
                type(last_error).__name__,
            )
            response = getattr(last_error, "response", None)
            retry_after = getattr(response, "headers", {}).get("Retry-After") if response else None
            try:
                delay = float(retry_after) if retry_after is not None else None
            except ValueError:
                delay = None
            time.sleep(
                max(0.0, delay)
                if delay is not None
                else min(2 ** (attempt - 1), 8) + random.uniform(0, 0.25)
            )
        raise OpenDartError(f"OpenDART request failed endpoint={endpoint}") from last_error

    def download_corp_codes(self) -> bytes:
        """corpCode XML ZIP 원문을 반환한다."""

        return self._request("corpCode.xml", {}, expect_json=False)

    def company(self, corp_code: str) -> OpenDartJsonResponse:
        """기업개황의 HTTP 원문과 검증된 payload를 반환한다."""

        return self._request("company.json", {"corp_code": corp_code})

    def financials(
        self,
        corp_code: str,
        business_year: str,
        report_code: str,
        fs_div: str = "CFS",
    ) -> OpenDartJsonResponse:
        """단일회사 전체 재무제표의 HTTP 원문과 payload를 반환한다."""

        return self._request(
            "fnlttSinglAcntAll.json",
            {
                "corp_code": corp_code,
                "bsns_year": business_year,
                "reprt_code": report_code,
                "fs_div": fs_div,
            },
        )

    def financials_multi(
        self,
        corp_codes: list[str],
        business_year: str,
        report_code: str,
    ) -> OpenDartJsonResponse:
        """최대 100개 회사의 주요 재무계정을 한 요청으로 조회한다.

        OpenDART 다중회사 주요계정 API의 회사 수 제한을 client 계약에서 먼저 검증해
        잘못된 대량 요청이 provider의 021 오류와 불필요한 quota 사용으로 이어지지 않게 한다.
        """

        normalized = [str(code).strip() for code in corp_codes if str(code).strip()]
        if not normalized:
            raise ValueError("corp_codes must not be empty")
        if len(normalized) > 100:
            raise ValueError("OpenDART financials_multi supports at most 100 companies")
        if any(len(code) != 8 or not code.isdigit() for code in normalized):
            raise ValueError("OpenDART corp_code must be 8 digits")
        return self._request(
            "fnlttMultiAcnt.json",
            {
                "corp_code": ",".join(normalized),
                "bsns_year": business_year,
                "reprt_code": report_code,
            },
        )

    def disclosures(
        self,
        corp_code: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        disclosure_type: str | None = None,
        limit: int = 100,
    ) -> list[OpenDartJsonResponse]:
        """기업별 공시를 요청한 건수 또는 provider 마지막 페이지까지 수집한다.

        각 페이지의 HTTP 원문을 별도 객체로 반환해 Raw Blob lineage와 pagination 경계를
        잃지 않는다. 마지막 페이지가 limit을 초과해도 원문은 자르지 않고, DB 적재 단계가
        최종 건수만 제한한다.
        """

        if limit < 1:
            raise ValueError("limit must be at least 1")
        params: dict[str, Any] = {
            "corp_code": corp_code,
            "page_count": min(limit, 100),
        }
        if start_date:
            params["bgn_de"] = start_date
        if end_date:
            params["end_de"] = end_date
        if disclosure_type:
            params["pblntf_ty"] = disclosure_type
        pages: list[OpenDartJsonResponse] = []
        received = 0
        page_no = 1
        while True:
            response = self._request("list.json", {**params, "page_no": page_no})
            items = response.payload.get("list", [])
            if not isinstance(items, list):
                raise OpenDartError("OpenDART disclosure list must be an array")
            pages.append(response)
            received += len(items)
            try:
                total_page = max(1, int(response.payload.get("total_page", 1)))
            except (TypeError, ValueError) as exc:
                raise OpenDartError("invalid OpenDART disclosure total_page") from exc
            if received >= limit or page_no >= total_page or not items:
                break
            page_no += 1
        return pages

    def disclosures_market(
        self,
        *,
        start_date: str,
        end_date: str,
        corp_cls: str,
    ) -> list[OpenDartJsonResponse]:
        """기존 호출부 호환을 위해 streaming 공시 iterator를 list로 반환한다."""

        return list(
            self.iter_disclosures_market(
                start_date=start_date,
                end_date=end_date,
                corp_cls=corp_cls,
            )
        )

    def iter_disclosures_market(
        self,
        *,
        start_date: str,
        end_date: str,
        corp_cls: str,
        start_page: int = 1,
    ) -> Iterator[OpenDartJsonResponse]:
        """한 시장의 기간 공시를 페이지마다 즉시 yield한다.

        corp_code 없이 공시검색 API를 사용하면 provider가 검색기간을 최대 3개월로 제한하므로
        호출자는 그보다 짧은 구간을 넘겨야 한다. 전체 응답을 list에 누적하지 않아 수백 개
        페이지도 한 페이지 크기의 메모리만 사용하며, 중단 후 저장된 page부터 재개할 수 있다.
        """

        if corp_cls not in {"Y", "K"}:
            raise ValueError("corp_cls must be Y(KOSPI) or K(KOSDAQ)")
        if len(start_date) != 8 or not start_date.isdigit():
            raise ValueError("start_date must be YYYYMMDD")
        if len(end_date) != 8 or not end_date.isdigit():
            raise ValueError("end_date must be YYYYMMDD")
        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        if start_page < 1:
            raise ValueError("start_page must be at least 1")

        params: dict[str, Any] = {
            "bgn_de": start_date,
            "end_de": end_date,
            "corp_cls": corp_cls,
            "page_count": 100,
            "sort": "date",
            "sort_mth": "asc",
        }
        page_no = start_page
        while True:
            response = self._request("list.json", {**params, "page_no": page_no})
            items = response.payload.get("list", [])
            if not isinstance(items, list):
                raise OpenDartError("OpenDART disclosure list must be an array")
            try:
                total_page = max(1, int(response.payload.get("total_page", 1)))
            except (TypeError, ValueError) as exc:
                raise OpenDartError("invalid OpenDART disclosure total_page") from exc
            yield response
            if page_no >= total_page or not items:
                break
            page_no += 1
