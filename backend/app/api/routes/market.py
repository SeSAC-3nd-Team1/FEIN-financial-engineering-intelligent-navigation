import asyncio
from datetime import UTC, datetime
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, Path, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.api.deps import current_user
from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.kis.hub import realtime_hub
from app.models import User
from app.schemas.api import MinuteCandleListResponse, PriceResponse, RealtimeStatusResponse, RealtimeSubscriptionRequest
from app.services.market import MarketService

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/stocks/{stock_code}/price", response_model=PriceResponse)
def current_price(
    stock_code: str = Path(pattern=r"^[0-9A-Z]{6,12}$"),
    _: User = Depends(current_user),
) -> PriceResponse:
    price, as_of, source = MarketService().get_price(stock_code)
    return PriceResponse(stock_code=stock_code, price=price, as_of=as_of, source=source)


@router.get("/stocks/{stock_code}/candles", response_model=MinuteCandleListResponse)
def minute_candles(
    stock_code: str = Path(pattern=r"^[0-9A-Z]{6,12}$"),
    interval: Literal["1m"] = Query(default="1m"),
    limit: int = Query(default=120, ge=1, le=120),
    _: User = Depends(current_user),
) -> MinuteCandleListResponse:
    candles, as_of, source = MarketService().get_minute_candles(stock_code, limit)
    return MinuteCandleListResponse(
        stock_code=stock_code,
        interval=interval,
        items=[candle.to_payload() for candle in candles],
        source=source,
        as_of=as_of,
    )


@router.get("/realtime/status", response_model=RealtimeStatusResponse)
def realtime_status(_: User = Depends(current_user)) -> dict[str, object]:
    return realtime_hub.status()


def _authenticate_websocket_token(token: str) -> datetime:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )
        user_id = int(payload["sub"])
        expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=UTC)
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise ValueError("invalid token") from exc
    with SessionLocal() as session:
        user = session.get(User, user_id)
        if not user or user.account_status != "ACTIVE":
            raise ValueError("inactive user")
    return expires_at


async def _receive_subscription(websocket: WebSocket, *, require_token: bool) -> RealtimeSubscriptionRequest:
    message = await websocket.receive_json()
    request = RealtimeSubscriptionRequest.model_validate(message)
    if require_token and not request.token:
        raise ValueError("token is required")
    return request


@router.websocket("/realtime")
async def realtime_prices(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = None
    try:
        try:
            initial = await asyncio.wait_for(
                _receive_subscription(websocket, require_token=True),
                timeout=5,
            )
            if initial.action != "subscribe":
                raise ValueError("first action must be subscribe")
            token_expires_at = await run_in_threadpool(_authenticate_websocket_token, initial.token or "")
        except (asyncio.TimeoutError, ValidationError, ValueError):
            await websocket.send_json({"type": "error", "code": "INVALID_SUBSCRIPTION", "message": "인증 토큰과 유효한 구독 종목이 필요합니다."})
            await websocket.close(code=4401)
            return

        try:
            queue = await realtime_hub.add_subscriber(set(initial.stock_codes))
        except Exception as exc:
            code = getattr(exc, "code", "KIS_REALTIME_UNAVAILABLE")
            message = getattr(exc, "message", "KIS 실시간 시세를 사용할 수 없습니다.")
            await websocket.send_json({"type": "error", "code": code, "message": message})
            await websocket.close(code=1011)
            return

        await websocket.send_json({
            "type": "subscribed",
            "stock_codes": sorted(initial.stock_codes),
            "connected": realtime_hub.connected,
        })

        while True:
            if token_expires_at is not None and datetime.now(UTC) >= token_expires_at:
                await websocket.send_json({"type": "error", "code": "INVALID_TOKEN", "message": "인증 토큰이 만료되었습니다."})
                await websocket.close(code=4401)
                return
            quote_task = asyncio.create_task(queue.get())
            receive_task = asyncio.create_task(websocket.receive_json())
            heartbeat_task = asyncio.create_task(asyncio.sleep(15))
            done, pending = await asyncio.wait(
                {quote_task, receive_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            if quote_task in done:
                await websocket.send_json(quote_task.result().to_payload())
                continue
            if heartbeat_task in done:
                await websocket.send_json({
                    "type": "heartbeat",
                    "connected": realtime_hub.connected,
                    "last_received_at": realtime_hub.last_received_at.isoformat() if realtime_hub.last_received_at else None,
                })
                continue

            try:
                request = RealtimeSubscriptionRequest.model_validate(receive_task.result())
                codes = set(request.stock_codes)
                subscribed = await realtime_hub.update_subscriber(
                    queue,
                    add=codes if request.action == "subscribe" else set(),
                    remove=codes if request.action == "unsubscribe" else set(),
                )
                await websocket.send_json({"type": "subscribed", "stock_codes": sorted(subscribed), "connected": realtime_hub.connected})
            except (ValidationError, ValueError):
                await websocket.send_json({"type": "error", "code": "INVALID_SUBSCRIPTION", "message": "구독 요청 형식이 올바르지 않습니다."})
    except WebSocketDisconnect:
        return
    finally:
        if queue is not None:
            await realtime_hub.remove_subscriber(queue)
