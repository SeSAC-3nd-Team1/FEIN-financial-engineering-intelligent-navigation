"""거래 repository의 버전 조회 규칙을 검증한다."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.repositories.trading import TradingRepository


def test_target_weights_only_returns_rows_from_latest_effective_version() -> None:
    removed_from_latest_version = "000660"

    class FakeSession:
        def scalar(self, query):
            self.version_query = query
            return date(2026, 8, 20)

        def scalars(self, query):
            self.rows_query = query
            return [SimpleNamespace(stock_code="005930", target_weight=Decimal("1"))]

    session = FakeSession()
    repository = TradingRepository(session)

    result = repository.target_weights("balanced", date(2026, 8, 25))

    assert result == {"005930": Decimal("1")}
    assert removed_from_latest_version not in result
    assert "effective_from =" in str(session.rows_query)
    assert "effective_from <=" not in str(session.rows_query)
