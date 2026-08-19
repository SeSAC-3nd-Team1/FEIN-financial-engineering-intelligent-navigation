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


class RuntimeKISClient(KISClient):
    """KIS client with paper-API throttling, KST chart queries, and readable errors."""

    def __init__(self) -> None:
        super().__init__()
        self._rest_lock = asyncio.Lock()
        self._last_rest_call = 0.0

    async def _rate_limit(self) -> None:
        # Paper trading is deliberately throttled more conservatively than real trading.
        interval = 0.55 if self.settings.mode == "paper" else 0.10
        async with self._rest_lock:
            now = time.monotonic()
            wait = interval - (now - self._last_rest_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_rest_call = time.monotonic()

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
            raise HTTPException(
                status_code=502,
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
            raise HTTPException(status_code=502, detail=f"KIS API 오류: {detail}")

        return body

    async def _get(self, path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any]:
        await self._rate_limit()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.settings.base_url}{path}",
                params=params,
                headers=await self._headers(tr_id),
            )
        return self._validate_response(response)

    async def _post(self, path: str, tr_id: str, payload: dict[str, str]) -> dict[str, Any]:
        await self._rate_limit()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.settings.base_url}{path}",
                json=payload,
                headers=await self._headers(tr_id),
            )
        return self._validate_response(response)

    async def _approval_key(self) -> str:
        await self._rate_limit()
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.settings.app_key,
            "secretkey": self.settings.app_secret,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.settings.base_url}/oauth2/Approval",
                json=payload,
            )
        body = self._validate_response(response)
        approval_key = body.get("approval_key")
        if not approval_key:
            raise HTTPException(status_code=502, detail="KIS WebSocket approval_key가 없습니다.")
        return str(approval_key)

    async def chart(self, symbol: str) -> list[dict[str, Any]]:
        if self.mock_mode:
            return await super().chart(symbol)

        now_kst = datetime.now(KST)
        current_time = now_kst.time().replace(tzinfo=None)
        if MARKET_OPEN <= current_time <= MARKET_CLOSE:
            query_time = now_kst.strftime("%H%M%S")
        else:
            # Outside regular trading hours, request up to the regular-session close.
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
        return result[-120:]


kis_client = RuntimeKISClient()

__all__ = ["OrderRequest", "kis_client"]
