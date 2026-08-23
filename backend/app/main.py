"""SeSAC 금융 서비스 FastAPI 진입점."""

import os

import psycopg
import redis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import accounts, auth, market, orders, portfolio, strategies
from app.core.errors import ServiceError

app = FastAPI(
    title="SeSAC Team 1 Virtual Trading API",
    version="1.0.0",
    description="KIS 현재가를 사용하고 주문/체결/잔액은 내부 PostgreSQL에서 관리하는 가상투자 API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ServiceError)
async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/dependencies", tags=["health"], response_model=None)
def dependency_health():
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as connection:
            connection.execute("SELECT 1")
        cache = redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=3, decode_responses=True)
        cache.ping()
    except (KeyError, psycopg.Error, redis.RedisError):
        return JSONResponse(status_code=503, content={"code": "DEPENDENCY_UNAVAILABLE", "message": "PostgreSQL 또는 Redis를 사용할 수 없습니다."})
    return {"postgres": "ok", "redis": "ok"}


for router in (auth.router, accounts.router, strategies.router, market.router, orders.router, portfolio.router):
    app.include_router(router, prefix="/api/v1")
