from __future__ import annotations

import asyncio
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from .kis import KISClient, OrderRequest

KST = timezone(timedelta(hours=9))
MARKET_OPEN = dt_time(9, 0)
MARKET_CLOSE = dt_time(15, 30)
RATE_LIMIT_CODE = "EGW00201"


class RuntimeKISClient(KISClient):
    """KIS client hardened for the paper-trading dashboard PoC.

    All outbound KIS HTTP calls, including token/approval-key issuance, are serialized.
    Short-lived caches collapse React development-mode duplicate requests.
    """

    def __init__(self) -> None:
        super().__init__()
        self._request_lock = asyncio.Lock()
        self._last_request_finished_at = 0.0

        self._account_lock = asyncio.Lock()
        self._account_cache: dict[str, Any] | None = None
        self._account_cache_at = 0.0

        self._chart_locks: dict[str, asyncio.Lock] = {}
        self._chart_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

        self._approval_lock = asyncio.Lock()
        self._approval_key_cache: str | None = None
        self._approval_key_cache_at = 0.0

    @property
    def _request_interval(self) -> float:
        # KIS official samples use a 0.5s paper-trading interval. Keep extra headroom
        # because this dashboard initializes account, chart, and WebSocket together.
        return 0.75 if self.settings.mode == "paper" else 0.10

    async def _throttled_request(
        self,
        method: str,
        url: str,
        *,
        retry_on_rate_limit: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        attempts = 2 if retry_on_rate_limit else 1
        response: httpx.Response | None = None

        for attempt in range(attempts):
            async with self._request_lock:
                elapsed = time.monotonic() - self._last_request_finished_at
                wait = self._request_interval - elapsed
                if wait > 0:
                    await asyncio.sleep(wait)

                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.request(method, url, **kwargs)

                # Measure the next gap from completion, which is more conservative than
                # measuring from request start and prevents overlapping bursts.
                self._last_request_finished_at = time.monotonic()

            if not self._is_rate_limited(response) or attempt == attempts - 1:
                return response

            # A short recovery is appropriate for an interactive dashboard. The KIS
            # backtester uses a much longer cooldown for bulk/looped workloads.
            await asyncio.sleep(2.0)

        assert response is not None
        return response

    @staticmethod
    def _response_body(response: httpx.Response) -> dict[str, Any] | None:
        try:
            body = response.json()
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    @classmethod
    def _is_rate_limited(cls, response: httpx.Response) -> bool:
        body = cls._response_body(response)
        return bool(body and body.get("msg_cd") == RATE_LIMIT_CODE)

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            text = response.text.strip()
            return text or f"KIS HTTP {response.status_code}"

        if isinstance(body, dict):
            message = body.get("msg1") or body.get("message") or body.get("msg")
            code = body.get("msg_cd") or body.get("rt_cd")
            if message and code:
                return f"{message} ({code})"
            if message:
                return str(message)
        return str(body)

    @classmethod
    def _validate_response(cls, response: httpx.Response) -> dict[str, Any]:
        if response.is_error:
            status_code = 429 if cls._is_rate_limited(response) else 502
            raise HTTPException(
                status_code=status_code,
                detail=f"KIS API 오류: {cls._error_detail(response)}",
            )

        try:
            body = response.json()
        except ValueError as error:
            raise HTTPException(
                status_code=502,
                detail="KIS API가 올바른 JSON 응답을 반환하지 않았습니다.",
            ) from error

        if not isinstance(body, dict):
            raise HTTPException(status_code=502, detail="KIS API 응답 형식이 올바르지 않습니다.")

        if body.get("rt_cd") not in {None, "0"}:
            message = body.get("msg1", "KIS API 요청 실패")
            code = body.get("msg_cd") or body.get("rt_cd")
            detail = f"{message} ({code})" if code else str(message)
            status_code = 429 if code == RATE_LIMIT_CODE else 502
            raise HTTPException(status_code=status_code, detail=f"KIS API 오류: {detail}")

        return body

    async def _access_token(self) -> str:
        if self._token and datetime.now() < self._token_expires_at:
            return self._token
        if not self.settings.configured:
            raise HTTPException(503, "KIS_APP_KEY / KIS_APP_SECRET이 설정되지 않았습니다.")

        async with self._token_lock:
            if self._token and datetime.now() < self._token_expires_at:
                return self._token

            payload = {
                "grant_type": "client_credentials",
                "appkey": self.settings.app_key,
                "appsecret": self.settings.app_secret,
            }
            response = await self._throttled_request(
                "POST",
                f"{self.settings.base_url}/oauth2/tokenP",
                json=payload,
                headers={"content-type": "application/json"},
                retry_on_rate_limit=False,
            )
            body = self._validate_response(response)
            token = body.get("access_token")
            if not token:
                raise HTTPException(status_code=502, detail="KIS access_token이 없습니다.")

            self._token = str(token)
            expires_in = int(body.get("expires_in", 86400))
            self._token_expires_at = datetime.now() + timedelta(seconds=max(60, expires_in - 300))
            return self._token

    async def _get(self, path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any]:
        headers = await self._headers(tr_id)
        response = await self._throttled_request(
            "GET",
            f"{self.settings.base_url}{path}",
            params=params,
            headers=headers,
        )
        return self._validate_response(response)

    async def _post(self, path: str, tr_id: str, payload: dict[str, str]) -> dict[str, Any]:
        headers = await self._headers(tr_id)
        response = await self._throttled_request(
            "POST",
            f"{self.settings.base_url}{path}",
            json=payload,
            headers=headers,
        )
        return self._validate_response(response)

    async def _approval_key(self) -> str:
        now = time.monotonic()
        if self._approval_key_cache and now - self._approval_key_cache_at < 300:
            return self._approval_key_cache

        async with self._approval_lock:
            now = time.monotonic()
            if self._approval_key_cache and now - self._approval_key_cache_at < 300:
                return self._approval_key_cache

            payload = {
                "grant_type": "client_credentials",
                "appkey": self.settings.app_key,
                "secretkey": self.settings.app_secret,
            }
            response = await self._throttled_request(
                "POST",
                f"{self.settings.base_url}/oauth2/Approval",
                json=payload,
            )
            body = self._validate_response(response)
            approval_key = body.get("approval_key")
            if not approval_key:
                raise HTTPException(status_code=502, detail="KIS WebSocket approval_key가 없습니다.")

            self._approval_key_cache = str(approval_key)
            self._approval_key_cache_at = time.monotonic()
            return self._approval_key_cache

    async def account(self) -> dict[str, Any]:
        if self.mock_mode:
            return await super().account()

        now = time.monotonic()
        if self._account_cache is not None and now - self._account_cache_at < 2.0:
            return self._account_cache

        async with self._account_lock:
            now = time.monotonic()
            if self._account_cache is not None and now - self._account_cache_at < 2.0:
                return self._account_cache

            account = await super().account()
            self._account_cache = account
            self._account_cache_at = time.monotonic()
            return account

    async def chart(self, symbol: str) -> list[dict[str, Any]]:
        if self.mock_mode:
            return await super().chart(symbol)

        cached = self._chart_cache.get(symbol)
        now = time.monotonic()
        if cached and now - cached[0] < 3.0:
            return cached[1]

        lock = self._chart_locks.setdefault(symbol, asyncio.Lock())
        async with lock:
            cached = self._chart_cache.get(symbol)
            now = time.monotonic()
            if cached and now - cached[0] < 3.0:
                return cached[1]

            now_kst = datetime.now(KST)
            current_time = now_kst.time().replace(tzinfo=None)
            if MARKET_OPEN <= current_time <= MARKET_CLOSE:
                query_time = now_kst.strftime("%H%M%S")
            else:
                query_time = "153000"

            body = await self._get(
                "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
                "FHKST03010200",
                {
                    "FID_ETC_CLS_CODE": "",
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol,
                    "FID_INPUT_HOUR_1": query_time,
                    "FID_PW_DATA_INCU_YN": "Y",
                },
            )

            result: list[dict[str, Any]] = []
            for row in reversed(body.get("output2", []) or []):
                try:
                    result.append(
                        {
                            "time": row.get("stck_cntg_hour", ""),
                            "open": int(float(row.get("stck_oprc", 0) or 0)),
                            "high": int(float(row.get("stck_hgpr", 0) or 0)),
                            "low": int(float(row.get("stck_lwpr", 0) or 0)),
                            "close": int(float(row.get("stck_prpr", 0) or 0)),
                            "volume": int(float(row.get("cntg_vol", 0) or 0)),
                        }
                    )
                except (TypeError, ValueError):
                    continue

            result = result[-120:]
            self._chart_cache[symbol] = (time.monotonic(), result)
            return result


kis_client = RuntimeKISClient()

__all__ = ["OrderRequest", "kis_client"]
