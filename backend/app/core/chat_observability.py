"""Chat Agent correlation, structured telemetry, and request limiting helpers."""

from __future__ import annotations

from collections import Counter
from contextvars import ContextVar
import logging
import time
from uuid import uuid4

import redis

logger = logging.getLogger("app.chat_agent")
request_id_context: ContextVar[str] = ContextVar("chat_request_id", default="-")
_metrics: Counter[str] = Counter()


def new_request_id() -> str:
    return str(uuid4())


def current_request_id() -> str:
    return request_id_context.get()


def increment_metric(name: str, value: int = 1) -> None:
    _metrics[name] += value


def metric_snapshot() -> dict[str, int]:
    return dict(_metrics)


def observe_provider_request(
    *,
    outcome: str,
    elapsed_ms: float,
    status_code: int | None = None,
    usage: dict[str, object] | None = None,
) -> None:
    increment_metric("chat_provider_requests_total")
    increment_metric(f"chat_provider_requests_{outcome}_total")
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
    increment_metric("chat_tool_calls_total")
    logger.info(
        "chat_tool_call",
        extra={
            "chat_request_id": current_request_id(),
            "tool_name": name,
            "outcome": outcome,
            "elapsed_ms": round(elapsed_ms, 2),
        },
    )


def check_rate_limit(
    client: redis.Redis,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> bool:
    """Atomically count a request; returns false after the configured window limit."""
    bucket = f"chat:rate:{key}:{int(time.time()) // window_seconds}"
    try:
        count = int(client.incr(bucket))
        if count == 1:
            client.expire(bucket, window_seconds + 1)
        return count <= limit
    except redis.RedisError:
        logger.exception(
            "chat_rate_limit_unavailable",
            extra={"chat_request_id": current_request_id()},
        )
        increment_metric("chat_rate_limit_unavailable_total")
        return True
