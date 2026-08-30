from __future__ import annotations

from copy import deepcopy
from typing import Any

import structlog


_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "client_secret",
    "connection_string",
    "endpoint",
    "password",
    "resource_key",
    "secret",
    "token",
}


def _is_sensitive(key: object) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith("_token")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _REDACTED if _is_sensitive(key) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value


def redact_event(
    logger: Any,
    method_name: str | None,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Return a redacted event without modifying the caller's dictionary."""
    return _redact(deepcopy(event_dict))


def configure_logging() -> None:
    structlog.configure(
        processors=[
            redact_event,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )
