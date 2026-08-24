"""거래 도메인의 SQLAlchemy repository."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Order, PortfolioSnapshot, Position, RebalancingDecision, Strategy, StrategyTargetWeight, VirtualAccount


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

    def active_accounts(self) -> list[VirtualAccount]:
        return list(self.session.scalars(
            select(VirtualAccount).where(VirtualAccount.status == "ACTIVE").order_by(VirtualAccount.id)
        ))

    def save_snapshot(self, account_id: UUID, snapshot_date: date, **values) -> None:
        """동시 조회도 계좌·일자 한 행으로 수렴하도록 PostgreSQL UPSERT한다."""

        statement = insert(PortfolioSnapshot).values(
            account_id=account_id,
            snapshot_date=snapshot_date,
            **values,
        )
        self.session.execute(statement.on_conflict_do_update(
            constraint="uq_portfolio_snapshots_account_date",
            set_={**values, "updated_at": func.now()},
        ))

    def snapshots_since(self, account_id: UUID, start_date: date | None) -> list[PortfolioSnapshot]:
        query = select(PortfolioSnapshot).where(PortfolioSnapshot.account_id == account_id)
        if start_date is not None:
            query = query.where(PortfolioSnapshot.snapshot_date >= start_date)
        return list(self.session.scalars(query.order_by(PortfolioSnapshot.snapshot_date)))

    def latest_snapshot(self, account_id: UUID, effective_on: date | None = None) -> PortfolioSnapshot | None:
        query = select(PortfolioSnapshot).where(PortfolioSnapshot.account_id == account_id)
        if effective_on is not None:
            query = query.where(PortfolioSnapshot.snapshot_date <= effective_on)
        return self.session.scalar(query.order_by(PortfolioSnapshot.snapshot_date.desc()).limit(1))

    def decision_by_idempotency(self, account_id: UUID, key: str) -> RebalancingDecision | None:
        return self.session.scalar(select(RebalancingDecision).where(
            RebalancingDecision.account_id == account_id,
            RebalancingDecision.idempotency_key == key,
        ))

    def add_decision(self, decision: RebalancingDecision) -> None:
        self.session.add(decision)

    def decisions_since(self, account_id: UUID, created_after: datetime) -> list[RebalancingDecision]:
        return list(self.session.scalars(
            select(RebalancingDecision)
            .where(
                RebalancingDecision.account_id == account_id,
                RebalancingDecision.created_at >= created_after,
            )
            .order_by(RebalancingDecision.created_at.desc())
        ))

    def target_weights(self, strategy_id: str, effective_on: date) -> dict[str, Decimal]:
        latest_effective_from = self.session.scalar(
            select(func.max(StrategyTargetWeight.effective_from)).where(
                StrategyTargetWeight.strategy_id == strategy_id,
                StrategyTargetWeight.effective_from <= effective_on,
            )
        )
        if latest_effective_from is None:
            return {}
        rows = self.session.scalars(
            select(StrategyTargetWeight)
            .where(
                StrategyTargetWeight.strategy_id == strategy_id,
                StrategyTargetWeight.effective_from == latest_effective_from,
            )
            .order_by(StrategyTargetWeight.id)
        )
        return {row.stock_code: row.target_weight for row in rows}

    def order_by_idempotency(self, account_id: UUID, key: str) -> Order | None:
        return self.session.scalar(select(Order).where(Order.account_id == account_id, Order.idempotency_key == key))

    def strategies(self) -> list[Strategy]:
        return list(self.session.scalars(select(Strategy).where(Strategy.is_active.is_(True)).order_by(Strategy.id)))

    def strategy(self, strategy_id: str) -> Strategy | None:
        return self.session.get(Strategy, strategy_id)
