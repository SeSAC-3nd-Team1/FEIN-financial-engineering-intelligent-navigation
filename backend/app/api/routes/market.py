import asyncio
from datetime import UTC, datetime
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, Path, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import current_user
from app.core.config import settings
from app.db.session import SessionLocal, get_session
from app.integrations.kis.hub import realtime_hub
from app.models import User
from app.repositories.market_data import MarketDataRepository
from app.schemas.api import MinuteCandleListResponse, PriceResponse, RealtimeStatusResponse, RealtimeSubscriptionRequest, StockChartResponse, StockSummaryResponse
from app.services.market import MarketService, StockMarketService

router = APIRouter(prefix="/market", tags=["market"])


class WebSocketTokenError(Exception):
    """초기 WebSocket 인증 토큰이 유효하지 않다."""


class WebSocketAuthUnavailable(Exception):
    """WebSocket 사용자 인증 의존성을 사용할 수 없다."""


@router.get("/stocks/{stock_code}/price", response_model=PriceResponse)
def current_price(
    stock_code: str = Path(pattern=r"^[0-9A-Z]{6,12}$"),
    _: User = Depends(current_user),
) -> PriceResponse:
    quote = MarketService().get_quote(stock_code)
    return PriceResponse(
        stock_code=stock_code, price=quote.price, previous_close=quote.previous_close,
        change_amount=quote.change_amount, change_rate=quote.change_rate, volume=quote.volume,
        as_of=quote.as_of, source=quote.source,
    )


def get_stock_market_service(session: Session = Depends(get_session)) -> StockMarketService:
    return StockMarketService(MarketDataRepository(session))


@router.get("/stocks/{stock_code}/summary", response_model=StockSummaryResponse)
def stock_summary(
    stock_code: str = Path(pattern=r"^\d{6}$"),
    _: User = Depends(current_user),
    service: StockMarketService = Depends(get_stock_market_service),
) -> StockSummaryResponse:
    return service.summary(stock_code)


@router.get("/stocks/{stock_code}/chart", response_model=StockChartResponse)
def stock_chart(
    stock_code: str = Path(pattern=r"^\d{6}$"),
    period: Literal["1D", "1W", "3M", "6M", "1Y", "5Y"] = Query(default="3M"),
    _: User = Depends(current_user),
    service: StockMarketService = Depends(get_stock_market_service),
) -> StockChartResponse:
    return service.chart(stock_code, period)


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
        raise WebSocketTokenError("invalid token") from exc
    try:
        with SessionLocal() as session:
            user = session.get(User, user_id)
            if not user or user.account_status != "ACTIVE":
                raise WebSocketTokenError("inactive user")
    except SQLAlchemyError as exc:
        raise WebSocketAuthUnavailable("authentication dependency unavailable") from exc
    return expires_at


async def _receive_subscription(websocket: WebSocket, *, require_token: bool) -> RealtimeSubscriptionRequest:
    message = await websocket.receive_json()
    request = RealtimeSubscriptionRequest.model_validate(message)
    if require_token and not request.token:
        raise WebSocketTokenError("token is required")
    return request


async def _reject_websocket(
    websocket: WebSocket,
    *,
    error_code: str,
    message: str,
    close_code: int,
) -> None:
    await websocket.send_json({"type": "error", "code": error_code, "message": message})
    await websocket.close(code=close_code)


@router.websocket("/realtime")
async def realtime_prices(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = None
    quote_task: asyncio.Task | None = None
    receive_task: asyncio.Task | None = None
    heartbeat_task: asyncio.Task | None = None
    try:
        try:
            initial = await asyncio.wait_for(_receive_subscription(websocket, require_token=True), timeout=5)
        except asyncio.TimeoutError:
            await _reject_websocket(
                websocket,
                error_code="SUBSCRIPTION_TIMEOUT",
                message="초기 구독 요청 시간이 초과되었습니다.",
                close_code=4408,
            )
            return
        except WebSocketTokenError:
            await _reject_websocket(
                websocket,
                error_code="INVALID_TOKEN",
                message="유효한 인증 토큰이 필요합니다.",
                close_code=4401,
            )
            return
        except (ValidationError, ValueError):
            await _reject_websocket(
                websocket,
                error_code="INVALID_SUBSCRIPTION",
                message="구독 요청 형식이 올바르지 않습니다.",
                close_code=4400,
            )
            return

        if initial.action != "subscribe":
            await _reject_websocket(
                websocket,
                error_code="INVALID_SUBSCRIPTION",
                message="최초 요청은 종목 구독이어야 합니다.",
                close_code=4400,
            )
            return

        try:
            token_expires_at = await run_in_threadpool(_authenticate_websocket_token, initial.token or "")
        except WebSocketTokenError:
            await _reject_websocket(
                websocket,
                error_code="INVALID_TOKEN",
                message="유효한 인증 토큰이 필요합니다.",
                close_code=4401,
            )
            return
        except WebSocketAuthUnavailable:
            await _reject_websocket(
                websocket,
                error_code="AUTH_SERVICE_UNAVAILABLE",
                message="인증 서비스를 사용할 수 없습니다.",
                close_code=1011,
            )
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

        quote_task = asyncio.create_task(queue.get())
        receive_task = asyncio.create_task(websocket.receive_json())
        heartbeat_task = asyncio.create_task(asyncio.sleep(15))
        while True:
            if token_expires_at is not None and datetime.now(UTC) >= token_expires_at:
                await websocket.send_json({"type": "error", "code": "INVALID_TOKEN", "message": "인증 토큰이 만료되었습니다."})
                await websocket.close(code=4401)
                return
            done, _ = await asyncio.wait(
                {quote_task, receive_task, heartbeat_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if quote_task in done:
                await websocket.send_json(quote_task.result().to_payload())
                quote_task = asyncio.create_task(queue.get())
            if heartbeat_task in done:
                await websocket.send_json({
                    "type": "heartbeat",
                    "connected": realtime_hub.connected,
                    "last_received_at": realtime_hub.last_received_at.isoformat() if realtime_hub.last_received_at else None,
                })
                heartbeat_task = asyncio.create_task(asyncio.sleep(15))

            if receive_task in done:
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
                receive_task = asyncio.create_task(websocket.receive_json())
    except WebSocketDisconnect:
        return
    finally:
        tasks = [task for task in (quote_task, receive_task, heartbeat_task) if task is not None]
        for task in tasks:
            if not task.done():
                task.cancel()
        if queue is not None:
            await realtime_hub.remove_subscriber(queue)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
