"""SeSAC 금융 서비스 FastAPI 진입점."""

from contextlib import asynccontextmanager
import os

from redis import asyncio as redis_async
import redis
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.routes import (
    accounts,
    auth,
    backtest,
    car_goal,
    chat,
    companies,
    information,
    investment,
    investor_profile,
    market,
    model_recommendations,
    orders,
    portfolio,
    strategies,
    strategy_recommendations,
    trading_engine_fix1,
)
from app.core.chat_observability import (
    configure_logging,
    new_request_id,
    prometheus_metrics,
    request_id_context,
)
from app.core.errors import ServiceError
from app.db.session import engine
from app.integrations.kis.hub import realtime_hub


@asynccontextmanager
async def lifespan(application: FastAPI):
    configure_logging()
    application.state.chat_redis = redis_async.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    await realtime_hub.start()
    try:
        yield
    finally:
        await realtime_hub.stop()
        await application.state.chat_redis.aclose()


app = FastAPI(
    title="SeSAC Team 1 Virtual Trading API",
    version="1.0.0",
    description="KIS 현재가를 사용하고 주문/체결/잔액은 내부 PostgreSQL에서 관리하는 가상투자 API",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or new_request_id()
    token = request_id_context.set(request_id)
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    finally:
        request_id_context.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    response = JSONResponse(
        status_code=exc.status_code, content={"code": exc.code, "message": exc.message}
    )
    response.headers["X-Request-ID"] = getattr(request.state, "request_id", "-")
    return response


@app.get("/metrics", tags=["observability"], response_class=PlainTextResponse)
def metrics() -> str:
    return prometheus_metrics()


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/dependencies", tags=["health"], response_model=None)
def dependency_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        cache = redis.from_url(
            os.environ["REDIS_URL"], socket_connect_timeout=3, decode_responses=True
        )
        cache.ping()
    except (KeyError, SQLAlchemyError, redis.RedisError):
        return JSONResponse(
            status_code=503,
            content={
                "code": "DEPENDENCY_UNAVAILABLE",
                "message": "PostgreSQL 또는 Redis를 사용할 수 없습니다.",
            },
        )
    return {"postgres": "ok", "redis": "ok"}


for router in (
    auth.router,
    backtest.router,
    chat.router,
    accounts.router,
    car_goal.router,
    strategies.router,
    market.router,
    orders.router,
    portfolio.router,
    information.router,
    investment.router,
    investor_profile.router,
    strategy_recommendations.router,
    model_recommendations.router,
    companies.router,
    trading_engine_fix1.router,
):
    app.include_router(router, prefix="/api/v1")
