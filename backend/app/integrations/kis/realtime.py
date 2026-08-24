"""KIS 국내주식 실시간 체결가 WebSocket client."""

import json
import logging
import time
from typing import Any

import httpx
import websockets

from app.core.config import settings
from app.core.errors import ServiceError
from app.integrations.kis.parser import KIS_REALTIME_PRICE_TR_ID


logger = logging.getLogger(__name__)


class KisRealtimeClient:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client
        self._approval_key: str | None = None
        self._approval_expires_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(settings.kis_app_key and settings.kis_app_secret)

    async def approval_key(self) -> str:
        if self._approval_key and time.monotonic() < self._approval_expires_at:
            return self._approval_key
        if not self.configured:
            raise ServiceError("KIS_NOT_CONFIGURED", "KIS API credential이 설정되지 않았습니다.", 503)

        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=settings.request_timeout_seconds)
        try:
            response = await client.post(
                f"{settings.kis_base_url}/oauth2/Approval",
                json={
                    "grant_type": "client_credentials",
                    "appkey": settings.kis_app_key,
                    "secretkey": settings.kis_app_secret,
                },
                headers={"content-type": "application/json"},
            )
            response.raise_for_status()
            payload = response.json()
            approval_key = payload["approval_key"]
            if not isinstance(approval_key, str) or not approval_key:
                raise ValueError("approval_key is missing")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning("KIS realtime approval request failed error=%s", type(exc).__name__)
            raise ServiceError("KIS_REALTIME_UNAVAILABLE", "KIS 실시간 시세 인증을 완료하지 못했습니다.", 503) from exc
        finally:
            if owns_client:
                await client.aclose()

        self._approval_key = approval_key
        self._approval_expires_at = time.monotonic() + (23 * 60 * 60)
        return approval_key

    async def subscription_message(self, stock_code: str, *, subscribe: bool) -> str:
        return json.dumps({
            "header": {
                "approval_key": await self.approval_key(),
                "custtype": "P",
                "tr_type": "1" if subscribe else "2",
                "content-type": "utf-8",
            },
            "body": {"input": {"tr_id": KIS_REALTIME_PRICE_TR_ID, "tr_key": stock_code}},
        }, ensure_ascii=False)

    def connect(self):
        return websockets.connect(
            settings.kis_websocket_url,
            ping_interval=None,
            close_timeout=5,
            open_timeout=settings.request_timeout_seconds,
        )

    @staticmethod
    def system_message(raw: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def is_pingpong(payload: dict[str, Any]) -> bool:
        header = payload.get("header")
        return isinstance(header, dict) and header.get("tr_id") == "PINGPONG"

    @staticmethod
    def subscription_error(payload: dict[str, Any]) -> str | None:
        body = payload.get("body")
        if not isinstance(body, dict) or str(body.get("rt_cd", "0")) == "0":
            return None
        message = str(body.get("msg1", "KIS realtime subscription failed"))
        if "ALREADY IN SUBSCRIBE" in message.upper():
            return None
        return message

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
