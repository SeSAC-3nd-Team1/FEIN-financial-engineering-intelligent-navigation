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


def test_completed_onboarding_lookup_requires_user_mode_and_completed_status() -> None:
    onboarding = SimpleNamespace(account_id=uuid4(), status="COMPLETED")

    class FakeSession:
        def scalar(self, query):
            self.query = query
            return onboarding

    session = FakeSession()
    repository = TradingRepository(session)

    result = repository.completed_onboarding_for_user_mode(7, "AUTO")

    sql = str(session.query)
    assert result is onboarding
    assert "investment_onboardings.user_id" in sql
    assert "investment_onboardings.operation_mode" in sql
    assert "investment_onboardings.status" in sql


def test_external_cash_flows_excludes_buy_and_sell_ledger_rows() -> None:
    class FakeSession:
        def scalars(self, query):
            self.query = query
            return []

    session = FakeSession()
    repository = TradingRepository(session)

    repository.external_cash_flows(
        uuid4(),
        datetime(2026, 8, 20, tzinfo=UTC),
        datetime(2026, 8, 26, tzinfo=UTC),
    )

    sql = str(session.query)
    assert "cash_ledger.transaction_type IN" in sql
    assert "cash_ledger.created_at >=" in sql
    assert "cash_ledger.created_at <" in sql
    assert "cash_ledger.created_at, cash_ledger.id" in sql
