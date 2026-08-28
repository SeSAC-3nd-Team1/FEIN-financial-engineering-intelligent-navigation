"""1년 투자 이력이 준비된 개발·데모 전용 계정을 멱등 생성한다."""

from argparse import ArgumentParser, Namespace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
import os
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    AccountDeposit,
    CashLedger,
    Execution,
    InvestmentOnboarding,
    InvestorProfileAssessment,
    MarketIndex,
    MarketStockPrice,
    Order,
    PortfolioSnapshot,
    Position,
    Strategy,
    StrategyTargetWeight,
    Term,
    User,
    UserAgreement,
    VirtualAccount,
)
from app.services.model_recommendation import ModelRecommendationService
from scripts.demo_history import SimulationResult, simulate_history
from scripts.historical_momentum import (
    PriceBar,
    monthly_signal_dates,
    select_momentum_targets,
)

DEMO_VERSION = "minjun-1y-v3"
DEMO_LOGIN_ID = "demomin32"
DEMO_EMAIL = "demo.minjun@example.invalid"
INITIAL_CASH = Decimal("3000000.00")
HISTORY_TRADING_DAYS = 253
KST = ZoneInfo("Asia/Seoul")


def model_target_weights(snapshot) -> dict[str, Decimal]:
    """실제 최신 모멘텀 산출물만 95% 주식 목표 비중으로 변환한다."""

    if snapshot.source != "generated" or snapshot.is_stale:
        raise RuntimeError("최신 generated 모멘텀 모델 추천이 필요합니다.")
    weights = {
        item.symbol: Decimal(str(item.target_weight))
        for item in snapshot.recommendations
        if item.target_weight > 0
    }
    if not weights or sum(weights.values(), Decimal("0")) != Decimal("0.95"):
        raise RuntimeError("모멘텀 모델 목표 주식 비중 합계는 0.95여야 합니다.")
    return weights


def ensure_demo_environment(enabled: str, environment: str) -> None:
    if enabled.lower() not in {"1", "true", "yes"}:
        raise RuntimeError(
            "DEMO_SEED_ENABLED=true를 명시해야 데모 시드를 실행할 수 있습니다."
        )
    if environment.strip().lower() in {"prod", "production", "live"}:
        raise RuntimeError("운영 환경에서는 데모 시드를 실행할 수 없습니다.")


def _historical_model_history(
    session: Session,
    final_model_date: date,
    final_model_weights: dict[str, Decimal],
) -> tuple[
    list[date],
    dict[str, dict[date, Decimal]],
    dict[int, dict[str, Decimal]],
    dict[int, date],
]:
    index_dates = sorted(
        set(
            session.scalars(
                select(MarketIndex.trade_date).where(
                    MarketIndex.market == "KOSPI",
                    MarketIndex.index_name.in_(("코스피", "KOSPI")),
                )
            )
        )
    )
    if len(index_dates) < HISTORY_TRADING_DAYS:
        raise RuntimeError(
            "KOSPI 거래일이 부족합니다: "
            f"필요={HISTORY_TRADING_DAYS}, 실제={len(index_dates)}"
        )
    trading_dates = index_dates[-HISTORY_TRADING_DAYS:]
    if final_model_date not in trading_dates:
        raise RuntimeError("최신 모델 기준일이 1년 데모 거래 기간에 없습니다.")
    warmup_start = trading_dates[0] - timedelta(days=260)
    rows = session.execute(
        select(
            MarketStockPrice.stock_code,
            MarketStockPrice.trade_date,
            MarketStockPrice.open_price,
            MarketStockPrice.high_price,
            MarketStockPrice.low_price,
            MarketStockPrice.close_price,
            MarketStockPrice.volume,
            MarketStockPrice.trading_value,
            MarketStockPrice.market_cap,
        )
        .where(
            MarketStockPrice.trade_date >= warmup_start,
            MarketStockPrice.trade_date <= trading_dates[-1],
        )
        .order_by(MarketStockPrice.stock_code, MarketStockPrice.trade_date)
    )
    bars_by_stock: dict[str, list[PriceBar]] = {}
    for row in rows:
        bar = PriceBar(*row)
        bars_by_stock.setdefault(bar.stock_code, []).append(bar)

    signal_dates = sorted(set(monthly_signal_dates(trading_dates)) | {final_model_date})
    weights_by_date = {
        signal_date: select_momentum_targets(bars_by_stock, signal_date)
        for signal_date in signal_dates
    }
    if weights_by_date[final_model_date] != final_model_weights:
        raise RuntimeError(
            "DB 시점 데이터로 재현한 최신 모멘텀 결과가 generated 산출물과 다릅니다."
        )

    selected_codes = sorted(
        {code for weights in weights_by_date.values() for code in weights}
    )
    closes: dict[str, dict[date, Decimal]] = {}
    for stock_code in selected_codes:
        observed = {
            bar.trade_date: Decimal(bar.close_price)
            for bar in bars_by_stock[stock_code]
            if bar.close_price is not None and bar.close_price > 0
        }
        aligned: dict[date, Decimal] = {}
        last_close: Decimal | None = None
        for trading_date in trading_dates:
            last_close = observed.get(trading_date, last_close)
            if last_close is None:
                raise RuntimeError(f"{stock_code} 평가 종가가 없습니다: {trading_date}")
            aligned[trading_date] = last_close
        closes[stock_code] = aligned

    date_to_index = {
        trading_date: index for index, trading_date in enumerate(trading_dates)
    }
    schedule = {date_to_index[day]: weights for day, weights in weights_by_date.items()}
    schedule_dates = {date_to_index[day]: day for day in weights_by_date}
    return trading_dates, closes, schedule, schedule_dates


def _publish_model_targets(
    session: Session,
    effective_from: date,
    target_weights: dict[str, Decimal],
) -> None:
    existing = list(
        session.scalars(
            select(StrategyTargetWeight).where(
                StrategyTargetWeight.strategy_id == "momentum",
                StrategyTargetWeight.effective_from == effective_from,
            )
        )
    )
    if existing:
        current = {row.stock_code: Decimal(row.target_weight) for row in existing}
        if current != target_weights:
            raise RuntimeError(
                "같은 기준일의 모멘텀 목표 비중이 다르게 저장돼 있습니다."
            )
        return
    session.add_all(
        [
            StrategyTargetWeight(
                strategy_id="momentum",
                stock_code=stock_code,
                target_weight=weight,
                effective_from=effective_from,
            )
            for stock_code, weight in target_weights.items()
        ]
    )


def _latest_terms(session: Session, effective_at: datetime) -> list[Term]:
    rows = session.scalars(
        select(Term)
        .where(Term.effective_at <= effective_at)
        .order_by(Term.term_code, Term.effective_at.desc(), Term.id.desc())
    )
    latest: dict[str, Term] = {}
    for term in rows:
        latest.setdefault(term.term_code, term)
    return list(latest.values())


def _already_seeded(
    session: Session, login_id: str
) -> tuple[User, VirtualAccount] | None:
    user = session.scalar(select(User).where(User.user_id == login_id))
    if user is None:
        return None
    account = session.scalar(
        select(VirtualAccount).where(
            VirtualAccount.user_id == user.id,
            VirtualAccount.operation_mode == "AUTO",
        )
    )
    if account is None:
        raise RuntimeError(
            "같은 로그인 아이디의 기존 사용자가 있어 데모 계정을 만들 수 없습니다."
        )
    marker = session.scalar(
        select(Order.id)
        .where(
            Order.account_id == account.id,
            Order.idempotency_key.like(f"demo-{DEMO_VERSION}-%"),
        )
        .limit(1)
    )
    if marker is None:
        raise RuntimeError(
            "같은 로그인 아이디의 기존 계정이 데모 시드 소유가 아닙니다."
        )
    return user, account


def _persist_simulation(
    session: Session,
    account: VirtualAccount,
    simulation: SimulationResult,
) -> None:
    for trade in simulation.trades:
        executed_at = datetime.combine(
            trade.trade_date, time(15, 31, trade.sequence % 60), tzinfo=KST
        )
        order = Order(
            id=uuid4(),
            account_id=account.id,
            stock_code=trade.stock_code,
            side=trade.side,
            order_type="MARKET",
            quantity=trade.quantity,
            requested_price=trade.price,
            status="FILLED",
            idempotency_key=(
                f"demo-{DEMO_VERSION}-{trade.trade_date.isoformat()}-"
                f"{trade.sequence}-{trade.stock_code}-{trade.side.lower()}"
            ),
            requested_at=executed_at,
        )
        session.add(order)
        # ORM relationship을 사용하지 않고 UUID FK만 직접 지정하므로 주문을 먼저
        # 확정해 executions의 FK insert 순서를 명시적으로 보장한다.
        session.flush()
        session.add(
            Execution(
                order_id=order.id,
                account_id=account.id,
                stock_code=trade.stock_code,
                side=trade.side,
                quantity=trade.quantity,
                execution_price=trade.price,
                executed_at=executed_at,
            )
        )
        session.add(
            CashLedger(
                account_id=account.id,
                transaction_type=trade.side,
                amount=-trade.amount if trade.side == "BUY" else trade.amount,
                balance_after=trade.cash_after,
                reference_type="ORDER",
                reference_id=str(order.id),
                created_at=executed_at,
            )
        )

    for stock_code, holding in simulation.holdings.items():
        session.add(
            Position(
                account_id=account.id,
                stock_code=stock_code,
                quantity=holding.quantity,
                average_price=holding.average_price,
                realized_profit=holding.realized_profit,
            )
        )
    for item in simulation.snapshots:
        session.add(
            PortfolioSnapshot(
                account_id=account.id,
                snapshot_date=item.snapshot_date,
                cash_balance=item.cash_balance,
                total_purchase_amount=item.total_purchase_amount,
                total_evaluation_amount=item.total_evaluation_amount,
                total_assets=item.total_assets,
                unrealized_profit=item.unrealized_profit,
                realized_profit=item.realized_profit,
                return_rate=item.return_rate,
            )
        )


def seed_demo_account(
    session: Session,
    *,
    password: str,
    login_id: str = DEMO_LOGIN_ID,
    email: str = DEMO_EMAIL,
) -> tuple[User, VirtualAccount, SimulationResult | None]:
    if len(password) < 8:
        raise RuntimeError("DEMO_ACCOUNT_PASSWORD는 8자 이상이어야 합니다.")
    existing = _already_seeded(session, login_id)
    if existing is not None:
        return existing[0], existing[1], None

    strategy = session.get(Strategy, "momentum")
    if strategy is None or not strategy.is_active:
        raise RuntimeError(
            "활성 momentum 전략이 없습니다. DB migration/seed를 먼저 실행해주세요."
        )
    model_snapshot = ModelRecommendationService().latest()
    final_target_weights = model_target_weights(model_snapshot)
    trading_dates, closes, target_schedule, target_schedule_dates = (
        _historical_model_history(
            session,
            model_snapshot.as_of,
            final_target_weights,
        )
    )
    first_weights = target_schedule[0]
    simulation = simulate_history(
        trading_dates,
        closes,
        first_weights,
        initial_cash=INITIAL_CASH,
        target_weight_schedule=target_schedule,
    )
    started_at = datetime.combine(trading_dates[0], time(9), tzinfo=KST)
    now = datetime.now(UTC)

    try:
        user = User(
            user_id=login_id,
            password_hash=hash_password(password),
            name="김민준",
            birthdate="940315",
            phone_number="01000000000",
            email=email.lower(),
            email_verified_at=started_at,
            member_type="ASSOCIATE",
            account_status="ACTIVE",
            active_operation_mode="AUTO",
            operation_mode_changed_at=started_at,
            created_at=started_at,
            updated_at=now,
        )
        session.add(user)
        session.flush()
        # 투자 이력은 데모를 위해 소급하지만 약관 동의는 현재 유효한 버전에 현재 시점으로 남긴다.
        for term in _latest_terms(session, now):
            session.add(
                UserAgreement(
                    user_id=user.id,
                    term_id=term.id,
                    is_agreed=True,
                    agreed_at=now,
                    user_agent=f"demo-seed/{DEMO_VERSION}",
                )
            )
        session.add(
            InvestorProfileAssessment(
                user_id=user.id,
                questionnaire_version="v1",
                analysis_version="v1",
                profile_type="성장추구형",
                stability=2,
                return_seeking=4,
                horizon=4,
                tendency_line="변동성을 감수하며 중장기 자산 성장을 추구해요.",
                description="투자 경험은 짧지만 장기 성장과 수익을 중시하는 사회초년생 데모 성향입니다.",
                analysis_summary=[
                    "투자 기간은 3~5년을 생각하고 있어요.",
                    "금융자산의 10~30% 범위에서 투자해요.",
                    "약 20% 손실까지 감내할 수 있어요.",
                ],
                model_version="demo-fixed-v1",
                prompt_version="v1",
                created_at=started_at,
            )
        )
        account = VirtualAccount(
            user_id=user.id,
            operation_mode="AUTO",
            account_name="민준의 AI 자동투자",
            initial_cash=INITIAL_CASH,
            cash_balance=simulation.final_cash,
            invested_principal=INITIAL_CASH,
            status="ACTIVE",
            selected_strategy_id="momentum",
            created_at=started_at,
            updated_at=now,
        )
        session.add(account)
        session.flush()
        onboarding = InvestmentOnboarding(
            user_id=user.id,
            strategy_id="momentum",
            investment_amount=INITIAL_CASH,
            operation_mode="AUTO",
            status="COMPLETED",
            account_id=account.id,
            completed_at=started_at,
            created_at=started_at,
            updated_at=started_at,
        )
        session.add(onboarding)
        session.flush()
        deposit = AccountDeposit(
            account_id=account.id,
            onboarding_id=onboarding.id,
            amount=INITIAL_CASH,
            balance_after=INITIAL_CASH,
            status="COMPLETED",
            idempotency_key=f"demo-{DEMO_VERSION}-initial-deposit",
            created_at=started_at,
            completed_at=started_at,
        )
        session.add(deposit)
        session.flush()
        session.add(
            CashLedger(
                account_id=account.id,
                transaction_type="INITIAL_DEPOSIT",
                amount=INITIAL_CASH,
                balance_after=INITIAL_CASH,
                reference_type="ACCOUNT_DEPOSIT",
                reference_id=str(deposit.id),
                created_at=started_at,
            )
        )
        for schedule_index, weights in sorted(target_schedule.items()):
            _publish_model_targets(
                session,
                target_schedule_dates[schedule_index],
                weights,
            )
        _persist_simulation(session, account, simulation)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return user, account, simulation


def parse_args() -> Namespace:
    parser = ArgumentParser(description="1년 이력이 포함된 데모 계정을 생성합니다.")
    parser.add_argument("--user-id", default=DEMO_LOGIN_ID)
    parser.add_argument("--email", default=DEMO_EMAIL)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_demo_environment(
        os.getenv("DEMO_SEED_ENABLED", ""),
        os.getenv("APP_ENV", "development"),
    )
    password = os.getenv("DEMO_ACCOUNT_PASSWORD", "")
    if not password:
        raise RuntimeError("DEMO_ACCOUNT_PASSWORD 환경변수가 필요합니다.")
    with SessionLocal() as session:
        user, account, simulation = seed_demo_account(
            session,
            password=password,
            login_id=args.user_id,
            email=args.email,
        )
    status = "ALREADY_SEEDED" if simulation is None else "CREATED"
    snapshot_count = 0 if simulation is None else len(simulation.snapshots)
    trade_count = 0 if simulation is None else len(simulation.trades)
    print(
        f"status={status} user_id={user.user_id} account_id={account.id} "
        f"snapshots={snapshot_count} trades={trade_count}"
    )


if __name__ == "__main__":
    main()
