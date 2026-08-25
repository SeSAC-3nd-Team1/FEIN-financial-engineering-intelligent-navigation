"""KIS 외부 응답과 서비스 계층 사이의 실시간 시세 모델."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import re


STOCK_CODE_PATTERN = re.compile(r"^[0-9A-Z]{6,12}$")


@dataclass(frozen=True)
class CurrentQuote:
    stock_code: str
    price: Decimal
    previous_close: Decimal | None
    change_amount: Decimal | None
    change_rate: Decimal | None
    volume: int | None
    as_of: datetime
    source: str = "KIS_REST"

    def __post_init__(self) -> None:
        if not STOCK_CODE_PATTERN.fullmatch(self.stock_code):
            raise ValueError("invalid stock code")
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("price must be a positive finite number")
        for value in (self.previous_close, self.change_amount, self.change_rate):
            if value is not None and not value.is_finite():
                raise ValueError("quote values must be finite")
        if self.previous_close is not None and self.previous_close <= 0:
            raise ValueError("previous close must be positive")
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume must not be negative")
        if self.as_of.tzinfo is None:
            raise ValueError("quote timestamp must include timezone information")


@dataclass(frozen=True)
class MinuteCandle:
    stock_code: str
    started_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    is_closed: bool
    source: str = "KIS_REST"

    def __post_init__(self) -> None:
        if not STOCK_CODE_PATTERN.fullmatch(self.stock_code):
            raise ValueError("invalid stock code")
        if self.started_at.tzinfo is None:
            raise ValueError("candle timestamp must include timezone information")
        prices = (self.open, self.high, self.low, self.close)
        if any(not price.is_finite() or price <= 0 for price in prices):
            raise ValueError("candle prices must be positive finite numbers")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("invalid candle price range")
        if self.volume < 0:
            raise ValueError("volume must not be negative")

    def to_payload(self) -> dict[str, str | int | bool]:
        return {
            "started_at": self.started_at.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": self.volume,
            "is_closed": self.is_closed,
        }

    @classmethod
    def from_payload(cls, stock_code: str, payload: dict[str, object]) -> "MinuteCandle":
        try:
            return cls(
                stock_code=stock_code,
                started_at=datetime.fromisoformat(str(payload["started_at"])),
                open=Decimal(str(payload["open"])),
                high=Decimal(str(payload["high"])),
                low=Decimal(str(payload["low"])),
                close=Decimal(str(payload["close"])),
                volume=int(payload["volume"]),
                is_closed=bool(payload["is_closed"]),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError("invalid minute candle payload") from exc


@dataclass(frozen=True)
class RealtimeQuote:
    stock_code: str
    price: Decimal
    change: Decimal
    change_rate: Decimal
    trade_volume: int
    accumulated_volume: int
    traded_at: datetime
    received_at: datetime
    source: str = "KIS_WS"

    def __post_init__(self) -> None:
        if not STOCK_CODE_PATTERN.fullmatch(self.stock_code):
            raise ValueError("invalid stock code")
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("price must be a positive finite number")
        if not self.change.is_finite() or not self.change_rate.is_finite():
            raise ValueError("change values must be finite")
        if self.trade_volume < 0 or self.accumulated_volume < 0:
            raise ValueError("volume must not be negative")
        if self.traded_at.tzinfo is None or self.received_at.tzinfo is None:
            raise ValueError("quote timestamps must include timezone information")

    def to_payload(self) -> dict[str, str | int | bool]:
        return {
            "type": "price",
            "stock_code": self.stock_code,
            "price": str(self.price),
            "change": str(self.change),
            "change_rate": str(self.change_rate),
            "trade_volume": self.trade_volume,
            "accumulated_volume": self.accumulated_volume,
            "traded_at": self.traded_at.isoformat(),
            "received_at": self.received_at.isoformat(),
            "source": self.source,
            "is_stale": False,
        }

    def to_cache_json(self) -> str:
        return json.dumps(self.to_payload(), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_cache_json(cls, value: str | bytes) -> "RealtimeQuote":
        if isinstance(value, bytes):
            value = value.decode()
        payload = json.loads(value)
        try:
            return cls(
                stock_code=str(payload["stock_code"]),
                price=Decimal(str(payload["price"])),
                change=Decimal(str(payload["change"])),
                change_rate=Decimal(str(payload["change_rate"])),
                trade_volume=int(payload["trade_volume"]),
                accumulated_volume=int(payload["accumulated_volume"]),
                traded_at=datetime.fromisoformat(str(payload["traded_at"])),
                received_at=datetime.fromisoformat(str(payload["received_at"])),
                source=str(payload.get("source", "KIS_WS")),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ValueError("invalid realtime quote cache payload") from exc
