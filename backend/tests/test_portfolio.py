"""포트폴리오 평가 계산을 검증한다."""

from decimal import Decimal
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.integrations.kis.models import CurrentQuote
from app.services.portfolio import PortfolioService, build_history_points, calculate_rebalancing, calculate_return, calculate_weight, validate_target_weights


def test_return_rate() -> None:
    assert calculate_return(Decimal("25000"), Decimal("100000")) == Decimal("25.00")


def test_zero_purchase_return_is_zero() -> None:
    assert calculate_return(Decimal("100"), Decimal("0")) == Decimal("0")


def test_position_weight_uses_total_assets_including_cash() -> None:
    assert calculate_weight(Decimal("300000"), Decimal("1000000")) == Decimal("30.00")


def test_rebalancing_uses_only_explicit_target_weights() -> None:
    proposals = calculate_rebalancing(
        Decimal("1000000"),
        {"005930": Decimal("18.00")},
        {"005930": Decimal("0.14"), "000660": Decimal("0.10")},
        {"005930": "삼성전자", "000660": "SK하이닉스"},
    )

    assert [(item.stock_code, item.action, item.recommended_amount) for item in proposals] == [
        ("000660", "BUY", Decimal("100000.00")),
        ("005930", "SELL", Decimal("40000.00")),
    ]


def test_rebalancing_is_unavailable_without_targets() -> None:
    assert calculate_rebalancing(
        Decimal("1000000"), {"005930": Decimal("18")}, {}, {"005930": "삼성전자"}
    ) == []


def test_history_aligns_snapshot_with_latest_kospi_close() -> None:
    snapshots = [
        SimpleNamespace(snapshot_date=date(2026, 8, 20), total_assets=Decimal("1000000")),
        SimpleNamespace(snapshot_date=date(2026, 8, 22), total_assets=Decimal("1050000")),
    ]
    indices = [
        SimpleNamespace(trade_date=date(2026, 8, 20), close_value=Decimal("3000")),
        SimpleNamespace(trade_date=date(2026, 8, 21), close_value=Decimal("3030")),
    ]

    points = build_history_points(snapshots, indices)

    assert points[0].portfolio_return_rate == Decimal("0.00")
    assert points[1].portfolio_return_rate == Decimal("5.00")
    assert points[1].benchmark_return_rate == Decimal("1.00")


def test_history_uses_first_snapshot_date_as_benchmark_base_and_deduplicates_dates() -> None:
    snapshots = [
        SimpleNamespace(snapshot_date=date(2026, 8, 20), total_assets=Decimal("1000000")),
        SimpleNamespace(snapshot_date=date(2026, 8, 22), total_assets=Decimal("1050000")),
    ]
    indices = [
        SimpleNamespace(trade_date=date(2026, 8, 13), close_value=Decimal("2900")),
        SimpleNamespace(trade_date=date(2026, 8, 20), close_value=Decimal("3000")),
        SimpleNamespace(trade_date=date(2026, 8, 20), close_value=Decimal("3010")),
        SimpleNamespace(trade_date=date(2026, 8, 21), close_value=Decimal("3040")),
    ]

    points = build_history_points(snapshots, indices)

    assert points[0].benchmark_return_rate == Decimal("0.00")
    assert points[1].benchmark_return_rate == Decimal("1.00")


def test_invalid_target_weight_sum_is_rejected() -> None:
    with pytest.raises(ServiceError) as error:
        validate_target_weights({"005930": Decimal("0.5"), "000660": Decimal("0.4")})

    assert error.value.code == "INVALID_STRATEGY_TARGET_WEIGHTS"


def test_evaluate_combines_real_metadata_quote_and_daily_contribution() -> None:
    account_id = uuid4()
    account = SimpleNamespace(
        id=account_id,
        cash_balance=Decimal("300000"),
        selected_strategy_id=None,
    )
    position = SimpleNamespace(
        stock_code="005930",
        quantity=10,
        average_price=Decimal("70000"),
        realized_profit=Decimal("0"),
    )

    class FakeRepo:
        def owned_account(self, *_args):
            return account

        def positions(self, *_args):
            return [position]

    class FakeSession:
        def commit(self):
            raise AssertionError("GET evaluation must not commit")

        def rollback(self):
            raise AssertionError("GET evaluation must not roll back")

    service = PortfolioService.__new__(PortfolioService)
    service.session = FakeSession()
    service.repo = FakeRepo()
    service.market_repo = SimpleNamespace(stock=lambda _code: SimpleNamespace(
        stock_name="삼성전자", sector="반도체"
    ))
    service.market = SimpleNamespace(get_quote=lambda _code: CurrentQuote(
        stock_code="005930",
        price=Decimal("71000"),
        previous_close=Decimal("70500"),
        change_amount=Decimal("500"),
        change_rate=Decimal("0.71"),
        volume=100,
        as_of=datetime(2026, 8, 25, tzinfo=UTC),
        source="KIS",
    ))

    result = service.evaluate(1, account_id)

    assert result.total_assets == Decimal("1010000.00")
    assert result.positions[0].stock_name == "삼성전자"
    assert result.positions[0].weight == Decimal("70.30")
    assert result.today_profit == Decimal("5000.00")
    assert result.top_contributor and result.top_contributor.stock_code == "005930"


def test_evaluate_does_not_report_partial_today_profit_as_complete() -> None:
    account_id = uuid4()
    account = SimpleNamespace(id=account_id, cash_balance=Decimal("0"), selected_strategy_id=None)
    positions = [
        SimpleNamespace(stock_code="005930", quantity=1, average_price=Decimal("70000"), realized_profit=Decimal("0")),
        SimpleNamespace(stock_code="000660", quantity=1, average_price=Decimal("120000"), realized_profit=Decimal("0")),
    ]
    quotes = {
        "005930": CurrentQuote("005930", Decimal("71000"), Decimal("70500"), Decimal("500"), Decimal("0.71"), 100, datetime.now(UTC)),
        "000660": CurrentQuote("000660", Decimal("121000"), None, None, None, 100, datetime.now(UTC)),
    }

    service = PortfolioService.__new__(PortfolioService)
    service.session = SimpleNamespace()
    service.repo = SimpleNamespace(owned_account=lambda *_args: account, positions=lambda *_args: positions)
    service.market_repo = SimpleNamespace(stock=lambda _code: None)
    service.market = SimpleNamespace(get_quote=lambda code: quotes[code])

    result = service.evaluate(1, account_id)

    assert result.today_profit is None
    assert result.contributions[0].amount == Decimal("500.00")
    assert result.contributions[0].share_rate is None


def test_daily_snapshot_task_writes_and_commits_once() -> None:
    account = SimpleNamespace(id=uuid4())
    response = SimpleNamespace(
        cash_balance=Decimal("100"), total_purchase_amount=Decimal("200"),
        total_evaluation_amount=Decimal("220"), total_assets=Decimal("320"),
        unrealized_profit=Decimal("20"), realized_profit=Decimal("10"),
        return_rate=Decimal("10"),
    )

    class FakeRepo:
        def active_accounts(self):
            return [account]

        def save_snapshot(self, *args, **kwargs):
            self.saved = (args, kwargs)

    class FakeSession:
        def commit(self):
            self.committed = True

        def rollback(self):
            raise AssertionError("successful task must not roll back")

    service = PortfolioService.__new__(PortfolioService)
    service.session = FakeSession()
    service.repo = FakeRepo()
    service.market_repo = SimpleNamespace(has_kospi_close=lambda _date: True)
    service._evaluate_account = lambda _account, **_kwargs: response

    captured = service.capture_daily_snapshots(date(2026, 8, 25))

    assert captured == 1
    assert service.repo.saved[0] == (account.id, date(2026, 8, 25))
    assert service.session.committed is True


def test_daily_snapshot_quote_uses_krx_close_and_previous_trading_day() -> None:
    prices = [
        SimpleNamespace(
            trade_date=date(2026, 8, 25), close_price=Decimal("71000"),
            change_amount=Decimal("500"), change_rate=Decimal("0.71"),
            volume=1000, source="KRX",
        ),
        SimpleNamespace(trade_date=date(2026, 8, 24), close_price=Decimal("70500")),
    ]
    service = PortfolioService.__new__(PortfolioService)
    service.market_repo = SimpleNamespace(closing_prices=lambda *_args: prices)

    quote = service._closing_quote("005930", date(2026, 8, 25))

    assert quote.price == Decimal("71000")
    assert quote.previous_close == Decimal("70500")
    assert quote.source == "KRX"
    assert quote.as_of.isoformat() == "2026-08-25T15:30:00+09:00"
