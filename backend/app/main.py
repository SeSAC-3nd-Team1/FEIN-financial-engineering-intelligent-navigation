import asyncio
import os

import psycopg
import redis
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from .kis_runtime import OrderRequest, kis_client

app = FastAPI(title="SeSAC Team 1 API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/dependencies")
def dependency_health() -> dict[str, str]:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as connection:
            connection.execute("SELECT 1")
        cache = redis.from_url(os.environ["REDIS_URL"], socket_connect_timeout=3, decode_responses=True)
        cache.ping()
    except (KeyError, psycopg.Error, redis.RedisError) as error:
        raise HTTPException(status_code=503, detail="Dependency unavailable") from error
    return {"postgres": "ok", "redis": "ok"}


@app.get("/kis/status")
async def kis_status() -> dict:
    return kis_client.status()


@app.get("/kis/price/{symbol}")
async def kis_price(symbol: str) -> dict:
    return await kis_client.price(symbol)


@app.get("/kis/chart/{symbol}")
async def kis_chart(symbol: str) -> list[dict]:
    return await kis_client.chart(symbol)


@app.get("/kis/account")
async def kis_account() -> dict:
    return await kis_client.account()


@app.post("/kis/order")
async def kis_order(order: OrderRequest) -> dict:
    return await kis_client.order(order)


@app.websocket("/ws/kis/{symbol}")
async def kis_stream(websocket: WebSocket, symbol: str) -> None:
    await websocket.accept()
    stream = kis_client.stream(symbol)
    tick_task: asyncio.Task | None = None
    disconnect_task: asyncio.Task | None = None

    try:
        while True:
            tick_task = asyncio.create_task(anext(stream))
            disconnect_task = asyncio.create_task(websocket.receive())

            done, pending = await asyncio.wait(
                {tick_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            if disconnect_task in done:
                message = disconnect_task.result()
                if message.get("type") == "websocket.disconnect":
                    return

            if tick_task in done:
                try:
                    tick = tick_task.result()
                except StopAsyncIteration:
                    return
                await websocket.send_json(tick)

    except (WebSocketDisconnect, asyncio.CancelledError):
        return
    except Exception as error:
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.send_json({"type": "error", "message": str(error)})
                await websocket.close(code=1011)
            except WebSocketDisconnect:
                pass
    finally:
        for task in (tick_task, disconnect_task):
            if task is not None and not task.done():
                task.cancel()
        await stream.aclose()
