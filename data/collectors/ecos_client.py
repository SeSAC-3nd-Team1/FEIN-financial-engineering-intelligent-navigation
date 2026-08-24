"""한국은행 ECOS 통계 조회와 응답 검증을 담당한다."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import requests

from collectors.ecos_config import EcosSeries

logger = logging.getLogger(__name__)


class EcosError(RuntimeError):
    """ECOS 호출 또는 응답 검증 실패의 공통 예외다."""


class EcosNotConfiguredError(EcosError):
    """ECOS API key가 설정되지 않았을 때 발생한다."""


class EcosApiError(EcosError):
    """ECOS가 성공 대신 오류 코드를 반환했음을 나타낸다."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"ECOS code={code}: {message}")
        self.code = code


class EcosClient:
    """pagination과 제한된 backoff를 적용하는 ECOS 동기 client다."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://ecos.bok.or.kr/api",
        timeout_seconds: float = 10,
        max_attempts: int = 3,
        page_size: int = 1000,
        session: requests.Session | None = None,
    ) -> None:
        if not api_key.strip():
            raise EcosNotConfiguredError("ECOS_API_KEY is not configured")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.page_size = max(1, min(page_size, 1000))
        self.session = session or requests.Session()

    @staticmethod
    def _time(value: date, cycle: str) -> str:
        """ECOS 주기에 맞는 날짜 문자열을 만든다."""

        return value.strftime("%Y%m") if cycle == "M" else value.strftime("%Y%m%d")

    def _request(self, path: str, *, endpoint: str) -> dict[str, Any]:
        """key가 포함된 URL을 오류·로그에 노출하지 않고 JSON object를 반환한다."""

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(
                    f"{self.base_url}/{path}", timeout=self.timeout_seconds,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise requests.HTTPError(
                        f"retryable HTTP {response.status_code}", response=response,
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("ECOS JSON response must be an object")
                result = payload.get("RESULT")
                if isinstance(result, dict):
                    raise EcosApiError(
                        str(result.get("CODE", "UNKNOWN")),
                        str(result.get("MESSAGE", "invalid response")),
                    )
                return payload
            except EcosApiError:
                raise
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
                logger.warning(
                    "ECOS request retry endpoint=%s attempt=%s error=%s",
                    endpoint, attempt, type(exc).__name__,
                )
                time.sleep(min(2 ** (attempt - 1), 8))
        # requests 예외의 URL에는 path parameter인 key가 포함될 수 있어 exception chain도 숨긴다.
        raise EcosError(f"ECOS request failed endpoint={endpoint}") from None

    def observations(
        self, series: EcosSeries, start_date: date, end_date: date,
    ) -> list[dict[str, Any]]:
        """기간 내 시계열 원문 행을 provider 순서 그대로 모두 조회한다."""

        if start_date > end_date:
            raise ValueError("start_date must not be after end_date")
        rows: list[dict[str, Any]] = []
        start_row = 1
        while True:
            end_row = start_row + self.page_size - 1
            path = (
                f"StatisticSearch/{self.api_key}/json/kr/{start_row}/{end_row}/"
                f"{series.stat_code}/{series.cycle}/{self._time(start_date, series.cycle)}/"
                f"{self._time(end_date, series.cycle)}/{series.item_code}"
            )
            payload = self._request(path, endpoint="StatisticSearch")
            result = payload.get("StatisticSearch")
            if not isinstance(result, dict) or not isinstance(result.get("row", []), list):
                raise EcosError("invalid ECOS StatisticSearch response")
            page = result.get("row", [])
            rows.extend(page)
            try:
                total = int(result.get("list_total_count", len(rows)))
            except (TypeError, ValueError) as exc:
                raise EcosError("invalid ECOS list_total_count") from exc
            if not page or len(rows) >= total:
                return rows
            start_row = end_row + 1

    def statistic_items(self, stat_code: str) -> list[dict[str, Any]]:
        """registry 검증용 통계 항목 목록을 pagination하여 조회한다."""

        rows: list[dict[str, Any]] = []
        start_row = 1
        while True:
            end_row = start_row + self.page_size - 1
            payload = self._request(
                f"StatisticItemList/{self.api_key}/json/kr/{start_row}/{end_row}/{stat_code}",
                endpoint="StatisticItemList",
            )
            result = payload.get("StatisticItemList")
            if not isinstance(result, dict) or not isinstance(result.get("row", []), list):
                raise EcosError("invalid ECOS StatisticItemList response")
            page = result.get("row", [])
            rows.extend(page)
            total = int(result.get("list_total_count", len(rows)))
            if not page or len(rows) >= total:
                return rows
            start_row = end_row + 1
