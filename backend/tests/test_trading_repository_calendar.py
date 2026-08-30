from datetime import date, datetime

import pytest

import app.repositories.trading as trading_repository
from app.repositories.trading import TradingRepository


class FakeSession:
    def __init__(self, result):
        self.result = result

    def scalar(self, _query):
        return self.result


class FakeCalendar:
    def __init__(self, session_date: date):
        self.session_date = session_date

    def sessions_in_range(self, _start, _end):
        return [datetime.combine(self.session_date, datetime.min.time())]


@pytest.mark.parametrize(
    ("expected", "db_date"),
    [
        # Calendar quarter-end is a weekend: use the official prior session.
        (date(2026, 6, 29), date(2026, 6, 29)),
        # Calendar quarter-end is a weekday holiday: use the official prior session.
        (date(2026, 6, 29), date(2026, 6, 29)),
    ],
)
def test_quarter_end_uses_exchange_calendar_and_requires_db_session(
    monkeypatch, expected: date, db_date: date
) -> None:
    monkeypatch.setattr(
        trading_repository,
        "get_calendar",
        lambda _name: FakeCalendar(expected),
    )

    result = TradingRepository(FakeSession(db_date)).quarter_end_trade_date(2026, 2)

    assert result == expected


def test_quarter_end_missing_official_session_fails_closed(monkeypatch) -> None:
    official_date = date(2026, 6, 29)
    monkeypatch.setattr(
        trading_repository,
        "get_calendar",
        lambda _name: FakeCalendar(official_date),
    )

    result = TradingRepository(FakeSession(None)).quarter_end_trade_date(2026, 2)

    assert result is None


def test_current_quarter_is_not_inferred_from_database(monkeypatch) -> None:
    monkeypatch.setattr(
        trading_repository,
        "get_calendar",
        lambda _name: pytest.fail("calendar must not be consulted for an open quarter"),
    )

    result = TradingRepository(FakeSession(date(2099, 9, 29))).quarter_end_trade_date(2099, 3)

    assert result is None
