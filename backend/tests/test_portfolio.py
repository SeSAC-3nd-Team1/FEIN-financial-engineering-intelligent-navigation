"""포트폴리오 평가 계산과 AI 리밸런싱 응답을 검증한다."""

import asyncio
from decimal import Decimal
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.integrations.kis.models import CurrentQuote
from app.integrations.ai.rebalancing_client import AIRebalancingResult
from app.schemas.api import PortfolioResponse, PositionResponse
from app.services import portfolio as portfolio_service_module
from app.services.portfolio import (
    PortfolioService,
    build_allocations,
    build_history_points,
    calculate_rebalancing,
    calculate_return,
    calculate_weight,
    sort_positions,
    validate_target_weights,
)


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

    assert [
        (item.stock_code, item.action, item.recommended_amount) for item in proposals
    ] == [
        ("000660", "BUY", Decimal("100000.00")),
        ("005930", "SELL", Decimal("40000.00")),
    ]


def test_rebalancing_is_unavailable_without_targets() -> None:
    assert (
        calculate_rebalancing(
            Decimal("1000000"), {"005930": Decimal("18")}, {}, {"005930": "삼성전자"}
        )
        == []
    )


def test_history_aligns_snapshot_with_latest_kospi_close() -> None:
    snapshots = [
        SimpleNamespace(
            snapshot_date=date(2026, 8, 20), total_assets=Decimal("1000000")
        ),
        SimpleNamespace(
            snapshot_date=date(2026, 8, 22), total_assets=Decimal("1050000")
        ),
    ]
    indices = [
        SimpleNamespace(trade_date=date(2026, 8, 20), close_value=Decimal("3000")),
        SimpleNamespace(trade_date=date(2026, 8, 21), close_value=Decimal("3030")),
    ]

    points = build_history_points(snapshots, indices)

    assert points[0].portfolio_return_rate == Decimal("0.00")
    assert points[1].portfolio_return_rate == Decimal("5.00")
    assert points[1].benchmark_return_rate == Decimal("1.00")


def test_history_uses_first_snapshot_date_as_benchmark_base_and_deduplicates_dates() -> (
    None
):
    snapshots = [
        SimpleNamespace(
            snapshot_date=date(2026, 8, 20), total_assets=Decimal("1000000")
        ),
        SimpleNamespace(
            snapshot_date=date(2026, 8, 22), total_assets=Decimal("1050000")
        ),
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
        validate_target_weights({"005930": Decimal("0.7"), "000660": Decimal("0.4")})

    assert error.value.code == "INVALID_STRATEGY_TARGET_WEIGHTS"


def test_target_weights_allow_explicit_cash_buffer() -> None:
    validate_target_weights(
        {"005930": Decimal("0.475"), "000660": Decimal("0.475")},
        allow_cash_buffer=True,
    )


def test_cash_buffer_requires_exactly_five_percent_cash() -> None:
    with pytest.raises(ServiceError) as error:
        validate_target_weights(
            {"005930": Decimal("0.40"), "000660": Decimal("0.40")},
            allow_cash_buffer=True,
        )

    assert error.value.code == "INVALID_STRATEGY_TARGET_WEIGHTS"


def portfolio_position(
    stock_code: str,
    stock_name: str,
    *,
    weight: str,
    purchase_amount: str,
    return_rate: str,
) -> PositionResponse:
    return PositionResponse(
        stock_code=stock_code,
        stock_name=stock_name,
        sector=None,
        quantity=Decimal("1"),
        average_price=Decimal(purchase_amount),
        current_price=Decimal(purchase_amount),
        previous_close=None,
        change_rate=None,
        purchase_amount=Decimal(purchase_amount),
        evaluation_amount=Decimal(purchase_amount),
        unrealized_profit=Decimal("0"),
        return_rate=Decimal(return_rate),
        realized_profit=Decimal("0"),
        weight=Decimal(weight),
        today_profit=None,
        price_source="KRX",
        price_as_of=datetime(2026, 8, 25, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("sort_by", "order", "expected"),
    [
        ("stock_name", "asc", ["000660", "005930"]),
        ("weight", "desc", ["005930", "000660"]),
        ("purchase_amount", "asc", ["000660", "005930"]),
        ("return_rate", "desc", ["000660", "005930"]),
    ],
)
def test_home_positions_support_allowed_sort_columns(sort_by, order, expected) -> None:
    positions = [
        portfolio_position(
            "005930", "삼성전자", weight="60", purchase_amount="70000", return_rate="1"
        ),
        portfolio_position(
            "000660",
            "SK하이닉스",
            weight="30",
            purchase_amount="50000",
            return_rate="2",
        ),
    ]

    result = sort_positions(positions, sort_by, order)

    assert [item.stock_code for item in result] == expected


def test_home_allocations_include_cash_as_an_explicit_slice() -> None:
    position = portfolio_position(
        "005930", "삼성전자", weight="70", purchase_amount="700000", return_rate="0"
    )
    portfolio = PortfolioResponse(
        account_id=uuid4(),
        cash_balance=Decimal("300000"),
        total_purchase_amount=Decimal("700000"),
        total_evaluation_amount=Decimal("700000"),
        total_assets=Decimal("1000000"),
        unrealized_profit=Decimal("0"),
        realized_profit=Decimal("0"),
        return_rate=Decimal("0"),
        today_profit=None,
        top_contributor=None,
        contributions=[],
        strategy_targets_available=False,
        rebalancing_proposals=[],
        positions=[position],
    )

    result = build_allocations(portfolio)

    assert [(item.type, item.stock_code, item.weight) for item in result] == [
        ("STOCK", "005930", Decimal("70")),
        ("CASH", None, Decimal("30.00")),
    ]


def test_home_combines_account_evaluation_history_and_sorting_without_second_owner_lookup() -> (
    None
):
    account_id = uuid4()
    account = SimpleNamespace(
        id=account_id,
        account_name="나의 반자동 계좌",
        operation_mode="SEMI_AUTO",
        status="ACTIVE",
        selected_strategy_id="low",
    )
    positions = [
        portfolio_position(
            "005930", "삼성전자", weight="60", purchase_amount="600000", return_rate="1"
        ),
        portfolio_position(
            "000660",
            "SK하이닉스",
            weight="30",
            purchase_amount="300000",
            return_rate="2",
        ),
    ]
    portfolio = PortfolioResponse(
        account_id=account_id,
        cash_balance=Decimal("100000"),
        total_purchase_amount=Decimal("900000"),
        total_evaluation_amount=Decimal("900000"),
        total_assets=Decimal("1000000"),
        unrealized_profit=Decimal("0"),
        realized_profit=Decimal("0"),
        return_rate=Decimal("0"),
        today_profit=None,
        top_contributor=None,
        contributions=[],
        strategy_targets_available=False,
        rebalancing_proposals=[],
        positions=positions,
    )

    class FakeRepo:
        def __init__(self):
            self.owner_lookups = 0

        def owned_account(self, *_args):
            self.owner_lookups += 1
            return account

        def snapshots_since(self, *_args):
            return [
                SimpleNamespace(
                    snapshot_date=date(2026, 8, 25), total_assets=Decimal("1000000")
                )
            ]

    service = PortfolioService.__new__(PortfolioService)
    service.repo = FakeRepo()
    service.market_repo = SimpleNamespace(kospi_since=lambda *_args: [])
    service._evaluate_account = lambda _account: portfolio

    service.rebalancing_client = None
    service.rebalancing_model_version = "rebalancing-v1"

    result = asyncio.run(service.home(7, account_id, "3M", "return_rate", "desc"))

    assert service.repo.owner_lookups == 1
    assert result.account.operation_mode == "SEMI_AUTO"
    assert result.summary.total_assets == Decimal("1000000")
    assert result.trend.items[0].total_assets == Decimal("1000000")
    assert [item.stock_code for item in result.positions] == ["000660", "005930"]
    assert result.allocations[-1].type == "CASH"
    assert result.valuation_as_of == datetime(2026, 8, 25, tzinfo=UTC)
    assert result.rebalancing_insight.status == "UNAVAILABLE"


def test_home_offloads_sync_work_before_awaiting_ai_rebalancing(monkeypatch) -> None:
    account_id = uuid4()
    account = SimpleNamespace(
        id=account_id,
        account_name="나의 반자동 계좌",
        operation_mode="SEMI_AUTO",
        status="ACTIVE",
        selected_strategy_id="low",
    )
    candidate = calculate_rebalancing(
        Decimal("1000000"),
        {"005930": Decimal("20.00")},
        {"005930": Decimal("0.15")},
        {"005930": "삼성전자"},
    )[0]
    portfolio = PortfolioResponse(
        account_id=account_id,
        cash_balance=Decimal("800000"),
        total_purchase_amount=Decimal("200000"),
        total_evaluation_amount=Decimal("200000"),
        total_assets=Decimal("1000000"),
        unrealized_profit=Decimal("0"),
        realized_profit=Decimal("0"),
        return_rate=Decimal("0"),
        today_profit=None,
        top_contributor=None,
        contributions=[],
        strategy_targets_available=True,
        rebalancing_proposals=[candidate],
        positions=[],
    )

    events = []

    async def fake_run_in_threadpool(func, *args, **kwargs):
        events.append("sync")
        return func(*args, **kwargs)

    class FakeClient:
        async def analyze(self, context):
            events.append("ai")
            self.context = context
            return AIRebalancingResult(
                summary="목표 비중과 5%p 차이가 발생했습니다.",
                proposals=[
                    {
                        "stock_code": "005930",
                        "priority": 1,
                        "current_weight": "20.00",
                        "target_weight": "15.00",
                        "weight_diff": "5.00",
                        "action": "SELL",
                        "recommended_amount": "50000.00",
                        "reason": "전략 목표보다 보유 비중이 높습니다.",
                        "why_now": "현재 목표 비중과의 차이가 5%p로 확대됐습니다.",
                    }
                ],
            )

    class FakeRepo:
        def owned_account(self, *_args):
            return account

        def snapshots_since(self, *_args):
            return []

    client = FakeClient()
    service = PortfolioService.__new__(PortfolioService)
    service.repo = FakeRepo()
    service.market_repo = SimpleNamespace(kospi_since=lambda *_args: [])
    service.rebalancing_client = client
    service.rebalancing_model_version = "rebalancing-v1"
    service._evaluate_account = lambda _account: portfolio
    monkeypatch.setattr(
        portfolio_service_module, "run_in_threadpool", fake_run_in_threadpool
    )

    result = asyncio.run(service.home(7, account_id, "3M", "weight", "desc"))

    assert events == ["sync", "ai"]
    assert result.rebalancing_insight.status == "AVAILABLE"
    assert result.rebalancing_insight.model_version == "rebalancing-v1"
    assert result.rebalancing_proposals[0].source == "AI"
    assert (
        result.rebalancing_proposals[0].why_now
        == "현재 목표 비중과의 차이가 5%p로 확대됐습니다."
    )
    assert client.context.validated_candidates[0].recommended_amount == Decimal(
        "50000.00"
    )


def test_home_does_not_forward_fabricated_ai_rebalancing_values() -> None:
    candidate = calculate_rebalancing(
        Decimal("1000000"),
        {"005930": Decimal("20.00")},
        {"005930": Decimal("0.15")},
        {"005930": "삼성전자"},
    )[0]

    portfolio = PortfolioResponse(
        account_id=uuid4(),
        cash_balance=Decimal("800000"),
        total_purchase_amount=Decimal("200000"),
        total_evaluation_amount=Decimal("200000"),
        total_assets=Decimal("1000000"),
        unrealized_profit=Decimal("0"),
        realized_profit=Decimal("0"),
        return_rate=Decimal("0"),
        today_profit=None,
        top_contributor=None,
        contributions=[],
        strategy_targets_available=True,
        rebalancing_proposals=[candidate],
        positions=[],
    )

    class FabricatingClient:
        async def analyze(self, _context):
            return AIRebalancingResult(
                summary="잘못된 금액을 포함합니다.",
                proposals=[
                    {
                        "stock_code": "005930",
                        "priority": 1,
                        "current_weight": "20.00",
                        "target_weight": "15.00",
                        "weight_diff": "5.00",
                        "action": "SELL",
                        "recommended_amount": "999999.00",
                        "reason": "제안 이유",
                        "why_now": "현재 제안 이유",
                    }
                ],
            )

    service = PortfolioService.__new__(PortfolioService)
    service.rebalancing_client = FabricatingClient()
    service.rebalancing_model_version = "rebalancing-v1"
    account = SimpleNamespace(operation_mode="SEMI_AUTO", selected_strategy_id="low")

    insight, proposals = asyncio.run(
        service._ai_rebalancing(
            account,
            portfolio,
            valuation_as_of=None,
        )
    )

    assert insight.status == "UNAVAILABLE"
    assert proposals == []


def test_evaluate_combines_real_metadata_quote_and_daily_contribution() -> None:
    account_id = uuid4()
    account = SimpleNamespace(
        id=account_id,
        cash_balance=Decimal("300000"),
        invested_principal=Decimal("1000000"),
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
    service.market_repo = SimpleNamespace(
        stock=lambda _code: SimpleNamespace(stock_name="삼성전자", sector="반도체")
    )
    service.market = SimpleNamespace(
        get_quote=lambda _code: CurrentQuote(
            stock_code="005930",
            price=Decimal("71000"),
            previous_close=Decimal("70500"),
            change_amount=Decimal("500"),
            change_rate=Decimal("0.71"),
            volume=100,
            as_of=datetime(2026, 8, 25, tzinfo=UTC),
            source="KIS",
        )
    )

    result = service.evaluate(1, account_id)

    assert result.total_assets == Decimal("1010000.00")
    assert result.valuation_profit == Decimal("10000.00")
    assert result.return_rate == Decimal("1.00")
    assert result.positions[0].stock_name == "삼성전자"
    assert result.positions[0].weight == Decimal("70.30")
    assert result.today_profit == Decimal("5000.00")
    assert result.top_contributor and result.top_contributor.stock_code == "005930"


def test_evaluate_does_not_report_partial_today_profit_as_complete() -> None:
    account_id = uuid4()
    account = SimpleNamespace(
        id=account_id, cash_balance=Decimal("0"), selected_strategy_id=None
    )
    positions = [
        SimpleNamespace(
            stock_code="005930",
            quantity=1,
            average_price=Decimal("70000"),
            realized_profit=Decimal("0"),
        ),
        SimpleNamespace(
            stock_code="000660",
            quantity=1,
            average_price=Decimal("120000"),
            realized_profit=Decimal("0"),
        ),
    ]
    quotes = {
        "005930": CurrentQuote(
            "005930",
            Decimal("71000"),
            Decimal("70500"),
            Decimal("500"),
            Decimal("0.71"),
            100,
            datetime.now(UTC),
        ),
        "000660": CurrentQuote(
            "000660", Decimal("121000"), None, None, None, 100, datetime.now(UTC)
        ),
    }

    service = PortfolioService.__new__(PortfolioService)
    service.session = SimpleNamespace()
    service.repo = SimpleNamespace(
        owned_account=lambda *_args: account, positions=lambda *_args: positions
    )
    service.market_repo = SimpleNamespace(stock=lambda _code: None)
    service.market = SimpleNamespace(get_quote=lambda code: quotes[code])

    result = service.evaluate(1, account_id)

    assert result.today_profit is None
    assert result.contributions[0].amount == Decimal("500.00")
    assert result.contributions[0].share_rate is None


def test_evaluate_falls_back_to_latest_krx_close_when_live_quote_fails() -> None:
    account_id = uuid4()
    account = SimpleNamespace(
        id=account_id, cash_balance=Decimal("300000"), selected_strategy_id=None
    )
    position = SimpleNamespace(
        stock_code="005930",
        quantity=Decimal("1.5"),
        average_price=Decimal("70000"),
        realized_profit=Decimal("0"),
    )
    prices = [
        SimpleNamespace(
            trade_date=date(2026, 8, 25),
            close_price=Decimal("71000"),
            change_amount=Decimal("500"),
            change_rate=Decimal("0.71"),
            volume=1000,
            source="KRX",
        ),
        SimpleNamespace(trade_date=date(2026, 8, 24), close_price=Decimal("70500")),
    ]

    def fail_live_quote(_stock_code: str) -> CurrentQuote:
        raise ServiceError(
            "KIS_UNAVAILABLE", "현재 시장가격을 조회하지 못했습니다.", 503
        )

    service = PortfolioService.__new__(PortfolioService)
    service.session = SimpleNamespace()
    service.repo = SimpleNamespace(
        owned_account=lambda *_args: account, positions=lambda *_args: [position]
    )
    service.market_repo = SimpleNamespace(
        stock=lambda _code: SimpleNamespace(stock_name="삼성전자", sector="반도체"),
        latest_price=lambda _code: prices[0],
        closing_prices=lambda *_args: prices,
    )
    service.market = SimpleNamespace(get_quote=fail_live_quote)

    result = service.evaluate(1, account_id)

    assert len(result.positions) == 1
    assert result.positions[0].quantity == Decimal("1.5")
    assert result.positions[0].current_price == Decimal("71000")
    assert result.positions[0].previous_close == Decimal("70500")
    assert result.positions[0].price_source == "KRX"


def test_daily_snapshot_task_writes_and_commits_once() -> None:
    account = SimpleNamespace(id=uuid4())
    response = SimpleNamespace(
        cash_balance=Decimal("100"),
        total_purchase_amount=Decimal("200"),
        total_evaluation_amount=Decimal("220"),
        total_assets=Decimal("320"),
        unrealized_profit=Decimal("20"),
        realized_profit=Decimal("10"),
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
            trade_date=date(2026, 8, 25),
            close_price=Decimal("71000"),
            change_amount=Decimal("500"),
            change_rate=Decimal("0.71"),
            volume=1000,
            source="KRX",
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
