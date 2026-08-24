"""포트폴리오 평가 계산을 검증한다."""

from decimal import Decimal
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.integrations.kis.models import CurrentQuote
from app.services.portfolio import PortfolioService, build_history_points, calculate_rebalancing, calculate_return, calculate_weight


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

        def save_snapshot(self, *_args, **_kwargs):
            self.snapshot_saved = True

    class FakeSession:
        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

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
    assert service.repo.snapshot_saved is True
