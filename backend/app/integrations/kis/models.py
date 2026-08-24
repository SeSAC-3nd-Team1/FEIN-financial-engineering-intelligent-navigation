"""KIS 외부 응답과 서비스 계층 사이의 실시간 시세 모델."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import re


STOCK_CODE_PATTERN = re.compile(r"^[0-9A-Z]{6,12}$")


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
