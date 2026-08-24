"""기존 Frontend Mock 구성을 개발용 가상 주문으로 멱등 생성한다."""

from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal, ROUND_FLOOR
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import User, VirtualAccount
from app.repositories import TradingRepository
from app.repositories.market_data import MarketDataRepository
from app.schemas.api import OrderCreateRequest
from app.services.trading import TradingService


DEMO_PORTFOLIO_VERSION = "mock-holdings-v1"
DEMO_ALLOCATIONS = (
    ("005930", "삼성전자", Decimal("0.180")),
    ("000660", "SK하이닉스", Decimal("0.162")),
    ("033780", "KT&G", Decimal("0.110")),
    ("035420", "NAVER", Decimal("0.090")),
    ("005380", "현대차", Decimal("0.064")),
    ("068270", "셀트리온", Decimal("0.048")),
    ("000270", "기아", Decimal("0.042")),
    ("051900", "LG생활건강", Decimal("0.036")),
    ("005490", "POSCO홀딩스", Decimal("0.032")),
    ("207940", "삼성바이오로직스", Decimal("0.029")),
    ("105560", "KB금융", Decimal("0.026")),
    ("055550", "신한지주", Decimal("0.024")),
    ("086790", "하나금융지주", Decimal("0.021")),
    ("000810", "삼성화재", Decimal("0.019")),
    ("066570", "LG전자", Decimal("0.018")),
    ("035720", "카카오", Decimal("0.016")),
    ("015760", "한국전력", Decimal("0.015")),
    ("017670", "SK텔레콤", Decimal("0.014")),
    ("000100", "유한양행", Decimal("0.013")),
    ("271560", "오리온", Decimal("0.011")),
)


@dataclass(frozen=True)
class SeedResult:
    stock_code: str
    stock_name: str
    quantity: Decimal
    price: Decimal
    amount: Decimal
    status: str


class KrxSeedMarket:
    """수량 계산과 체결에 PostgreSQL의 동일한 최신 KRX 종가를 사용한다."""

    def __init__(self, session: Session) -> None:
        self.repository = MarketDataRepository(session)
        self.prices: dict[str, tuple[Decimal, datetime, str]] = {}

    def get_price(self, stock_code: str) -> tuple[Decimal, datetime, str]:
        if stock_code not in self.prices:
            latest = self.repository.latest_price(stock_code)
            if latest is None or latest.close_price <= 0:
                raise RuntimeError(f"최신 KRX 종가를 찾을 수 없습니다: {stock_code}")
            as_of = datetime.combine(
                latest.trade_date,
                time(15, 30),
                tzinfo=ZoneInfo("Asia/Seoul"),
            )
            self.prices[stock_code] = (latest.close_price, as_of, "KRX")
        return self.prices[stock_code]


def allocation_quantity(initial_cash: Decimal, weight: Decimal, price: Decimal) -> Decimal:
    if initial_cash <= 0 or weight <= 0 or price <= 0:
        return Decimal("0")
    return (initial_cash * weight / price).quantize(Decimal("0.00000001"), rounding=ROUND_FLOOR)


def idempotency_key(stock_code: str) -> str:
    return f"demo-{DEMO_PORTFOLIO_VERSION}-{stock_code}"


def find_account(session: Session, login_id: str) -> tuple[User, VirtualAccount]:
    user = session.scalar(select(User).where(User.user_id == login_id))
    if user is None:
        raise RuntimeError(f"개발용 사용자를 찾을 수 없습니다: {login_id}")
    account = session.scalar(select(VirtualAccount).where(VirtualAccount.user_id == user.id))
    if account is None:
        raise RuntimeError("가상계좌가 없습니다. 먼저 앱에서 투자 시작 절차를 완료해주세요.")
    if account.status != "ACTIVE":
        raise RuntimeError("활성 상태의 가상계좌가 아닙니다.")
    return user, account


def seed_demo_portfolio(
    session: Session,
    login_id: str,
    *,
    market: KrxSeedMarket | None = None,
    dry_run: bool = False,
) -> tuple[VirtualAccount, list[SeedResult]]:
    user, account = find_account(session, login_id)
    cached_market = market or KrxSeedMarket(session)
    repository = TradingRepository(session)
    trading = TradingService(session, cached_market)
    results: list[SeedResult] = []
    planned: list[tuple[str, str, Decimal, Decimal, str]] = []
    available_cash = account.cash_balance

    for stock_code, stock_name, weight in DEMO_ALLOCATIONS:
        key = idempotency_key(stock_code)
        existing = repository.order_by_idempotency(account.id, key)
        if existing is not None:
            price = existing.requested_price or Decimal("0")
            results.append(SeedResult(
                stock_code,
                stock_name,
                existing.quantity,
                price,
                price * existing.quantity,
                "ALREADY_SEEDED",
            ))
            continue

        price, _, _ = cached_market.get_price(stock_code)
        quantity = allocation_quantity(account.initial_cash, weight, price)
        if quantity <= 0:
            raise RuntimeError(f"목표 수량을 계산할 수 없습니다: {stock_code}")
        planned.append((stock_code, stock_name, quantity, price, key))

    required_cash = sum(
        (price * quantity for _, _, quantity, price, _ in planned),
        Decimal("0"),
    )
    if required_cash > available_cash:
        raise RuntimeError(
            f"20개 Mock 종목 매수에 필요한 현금이 부족합니다: "
            f"필요={required_cash:.2f}, 보유={available_cash:.2f}"
        )

    for stock_code, stock_name, quantity, price, key in planned:
        if dry_run:
            results.append(SeedResult(
                stock_code,
                stock_name,
                quantity,
                price,
                price * quantity,
                "DRY_RUN",
            ))
            continue

        order = trading.execute_market_order(
            user.id,
            OrderCreateRequest(
                account_id=account.id,
                stock_code=stock_code,
                side="BUY",
                quantity=quantity,
                idempotency_key=key,
            ),
        )
        results.append(SeedResult(
            stock_code,
            stock_name,
            quantity,
            price,
            price * quantity,
            order.status,
        ))

    return account, results


def parse_args() -> Namespace:
    parser = ArgumentParser(description="개발용 사용자에게 기존 Mock 포트폴리오를 가상 매수합니다.")
    parser.add_argument("--user-id", required=True, help="로그인 아이디")
    parser.add_argument("--dry-run", action="store_true", help="현재가와 주문 수량만 확인합니다.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with SessionLocal() as session:
        account, results = seed_demo_portfolio(
            session,
            args.user_id,
            dry_run=args.dry_run,
        )
    print(f"account_id={account.id} initial_cash={account.initial_cash}")
    for result in results:
        print(
            f"{result.stock_code} {result.stock_name}: "
            f"quantity={result.quantity} price={result.price} "
            f"amount={result.amount:.2f} status={result.status}"
        )


if __name__ == "__main__":
    main()
