"""Chat Agent correlation, structured telemetry, and request limiting helpers."""

from __future__ import annotations

from collections import Counter
from contextvars import ContextVar
import json
import logging
import threading
import time
from uuid import uuid4

from redis import asyncio as redis_async
from redis.exceptions import RedisError

logger = logging.getLogger("app.chat_agent")
request_id_context: ContextVar[str] = ContextVar("chat_request_id", default="-")
_metrics: Counter[str] = Counter()
_metric_lock = threading.Lock()


class JsonFormatter(logging.Formatter):
    """Emit only explicitly supplied, safe structured fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "logger": record.name,
            "event": record.getMessage(),
            "level": record.levelname,
        }
        for field in (
            "chat_request_id",
            "outcome",
            "elapsed_ms",
            "status_code",
            "tool_name",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
        ):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def new_request_id() -> str:
    return str(uuid4())


def current_request_id() -> str:
    return request_id_context.get()


def increment_metric(name: str, value: int = 1) -> None:
    with _metric_lock:
        _metrics[name] += value


def metric_snapshot() -> dict[str, int]:
    with _metric_lock:
        return dict(_metrics)


def prometheus_metrics() -> str:
    lines = [
        "# HELP chat_agent_metric Chat Agent operational metric.",
        "# TYPE chat_agent_metric counter",
    ]
    for name, value in sorted(metric_snapshot().items()):
        lines.append(f"chat_agent_{name} {value}")
    return "\n".join(lines) + "\n"


def observe_provider_request(
    *,
    outcome: str,
    elapsed_ms: float,
    status_code: int | None = None,
    usage: dict[str, object] | None = None,
) -> None:
    increment_metric("provider_requests_total")
    increment_metric(f"provider_requests_{outcome}_total")
    increment_metric("provider_latency_ms_sum", round(elapsed_ms))
    if usage:
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(field)
            if isinstance(value, int):
                increment_metric(f"chat_{field}_total", value)
    logger.info(
        "chat_provider_request",
        extra={
            "chat_request_id": current_request_id(),
            "outcome": outcome,
            "elapsed_ms": round(elapsed_ms, 2),
            "status_code": status_code,
            "prompt_tokens": usage.get("prompt_tokens") if usage else None,
            "completion_tokens": usage.get("completion_tokens") if usage else None,
            "total_tokens": usage.get("total_tokens") if usage else None,
        },
    )


def observe_tool(*, name: str, outcome: str, elapsed_ms: float) -> None:
    increment_metric("tool_calls_total")
    increment_metric(f"tool_calls_{outcome}_total")
    increment_metric("tool_latency_ms_sum", round(elapsed_ms))
    logger.info(
        "chat_tool_call",
        extra={
            "chat_request_id": current_request_id(),
            "tool_name": name,
            "outcome": outcome,
            "elapsed_ms": round(elapsed_ms, 2),
        },
    )


async def check_rate_limit(
    client: redis_async.Redis,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> bool:
    """Atomically count without blocking the FastAPI event loop."""
    bucket = f"chat:rate:{key}:{int(time.time()) // window_seconds}"
    try:
        count = int(await client.incr(bucket))
        if count == 1:
            await client.expire(bucket, window_seconds + 1)
        return count <= limit
    except (RedisError, RuntimeError):
        logger.warning(
            "chat_rate_limit_unavailable",
            extra={"chat_request_id": current_request_id()},
        )
        increment_metric("chat_rate_limit_unavailable_total")
        return True
