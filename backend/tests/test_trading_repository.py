"""거래 repository의 버전 조회 규칙을 검증한다."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.models import Execution
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


def test_execution_history_uses_stable_keyset_and_stock_name_join() -> None:
    account_id = uuid4()
    executed_at = datetime(2026, 8, 25, 1, 2, tzinfo=UTC)
    execution = Execution(
        id=10,
        order_id=uuid4(),
        account_id=account_id,
        stock_code="005930",
        side="BUY",
        quantity=Decimal("1.5"),
        execution_price=Decimal("70000"),
        executed_at=executed_at,
    )

    class FakeSession:
        def execute(self, query):
            self.query = query
            return [(execution, "삼성전자")]

    session = FakeSession()
    repository = TradingRepository(session)

    result = repository.execution_history(
        account_id,
        limit=21,
        before_executed_at=executed_at,
        before_id=10,
    )

    sql = str(session.query)
    assert result[0].execution is execution
    assert result[0].stock_name == "삼성전자"
    assert "LEFT OUTER JOIN market_stocks" in sql
    assert "executions.executed_at <" in sql
    assert "executions.id <" in sql
    assert "executions.executed_at DESC, executions.id DESC" in sql
    assert "LIMIT" in sql
