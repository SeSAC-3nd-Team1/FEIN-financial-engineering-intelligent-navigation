"""Create the two presentation accounts used by the production demo.

This is an explicit, idempotent, operator-run seed.  It never changes an
existing user and requires a second production opt-in when run against the
demo deployment.
"""

from __future__ import annotations

from argparse import ArgumentParser
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, ROUND_DOWN
import os
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    AccountDeposit, CashLedger, Execution, InvestmentOnboarding,
    InvestorProfileAssessment, MarketIndex, MarketStockPrice, Order,
    PortfolioSnapshot, Position, StrategyTargetWeight, Term, User,
    UserAgreement, VirtualAccount,
)
from app.services.loss_avoidance_backtest import run_loss_avoidance_backtest
from app.services.model_recommendation import ModelRecommendationService
from app.repositories.backtest import StockPricePoint


KST = ZoneInfo("Asia/Seoul")
OLD_ID = "demoold1"
OLD_EMAIL = "demo.old@example.invalid"
NEW_ID = "demonew1"
NEW_EMAIL = "demo.new@example.invalid"
INITIAL_CASH = Decimal("10000000.00")
SEED_VERSION = "loss-avoidance-demo-1y-v1"


def require_explicit_demo_mode() -> None:
    if os.getenv("DEMO_SEED_ENABLED", "").lower() not in {"1", "true", "yes"}:
        raise RuntimeError("DEMO_SEED_ENABLED=true가 필요합니다.")
    if os.getenv("DEMO_SEED_TARGET", "").lower() != "production":
        raise RuntimeError("운영 데모 계정은 DEMO_SEED_TARGET=production이 필요합니다.")


def latest_terms(session, now: datetime) -> list[Term]:
    latest: dict[str, Term] = {}
    for term in session.scalars(
        select(Term).where(Term.effective_at <= now).order_by(Term.term_code, Term.effective_at.desc(), Term.id.desc())
    ):
        latest.setdefault(term.term_code, term)
    return list(latest.values())


def create_user(session, login_id: str, email: str, password: str, now: datetime) -> User:
    existing = session.scalar(select(User).where(User.user_id == login_id))
    if existing is not None:
        return existing
    user = User(
        user_id=login_id,
        password_hash=hash_password(password),
        name="김민준" if login_id == OLD_ID else "김서연",
        birthdate="940315" if login_id == OLD_ID else "990701",
        phone_number="01000000000" if login_id == OLD_ID else "01000000001",
        email=email,
        email_verified_at=now,
        member_type="ASSOCIATE",
        account_status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    session.flush()
    for term in latest_terms(session, now):
        session.add(UserAgreement(user_id=user.id, term_id=term.id, is_agreed=True, agreed_at=now, user_agent=f"demo-seed/{SEED_VERSION}"))
    session.add(InvestorProfileAssessment(
        user_id=user.id, questionnaire_version="v1", analysis_version="v1",
        profile_type="성장추구형", stability=2, return_seeking=4, horizon=4,
        tendency_line="장기 성장을 추구하는 데모 투자자예요.",
        description="FE!N 발표용 데모 투자성향입니다.",
        analysis_summary=["중장기 투자", "수익률과 위험을 함께 확인", "가상계좌 사용"],
        model_version="demo-fixed-v1", prompt_version="v1", created_at=now,
    ))
    return user


def get_or_create_new_user(session, password: str) -> User:
    now = datetime.now(UTC)
    return create_user(session, NEW_ID, NEW_EMAIL, password, now)


def seed_existing(session, password: str) -> tuple[User, VirtualAccount, bool]:
    now = datetime.now(UTC)
    user = create_user(session, OLD_ID, OLD_EMAIL, password, now)
    account = session.scalar(select(VirtualAccount).where(VirtualAccount.user_id == user.id, VirtualAccount.operation_mode == "AUTO"))
    if account is not None:
        return user, account, False

    snapshot = ModelRecommendationService(Path("/model-artifacts/loss_avoidance_snapshot.json")).latest()
    if snapshot.source != "generated" or snapshot.model_version != "algorithm-v2.4-fix2":
        raise RuntimeError("생성된 algorithm-v2.4-fix2 산출물이 필요합니다.")
    targets = {item.symbol: Decimal(str(item.target_weight)) for item in snapshot.recommendations if item.target_weight > 0}
    if not targets or sum(targets.values(), Decimal("0")) > Decimal("0.95"):
        raise RuntimeError("물림방지 목표 비중이 올바르지 않습니다.")
    index_dates = sorted(set(session.scalars(select(MarketIndex.trade_date).where(MarketIndex.market == "KOSPI", MarketIndex.index_name.in_(("코스피", "KOSPI"))))))
    trading_dates = index_dates[-253:]
    if len(trading_dates) < 253:
        raise RuntimeError("1년 데모에 필요한 KOSPI 거래일이 부족합니다.")
    warmup = trading_dates[0] - timedelta(days=260)
    rows = session.scalars(select(MarketStockPrice).where(MarketStockPrice.stock_code.in_(targets), MarketStockPrice.trade_date >= warmup, MarketStockPrice.trade_date <= trading_dates[-1]).order_by(MarketStockPrice.stock_code, MarketStockPrice.trade_date))
    points = [StockPricePoint(r.stock_code, r.trade_date, r.close_price, market_cap=r.market_cap, volume=r.volume, trading_value=r.trading_value, open_price=r.open_price, high_price=r.high_price, low_price=r.low_price) for r in rows]
    curve = run_loss_avoidance_backtest(points, trading_dates)
    started_at = datetime.combine(trading_dates[0], time(9), tzinfo=KST)
    account = VirtualAccount(user_id=user.id, operation_mode="AUTO", account_name="민준의 물림방지 자동투자", initial_cash=INITIAL_CASH, cash_balance=INITIAL_CASH * Decimal("0.05"), invested_principal=INITIAL_CASH, status="ACTIVE", selected_strategy_id="low", created_at=started_at, updated_at=now)
    session.add(account); session.flush()
    onboarding = InvestmentOnboarding(user_id=user.id, strategy_id="low", investment_amount=INITIAL_CASH, operation_mode="AUTO", status="COMPLETED", account_id=account.id, completed_at=started_at, created_at=started_at, updated_at=started_at)
    session.add(onboarding); session.flush()
    deposit = AccountDeposit(account_id=account.id, onboarding_id=onboarding.id, amount=INITIAL_CASH, balance_after=INITIAL_CASH, status="COMPLETED", idempotency_key=f"demo-{SEED_VERSION}-deposit", created_at=started_at, completed_at=started_at)
    session.add(deposit); session.flush()
    session.add(CashLedger(account_id=account.id, transaction_type="INITIAL_DEPOSIT", amount=INITIAL_CASH, balance_after=INITIAL_CASH, reference_type="ACCOUNT_DEPOSIT", reference_id=str(deposit.id), created_at=started_at))
    latest_prices = {code: session.scalar(select(MarketStockPrice).where(MarketStockPrice.stock_code == code).order_by(MarketStockPrice.trade_date.desc()).limit(1)) for code in targets}
    cash = INITIAL_CASH
    for code, weight in targets.items():
        price = latest_prices[code].close_price
        quantity = (INITIAL_CASH * weight / price).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        amount = (price * quantity).quantize(Decimal("0.01"))
        if quantity <= 0 or amount > cash:
            continue
        order = Order(id=uuid4(), account_id=account.id, stock_code=code, side="BUY", order_type="MARKET", quantity=quantity, requested_price=price, status="FILLED", idempotency_key=f"demo-{SEED_VERSION}-{snapshot.as_of}-{code}", requested_at=started_at)
        session.add(order); session.flush()
        session.add(Execution(order_id=order.id, account_id=account.id, stock_code=code, side="BUY", quantity=quantity, execution_price=price, executed_at=started_at))
        session.add(Position(account_id=account.id, stock_code=code, quantity=quantity, average_price=price, realized_profit=Decimal("0")))
        session.add(CashLedger(account_id=account.id, transaction_type="BUY", amount=-amount, balance_after=cash - amount, reference_type="ORDER", reference_id=str(order.id), created_at=started_at))
        cash -= amount
        session.add(StrategyTargetWeight(strategy_id="low", stock_code=code, target_weight=weight, effective_from=snapshot.as_of))
    for trade_date, value in zip(trading_dates, curve):
        assets = (INITIAL_CASH * Decimal(str(value))).quantize(Decimal("0.01"))
        session.add(PortfolioSnapshot(account_id=account.id, snapshot_date=trade_date, cash_balance=(assets * Decimal("0.05")).quantize(Decimal("0.01")), total_purchase_amount=INITIAL_CASH * Decimal("0.95"), total_evaluation_amount=(assets * Decimal("0.95")).quantize(Decimal("0.01")), total_assets=assets, unrealized_profit=assets - INITIAL_CASH, realized_profit=Decimal("0"), return_rate=(Decimal(str(value)) - Decimal("1")).quantize(Decimal("0.000001"))))
    session.commit()
    return user, account, True


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--password-old", default="demoold!2026")
    parser.add_argument("--password-new", default="demonew!2026")
    args = parser.parse_args()
    require_explicit_demo_mode()
    with SessionLocal() as session:
        old_user, old_account, old_created = seed_existing(session, args.password_old)
        new_user = get_or_create_new_user(session, args.password_new)
        session.commit()
        print(f"old={old_user.user_id} account={old_account.id} created={old_created}")
        print(f"new={new_user.user_id} created_or_existing=true")


if __name__ == "__main__":
    main()
