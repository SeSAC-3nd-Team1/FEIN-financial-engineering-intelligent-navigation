"""KRX OPEN API 인증과 응답 검증을 담당한다."""

from __future__ import annotations

import os
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from collectors.krx_config import KrxOperation


class KrxApiError(RuntimeError):
    """KRX가 HTTP 오류 또는 해석할 수 없는 payload를 반환했다."""


def get_krx_auth_key() -> str:
    """환경변수에서 KRX 인증키를 읽되 오류에 실제 값을 포함하지 않는다."""

    key = os.getenv("KRX_AUTH_KEY", "").strip()
    if not key:
        raise RuntimeError("KRX_AUTH_KEY is required")
    return key


class KrxClient:
    """승인된 KRX 일별 API만 호출하는 read-only client다."""

    def __init__(
        self,
        auth_key: str | None = None,
        *,
        base_url: str = "https://data-dbg.krx.co.kr/svc/apis",
        timeout_seconds: float = 10,
    ) -> None:
        self.auth_key = auth_key or get_krx_auth_key()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            backoff_jitter=0.25,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def fetch(self, operation: KrxOperation, base_date: str) -> list[dict[str, Any]]:
        """YYYYMMDD 기준 일자 자료를 원문 field 이름 그대로 반환한다."""

        if len(base_date) != 8 or not base_date.isdigit():
            raise ValueError("base_date must use YYYYMMDD format")
        try:
            response = self.session.get(
                f"{self.base_url}/{operation.path}",
                headers={"AUTH_KEY": self.auth_key},
                params={"basDd": base_date},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise KrxApiError(
                f"KRX request failed operation={operation.name} error={type(exc).__name__}"
            ) from None
        if not isinstance(payload, dict):
            raise KrxApiError(f"KRX response root is invalid operation={operation.name}")
        rows = payload.get("OutBlock_1")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise KrxApiError(f"KRX response rows are invalid operation={operation.name}")
        return rows
