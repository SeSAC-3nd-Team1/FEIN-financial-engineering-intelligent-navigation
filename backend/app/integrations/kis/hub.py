"""하나의 KIS upstream 연결을 API client들에게 fan-out하는 실시간 시세 hub."""

import asyncio
from collections import defaultdict
from contextlib import suppress
from datetime import UTC, datetime
import logging

import redis
import redis.asyncio as async_redis
import websockets

from app.core.config import settings
from app.core.errors import ServiceError
from app.integrations.kis.models import RealtimeQuote
from app.integrations.kis.parser import parse_realtime_price_frame
from app.integrations.kis.realtime import KisRealtimeClient


logger = logging.getLogger(__name__)
REALTIME_PRICE_KEY_PREFIX = "market:realtime:price:"


class KisRealtimeHub:
    def __init__(self, client: KisRealtimeClient | None = None, cache=None) -> None:
        self.client = client or KisRealtimeClient()
        self.cache = cache or async_redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
        )
        self._owns_cache = cache is None
        self._subscribers: dict[str, set[asyncio.Queue[RealtimeQuote]]] = defaultdict(set)
        self._subscriber_symbols: dict[asyncio.Queue[RealtimeQuote], set[str]] = {}
        self._lock = asyncio.Lock()
        self._commands: asyncio.Queue[tuple[bool, str]] = asyncio.Queue()
        self._wake = asyncio.Event()
        self._runner: asyncio.Task[None] | None = None
        self._stopping = False
        self.connected = False
        self.last_error: str | None = None
        self.last_received_at: datetime | None = None

    @property
    def configured(self) -> bool:
        return self.client.configured

    async def start(self) -> None:
        self._stopping = False

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._runner is not None:
            self._runner.cancel()
            with suppress(asyncio.CancelledError):
                await self._runner
        self._runner = None
        self.connected = False
        await self.client.aclose()
        if self._owns_cache:
            await self.cache.aclose()

    async def add_subscriber(self, stock_codes: set[str]) -> asyncio.Queue[RealtimeQuote]:
        if not self.configured:
            raise ServiceError("KIS_NOT_CONFIGURED", "KIS API credential이 설정되지 않았습니다.", 503)
        queue: asyncio.Queue[RealtimeQuote] = asyncio.Queue(maxsize=settings.realtime_client_queue_size)
        async with self._lock:
            self._subscriber_symbols[queue] = set()
            await self._update_locked(queue, add=stock_codes, remove=set())
            if self._runner is None or self._runner.done():
                self._runner = asyncio.create_task(self._run(), name="kis-realtime-hub")
        self._wake.set()
        return queue

    async def update_subscriber(
        self,
        queue: asyncio.Queue[RealtimeQuote],
        *,
        add: set[str],
        remove: set[str],
    ) -> set[str]:
        async with self._lock:
            if queue not in self._subscriber_symbols:
                raise ValueError("unknown realtime subscriber")
            resulting = (self._subscriber_symbols[queue] | add) - remove
            if len(resulting) > settings.realtime_max_symbols_per_client:
                raise ValueError("too many realtime symbols")
            await self._update_locked(queue, add=add, remove=remove)
            subscribed = set(self._subscriber_symbols[queue])
        if add:
            self._wake.set()
        return subscribed

    async def remove_subscriber(self, queue: asyncio.Queue[RealtimeQuote]) -> None:
        async with self._lock:
            symbols = self._subscriber_symbols.get(queue, set()).copy()
            await self._update_locked(queue, add=set(), remove=symbols)
            self._subscriber_symbols.pop(queue, None)

    async def _update_locked(
        self,
        queue: asyncio.Queue[RealtimeQuote],
        *,
        add: set[str],
        remove: set[str],
    ) -> None:
        current = self._subscriber_symbols[queue]
        for stock_code in add - current:
            first = not self._subscribers[stock_code]
            self._subscribers[stock_code].add(queue)
            current.add(stock_code)
            if first:
                await self._commands.put((True, stock_code))
        for stock_code in remove & current:
            subscribers = self._subscribers[stock_code]
            subscribers.discard(queue)
            current.discard(stock_code)
            if not subscribers:
                self._subscribers.pop(stock_code, None)
                await self._commands.put((False, stock_code))

    async def _active_symbols_and_clear_commands(self) -> list[str]:
        async with self._lock:
            symbols = sorted(self._subscribers)
            while not self._commands.empty():
                with suppress(asyncio.QueueEmpty):
                    self._commands.get_nowait()
            return symbols

    async def _run(self) -> None:
        backoff = 1
        while not self._stopping:
            symbols = await self._active_symbols_and_clear_commands()
            if not symbols:
                self._wake.clear()
                await self._wake.wait()
                continue
            try:
                async with self.client.connect() as socket:
                    for stock_code in symbols:
                        await socket.send(await self.client.subscription_message(stock_code, subscribe=True))
                    self.connected = True
                    self.last_error = None
                    backoff = 1
                    await self._consume(socket)
            except asyncio.CancelledError:
                raise
            except (OSError, websockets.exceptions.WebSocketException, ServiceError) as exc:
                self.last_error = type(exc).__name__
                logger.warning("KIS realtime connection failed error=%s", type(exc).__name__)
            except Exception as exc:  # provider protocol errors must not stop future reconnects
                self.last_error = type(exc).__name__
                logger.warning("KIS realtime loop failed error=%s", type(exc).__name__)
            finally:
                self.connected = False
            if not self._stopping and self._subscribers:
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, settings.realtime_reconnect_max_seconds)

    async def _consume(self, socket) -> None:
        while not self._stopping:
            receive_task = asyncio.create_task(socket.recv())
            command_task = asyncio.create_task(self._commands.get())
            done, pending = await asyncio.wait(
                {receive_task, command_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

            if command_task in done:
                subscribe, stock_code = command_task.result()
                await socket.send(await self.client.subscription_message(stock_code, subscribe=subscribe))
                if not self._subscribers:
                    return
                continue

            raw = receive_task.result()
            if not isinstance(raw, str) or not raw:
                continue
            if raw[0] in {"0", "1"}:
                try:
                    quotes = parse_realtime_price_frame(raw)
                except ValueError as exc:
                    logger.warning("KIS realtime frame rejected error=%s", type(exc).__name__)
                    continue
                for quote in quotes:
                    await self._publish(quote)
                continue

            payload = self.client.system_message(raw)
            if payload is None:
                continue
            if self.client.is_pingpong(payload):
                await socket.send(raw)
                continue
            error = self.client.subscription_error(payload)
            if error:
                raise ServiceError("KIS_REALTIME_SUBSCRIPTION_FAILED", "KIS 실시간 종목 구독에 실패했습니다.", 503)

    async def _publish(self, quote: RealtimeQuote) -> None:
        self.last_received_at = quote.received_at
        key = f"{REALTIME_PRICE_KEY_PREFIX}{quote.stock_code}"
        try:
            await self.cache.setex(key, settings.realtime_price_cache_ttl_seconds, quote.to_cache_json())
        except redis.RedisError:
            logger.warning("Redis realtime price write failed stock_code=%s", quote.stock_code)

        for queue in tuple(self._subscribers.get(quote.stock_code, ())):
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with suppress(asyncio.QueueFull):
                queue.put_nowait(quote)

    def status(self) -> dict[str, object]:
        return {
            "configured": self.configured,
            "connected": self.connected,
            "subscribed_symbols": len(self._subscribers),
            "downstream_clients": len(self._subscriber_symbols),
            "last_received_at": self.last_received_at,
            "last_error": self.last_error,
        }


realtime_hub = KisRealtimeHub()
