"""시장 데이터 repository의 조회 계약을 검증한다."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.repositories.market_data import MarketDataRepository


def test_kospi_since_filters_sorts_and_deduplicates_trade_dates() -> None:
    rows = [
        SimpleNamespace(id=3, trade_date=date(2026, 8, 22), close_value=Decimal("3040")),
        SimpleNamespace(id=1, trade_date=date(2026, 8, 20), close_value=Decimal("3000")),
        SimpleNamespace(id=2, trade_date=date(2026, 8, 20), close_value=Decimal("3010")),
    ]

    class FakeSession:
        def scalars(self, query):
            self.query = query
            return rows

    session = FakeSession()

    result = MarketDataRepository(session).kospi_since(date(2026, 8, 20))

    assert [(row.trade_date, row.close_value) for row in result] == [
        (date(2026, 8, 20), Decimal("3010")),
        (date(2026, 8, 22), Decimal("3040")),
    ]
    assert "market_indices.trade_date >=" in str(session.query)
    assert "ORDER BY market_indices.trade_date, market_indices.id" in str(session.query)
