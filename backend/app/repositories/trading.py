"""거래 도메인의 SQLAlchemy repository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Position, Strategy, VirtualAccount


class TradingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def owned_account(self, account_id: UUID, user_id: int, *, lock: bool = False) -> VirtualAccount | None:
        query = select(VirtualAccount).where(VirtualAccount.id == account_id, VirtualAccount.user_id == user_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def account_for_user(self, user_id: int) -> VirtualAccount | None:
        return self.session.scalar(select(VirtualAccount).where(VirtualAccount.user_id == user_id))

    def position(self, account_id: UUID, stock_code: str, *, lock: bool = False) -> Position | None:
        query = select(Position).where(Position.account_id == account_id, Position.stock_code == stock_code)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def positions(self, account_id: UUID) -> list[Position]:
        return list(self.session.scalars(select(Position).where(Position.account_id == account_id).order_by(Position.id)))

    def order_by_idempotency(self, account_id: UUID, key: str) -> Order | None:
        return self.session.scalar(select(Order).where(Order.account_id == account_id, Order.idempotency_key == key))

    def strategies(self) -> list[Strategy]:
        return list(self.session.scalars(select(Strategy).where(Strategy.is_active.is_(True)).order_by(Strategy.id)))

    def strategy(self, strategy_id: str) -> Strategy | None:
        return self.session.get(Strategy, strategy_id)
