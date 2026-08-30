"""KIS H0STCNT0 실시간 체결가 frame parser."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re

from app.integrations.kis.models import RealtimeQuote


KIS_REALTIME_PRICE_TR_ID = "H0STCNT0"
KIS_REALTIME_PRICE_FIELD_COUNT = 46
KST = timezone(timedelta(hours=9))


def _decimal(value: str, field: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid {field}") from exc
    if not result.is_finite():
        raise ValueError(f"invalid {field}")
    return result


def _integer(value: str, field: str) -> int:
    result = _decimal(value, field)
    if result != result.to_integral_value():
        raise ValueError(f"invalid {field}")
    return int(result)


def _signed(value: Decimal, sign_code: str) -> Decimal:
    if sign_code in {"4", "5"}:
        return -abs(value)
    if sign_code == "3":
        return Decimal("0")
    return abs(value)


def _trade_datetime(business_date: str, trade_time: str, received_at: datetime) -> datetime:
    if not re.fullmatch(r"[0-9]{6}", trade_time):
        raise ValueError("invalid trade time")
    if not re.fullmatch(r"[0-9]{8}", business_date):
        business_date = received_at.astimezone(KST).strftime("%Y%m%d")
    return datetime.strptime(f"{business_date}{trade_time}", "%Y%m%d%H%M%S").replace(tzinfo=KST)


def parse_realtime_price_frame(raw: str, *, received_at: datetime | None = None) -> list[RealtimeQuote]:
    """Pipe/caret 형식의 KIS 체결가 frame을 내부 시세로 변환한다."""
    if not raw or raw[0] not in {"0", "1"}:
        return []
    parts = raw.split("|", 3)
    if len(parts) != 4 or parts[1] != KIS_REALTIME_PRICE_TR_ID:
        return []
    try:
        record_count = int(parts[2])
    except ValueError as exc:
        raise ValueError("invalid realtime record count") from exc
    if record_count <= 0:
        raise ValueError("realtime record count must be positive")

    values = parts[3].split("^")
    required = record_count * KIS_REALTIME_PRICE_FIELD_COUNT
    if len(values) < required:
        raise ValueError("realtime price frame has too few fields")

    received_at = received_at or datetime.now(UTC)
    if received_at.tzinfo is None:
        raise ValueError("received_at must include timezone information")

    quotes: list[RealtimeQuote] = []
    for index in range(record_count):
        row = values[index * KIS_REALTIME_PRICE_FIELD_COUNT:(index + 1) * KIS_REALTIME_PRICE_FIELD_COUNT]
        sign_code = row[3]
        if sign_code not in {"1", "2", "3", "4", "5"}:
            raise ValueError("invalid change sign code")
        change = _signed(_decimal(row[4], "change"), sign_code)
        change_rate = _signed(_decimal(row[5], "change rate"), sign_code)
        quotes.append(RealtimeQuote(
            stock_code=row[0],
            price=_decimal(row[2], "price"),
            change=change,
            change_rate=change_rate,
            trade_volume=_integer(row[12], "trade volume"),
            accumulated_volume=_integer(row[13], "accumulated volume"),
            traded_at=_trade_datetime(row[33], row[1], received_at),
            received_at=received_at.astimezone(UTC),
        ))
    return quotes
