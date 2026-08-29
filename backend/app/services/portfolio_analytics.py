"""실제 KRX·OpenDART feature와 리밸런싱 판단 이력을 제공한다."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from math import sqrt
from statistics import correlation, stdev
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.models import RebalancingDecision
from app.repositories import TradingRepository
from app.repositories.market_data import MarketDataRepository
from app.schemas.api import (
    RebalancingDecisionCreateRequest,
    RebalancingDecisionHistoryResponse,
    RebalancingDecisionResponse,
    StockEvaluationAxisResponse,
    StockEvaluationResponse,
)
from app.services.portfolio import PortfolioService, validate_target_weights

FEATURE_WINDOW_DAYS = 180
MIN_PRICE_RETURNS = 40
MIN_DOWNSIDE_RETURNS = 10
DECISION_HISTORY_DAYS = 183


def _clamp_score(value: float) -> int:
    return round(max(0.0, min(100.0, value)))


def _linear_score(
    value: float, low: float, high: float, *, inverse: bool = False
) -> int:
    scaled = (value - low) / (high - low) * 100
    return _clamp_score(100 - scaled if inverse else scaled)


def _returns(
    points: list,
    value_attribute: str,
    *,
    share_attribute: str | None = None,
) -> dict[date, float]:
    ordered = sorted(points, key=lambda item: item.trade_date)
    result: dict[date, float] = {}
    previous_shares: int | None = None
    for previous, current in zip(ordered, ordered[1:]):
        previous_value = float(getattr(previous, value_attribute))
        current_value = float(getattr(current, value_attribute))
        if share_attribute and previous_shares is None:
            shares = getattr(previous, share_attribute)
            if shares is not None and shares > 0:
                previous_shares = shares
        corporate_action = False
        if share_attribute:
            shares = getattr(current, share_attribute)
            if shares is not None and shares > 0:
                corporate_action = (
                    previous_shares is not None and shares != previous_shares
                )
                previous_shares = shares
        if previous_value > 0 and not corporate_action:
            result[current.trade_date] = current_value / previous_value - 1
    return result


def _axis(
    key: str, label: str, score: int | None, basis: str
) -> StockEvaluationAxisResponse:
    return StockEvaluationAxisResponse(
        key=key,
        label=label,
        score=score,
        status="AVAILABLE" if score is not None else "UNAVAILABLE",
        basis=basis,
    )


def calculate_stability(stock_returns: dict[date, float]) -> tuple[int | None, str]:
    if len(stock_returns) < MIN_PRICE_RETURNS:
        return None, f"최근 수익률 표본이 {MIN_PRICE_RETURNS}개 미만입니다."
    annualized_volatility = stdev(stock_returns.values()) * sqrt(252)
    score = _linear_score(annualized_volatility, 0.10, 0.60, inverse=True)
    return (
        score,
        f"최근 {len(stock_returns)}거래일 연환산 변동성 {annualized_volatility * 100:.1f}%를 사용했습니다.",
    )


def calculate_financial_health(financial) -> tuple[int | None, str]:
    required = (
        financial.total_assets,
        financial.total_equity,
        financial.operating_cash_flow,
    )
    if any(value is None for value in required) or financial.total_assets <= 0:
        return None, "자산·자본·영업현금흐름 중 필요한 연간 재무값이 없습니다."
    assets = float(financial.total_assets)
    equity_ratio = float(financial.total_equity) / assets
    cash_flow_ratio = float(financial.operating_cash_flow) / assets
    score = round(
        (
            _linear_score(equity_ratio, 0.0, 0.70)
            + _linear_score(cash_flow_ratio, -0.05, 0.10)
        )
        / 2
    )
    return (
        score,
        f"{financial.business_year}년 자본비율 {equity_ratio * 100:.1f}%와 영업현금흐름/자산 {cash_flow_ratio * 100:.1f}%를 사용했습니다.",
    )


def calculate_growth(latest, previous) -> tuple[int | None, str]:
    values = (
        latest.revenue,
        latest.operating_income,
        previous.revenue,
        previous.operating_income,
    )
    if (
        any(value is None for value in values)
        or previous.revenue <= 0
        or previous.operating_income <= 0
    ):
        return None, "비교 가능한 2개 연도의 양수 매출·영업이익이 없습니다."
    revenue_growth = float(latest.revenue / previous.revenue - 1)
    operating_growth = float(latest.operating_income / previous.operating_income - 1)
    score = round(
        (
            _linear_score(revenue_growth, -0.20, 0.20)
            + _linear_score(operating_growth, -0.20, 0.20)
        )
        / 2
    )
    return (
        score,
        f"{previous.business_year}→{latest.business_year} 매출 {revenue_growth * 100:+.1f}%, 영업이익 {operating_growth * 100:+.1f}%를 사용했습니다.",
    )


def calculate_defense(
    stock_returns: dict[date, float], benchmark_returns: dict[date, float]
) -> tuple[int | None, str]:
    dates = [
        day
        for day in stock_returns.keys() & benchmark_returns.keys()
        if benchmark_returns[day] < 0
    ]
    if len(dates) < MIN_DOWNSIDE_RETURNS:
        return None, f"KOSPI 하락일 공통 표본이 {MIN_DOWNSIDE_RETURNS}개 미만입니다."
    benchmark_loss = sum(benchmark_returns[day] for day in dates)
    if benchmark_loss == 0:
        return None, "KOSPI 하락 폭을 계산할 수 없습니다."
    downside_capture = sum(stock_returns[day] for day in dates) / benchmark_loss
    score = _linear_score(downside_capture, -0.5, 2.0, inverse=True)
    return (
        score,
        f"최근 공통 KOSPI 하락일 {len(dates)}개의 하락 포착률 {downside_capture * 100:.1f}%를 사용했습니다.",
    )


def calculate_diversification(
    stock_returns: dict[date, float], other_returns: dict[date, float]
) -> tuple[int | None, str]:
    dates = sorted(stock_returns.keys() & other_returns.keys())
    if len(dates) < MIN_PRICE_RETURNS:
        return (
            None,
            f"다른 보유종목과 겹치는 수익률 표본이 {MIN_PRICE_RETURNS}개 미만입니다.",
        )
    stock_values = [stock_returns[day] for day in dates]
    portfolio_values = [other_returns[day] for day in dates]
    if len(set(stock_values)) < 2 or len(set(portfolio_values)) < 2:
        return None, "상관계수를 계산할 만큼 수익률 변화가 없습니다."
    coefficient = correlation(stock_values, portfolio_values)
    score = _linear_score(coefficient, -1.0, 1.0, inverse=True)
    return (
        score,
        f"다른 보유종목의 시가가중 수익률과 상관계수 {coefficient:.2f}를 사용했습니다.",
    )


class PortfolioAnalyticsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.trading = TradingRepository(session)
        self.market = MarketDataRepository(session)

    def stock_evaluation(
        self, user_id: int, account_id: UUID, stock_code: str
    ) -> StockEvaluationResponse:
        account = self.trading.owned_account(account_id, user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        stock = self.market.stock(stock_code)
        if not stock:
            raise NotFoundError("STOCK_NOT_FOUND", "KRX 종목정보를 찾을 수 없습니다.")
        latest_price = self.market.latest_price(stock_code)
        start_date = (
            latest_price.trade_date - timedelta(days=FEATURE_WINDOW_DAYS)
            if latest_price
            else date.today()
        )
        price_rows = (
            self.market.prices_since(stock_code, start_date) if latest_price else []
        )
        stock_returns = _returns(
            price_rows, "close_price", share_attribute="listed_shares"
        )

        financial_rows = self.market.annual_financials(stock_code)
        annual_by_year = {}
        for row in financial_rows:
            annual_by_year.setdefault(row.business_year, row)
        annuals = list(annual_by_year.values())

        stability = calculate_stability(stock_returns)
        financial_health = (
            calculate_financial_health(annuals[0])
            if annuals
            else (None, "최신 연간 OpenDART 재무제표가 없습니다.")
        )
        growth = (
            calculate_growth(annuals[0], annuals[1])
            if len(annuals) >= 2
            else (None, "비교 가능한 2개 연도의 OpenDART 재무제표가 없습니다.")
        )
        benchmark_returns = _returns(self.market.kospi_since(start_date), "close_value")
        defense = calculate_defense(stock_returns, benchmark_returns)
        other_returns = self._other_portfolio_returns(
            account_id, stock_code, start_date
        )
        diversification = calculate_diversification(stock_returns, other_returns)

        targets = (
            self.trading.target_weights(
                account.selected_strategy_id, latest_price.trade_date
            )
            if account.selected_strategy_id and latest_price
            else {}
        )
        validate_target_weights(
            targets,
            allow_cash_buffer=account.selected_strategy_id == "momentum",
        )
        target_weight = targets.get(stock_code)
        axes = [
            _axis("stability", "안정성", *stability),
            _axis("financial_health", "재무 건전성", *financial_health),
            _axis("growth", "성장성", *growth),
            _axis("defense", "방어력", *defense),
            _axis("diversification", "분산 기여", *diversification),
        ]
        available = [axis for axis in axes if axis.score is not None]
        strongest = max(available, key=lambda axis: axis.score) if available else None
        role_summary = None
        if strongest:
            target_text = (
                f" 전략 목표 비중은 {(target_weight * 100):.1f}%입니다."
                if target_weight is not None
                else ""
            )
            role_summary = f"현재 계산 가능한 항목 중 {strongest.label} 점수가 가장 높습니다.{target_text}"
        sources = []
        if price_rows:
            sources.append("KRX")
        if annuals:
            sources.append("OpenDART")
        if other_returns:
            sources.append("Portfolio")
        return StockEvaluationResponse(
            account_id=account_id,
            stock_code=stock_code,
            stock_name=stock.stock_name,
            as_of=latest_price.trade_date if latest_price else None,
            target_weight=(
                (target_weight * 100).quantize(Decimal("0.01"))
                if target_weight is not None
                else None
            ),
            role_summary=role_summary,
            axes=axes,
            sources=sources,
        )

    def _other_portfolio_returns(
        self, account_id: UUID, excluded_code: str, start_date: date
    ) -> dict[date, float]:
        series: list[tuple[float, dict[date, float]]] = []
        for position in self.trading.positions(account_id):
            if position.stock_code == excluded_code or position.quantity <= 0:
                continue
            latest = self.market.latest_price(position.stock_code)
            if latest is None:
                continue
            market_value = float(latest.close_price * position.quantity)
            returns = _returns(
                self.market.prices_since(position.stock_code, start_date),
                "close_price",
                share_attribute="listed_shares",
            )
            if market_value > 0 and returns:
                series.append((market_value, returns))
        if not series:
            return {}
        total_weight = sum(value for value, _ in series)
        dates = set().union(*(returns.keys() for _, returns in series))
        result = {}
        for day in dates:
            available = [
                (value, returns[day]) for value, returns in series if day in returns
            ]
            covered = sum(value for value, _ in available)
            if covered >= total_weight * 0.7:
                result[day] = (
                    sum(value * daily_return for value, daily_return in available)
                    / covered
                )
        return result

    def record_decision(
        self, user_id: int, request: RebalancingDecisionCreateRequest
    ) -> RebalancingDecisionResponse:
        account = self.trading.owned_account(request.account_id, user_id)
        if not account:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        existing = self.trading.decision_by_idempotency(
            request.account_id, request.idempotency_key
        )
        if existing:
            if (
                existing.stock_code != request.stock_code
                or existing.decision != request.decision
            ):
                raise ServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "동일 요청 키가 다른 리밸런싱 판단에 사용되었습니다.",
                    409,
                )
            return self._decision_response(existing)
        portfolio = PortfolioService(self.session).evaluate(user_id, request.account_id)
        proposal = next(
            (
                item
                for item in portfolio.rebalancing_proposals
                if item.stock_code == request.stock_code
            ),
            None,
        )
        if proposal is None:
            raise ServiceError(
                "REBALANCING_PROPOSAL_NOT_FOUND",
                "현재 유효한 리밸런싱 제안이 없습니다.",
                409,
            )
        baseline_date = max(
            (position.price_as_of.date() for position in portfolio.positions),
            default=datetime.now(ZoneInfo("Asia/Seoul")).date(),
        )
        proposal_key = ":".join(
            (
                str(account.selected_strategy_id or ""),
                proposal.stock_code,
                str(proposal.action),
                str(proposal.current_weight),
                str(proposal.target_weight),
                str(proposal.weight_diff),
                str(proposal.recommended_amount),
                baseline_date.isoformat(),
            )
        )
        existing_proposal = getattr(
            self.trading, "decision_by_proposal", lambda *_args: None
        )(request.account_id, proposal_key)
        if existing_proposal:
            if existing_proposal.decision != request.decision:
                raise ServiceError(
                    "REBALANCING_PROPOSAL_ALREADY_DECIDED",
                    "현재 리밸런싱 제안은 이미 다른 판단이 기록되었습니다.",
                    409,
                )
            return self._decision_response(existing_proposal)
        decision = RebalancingDecision(
            account_id=request.account_id,
            strategy_id=account.selected_strategy_id,
            stock_code=proposal.stock_code,
            stock_name=proposal.stock_name,
            action=proposal.action,
            current_weight=proposal.current_weight,
            target_weight=proposal.target_weight,
            weight_diff=proposal.weight_diff,
            recommended_amount=proposal.recommended_amount,
            decision=request.decision,
            idempotency_key=request.idempotency_key,
            proposal_key=proposal_key,
            baseline_snapshot_date=baseline_date,
            baseline_total_assets=portfolio.total_assets,
        )
        try:
            self.trading.add_decision(decision)
            self.session.commit()
            self.session.refresh(decision)
        except IntegrityError:
            self.session.rollback()
            existing = self.trading.decision_by_idempotency(
                request.account_id, request.idempotency_key
            ) or getattr(self.trading, "decision_by_proposal", lambda *_args: None)(
                request.account_id, proposal_key
            )
            if existing is None:
                raise
            if (
                existing.stock_code != request.stock_code
                or existing.decision != request.decision
            ):
                raise ServiceError(
                    "IDEMPOTENCY_CONFLICT",
                    "동일 요청 키가 다른 리밸런싱 판단에 사용되었습니다.",
                    409,
                )
            return self._decision_response(existing)
        except Exception:
            self.session.rollback()
            raise
        return self._decision_response(decision)

    def decision_history(
        self, user_id: int, account_id: UUID
    ) -> RebalancingDecisionHistoryResponse:
        if not self.trading.owned_account(account_id, user_id):
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        decisions = self.trading.decisions_since(
            account_id, datetime.now(UTC) - timedelta(days=DECISION_HISTORY_DAYS)
        )
        items = [self._decision_response(item) for item in decisions]
        return RebalancingDecisionHistoryResponse(
            account_id=account_id,
            proposed=len(items),
            accepted=sum(item.decision == "ACCEPTED" for item in items),
            held=sum(item.decision == "HELD" for item in items),
            items=items,
        )

    def _decision_response(
        self, decision: RebalancingDecision
    ) -> RebalancingDecisionResponse:
        latest = self.trading.latest_snapshot(decision.account_id)
        actual_return = None
        outcome_as_of = None
        if (
            decision.baseline_snapshot_date is not None
            and decision.baseline_total_assets is not None
            and decision.baseline_total_assets > 0
            and latest is not None
            and latest.snapshot_date > decision.baseline_snapshot_date
        ):
            actual_return = (
                (latest.total_assets / decision.baseline_total_assets - 1) * 100
            ).quantize(Decimal("0.01"))
            outcome_as_of = latest.snapshot_date
        return RebalancingDecisionResponse(
            id=decision.id,
            account_id=decision.account_id,
            strategy_id=decision.strategy_id,
            stock_code=decision.stock_code,
            stock_name=decision.stock_name,
            action=decision.action,
            current_weight=decision.current_weight,
            target_weight=decision.target_weight,
            weight_diff=decision.weight_diff,
            recommended_amount=decision.recommended_amount,
            decision=decision.decision,
            baseline_snapshot_date=decision.baseline_snapshot_date,
            actual_portfolio_return_rate=actual_return,
            outcome_as_of=outcome_as_of,
            created_at=decision.created_at,
        )
