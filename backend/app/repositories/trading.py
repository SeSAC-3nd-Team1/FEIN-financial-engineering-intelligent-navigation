"""거래 도메인의 SQLAlchemy repository."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from exchange_calendars import get_calendar
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from exchange_calendars import get_calendar

from app.models import (
    AccountCashDeposit,
    CashLedger,
    Execution,
    FundOperation,
    FundOperationOrder,
    InvestmentOnboarding,
    MarketStock,
    MarketIndex,
    MomentumRebalanceRun,
    Order,
    PortfolioSnapshot,
    Position,
    RebalancingDecision,
    Strategy,
    StrategyTargetWeight,
    User,
    VirtualAccount,
)


@dataclass(frozen=True)
class ExecutionHistoryRecord:
    execution: Execution
    stock_name: str | None


class TradingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def owned_account(
        self, account_id: UUID, user_id: int, *, lock: bool = False
    ) -> VirtualAccount | None:
        query = select(VirtualAccount).where(
            VirtualAccount.id == account_id, VirtualAccount.user_id == user_id
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def user(self, user_id: int, *, lock: bool = False) -> User | None:
        query = select(User).where(User.id == user_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def account_for_user(
        self,
        user_id: int,
        operation_mode: str,
        *,
        lock: bool = False,
    ) -> VirtualAccount | None:
        query = select(VirtualAccount).where(
            VirtualAccount.user_id == user_id,
            VirtualAccount.operation_mode == operation_mode,
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def accounts_for_user(self, user_id: int) -> list[VirtualAccount]:
        return list(
            self.session.scalars(
                select(VirtualAccount)
                .where(VirtualAccount.user_id == user_id)
                .order_by(VirtualAccount.operation_mode)
            )
        )

    def account_cash_deposit_by_idempotency(
        self,
        account_id: UUID,
        idempotency_key: str,
    ) -> AccountCashDeposit | None:
        return self.session.scalar(
            select(AccountCashDeposit).where(
                AccountCashDeposit.account_id == account_id,
                AccountCashDeposit.idempotency_key == idempotency_key,
            )
        )

    def completed_onboarding_for_user_mode(
        self,
        user_id: int,
        operation_mode: str,
    ) -> InvestmentOnboarding | None:
        return self.session.scalar(
            select(InvestmentOnboarding).where(
                InvestmentOnboarding.user_id == user_id,
                InvestmentOnboarding.operation_mode == operation_mode,
                InvestmentOnboarding.status == "COMPLETED",
            )
        )

    def position(
        self, account_id: UUID, stock_code: str, *, lock: bool = False
    ) -> Position | None:
        query = select(Position).where(
            Position.account_id == account_id, Position.stock_code == stock_code
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def positions(self, account_id: UUID) -> list[Position]:
        return list(
            self.session.scalars(
                select(Position)
                .where(Position.account_id == account_id)
                .order_by(Position.id)
            )
        )

    def active_accounts(self) -> list[VirtualAccount]:
        return list(
            self.session.scalars(
                select(VirtualAccount)
                .where(VirtualAccount.status == "ACTIVE")
                .order_by(VirtualAccount.id)
            )
        )

    def execution_history(
        self,
        account_id: UUID,
        *,
        limit: int,
        before_executed_at: datetime | None = None,
        before_id: int | None = None,
    ) -> list[ExecutionHistoryRecord]:
        """동일 시각 체결도 누락되지 않도록 시각과 PK를 함께 사용해 다음 페이지를 조회한다."""

        query = (
            select(Execution, MarketStock.stock_name)
            .outerjoin(MarketStock, MarketStock.stock_code == Execution.stock_code)
            .where(Execution.account_id == account_id)
        )
        if before_executed_at is not None and before_id is not None:
            query = query.where(
                or_(
                    Execution.executed_at < before_executed_at,
                    (Execution.executed_at == before_executed_at)
                    & (Execution.id < before_id),
                )
            )
        rows = self.session.execute(
            query.order_by(Execution.executed_at.desc(), Execution.id.desc()).limit(
                limit
            )
        )
        return [
            ExecutionHistoryRecord(execution=row[0], stock_name=row[1]) for row in rows
        ]

    def save_snapshot(self, account_id: UUID, snapshot_date: date, **values) -> None:
        """동시 조회도 계좌·일자 한 행으로 수렴하도록 PostgreSQL UPSERT한다."""

        statement = insert(PortfolioSnapshot).values(
            account_id=account_id,
            snapshot_date=snapshot_date,
            **values,
        )
        self.session.execute(
            statement.on_conflict_do_update(
                constraint="uq_portfolio_snapshots_account_date",
                set_={**values, "updated_at": func.now()},
            )
        )

    def snapshots_since(
        self, account_id: UUID, start_date: date | None
    ) -> list[PortfolioSnapshot]:
        query = select(PortfolioSnapshot).where(
            PortfolioSnapshot.account_id == account_id
        )
        if start_date is not None:
            query = query.where(PortfolioSnapshot.snapshot_date >= start_date)
        return list(
            self.session.scalars(query.order_by(PortfolioSnapshot.snapshot_date))
        )

    def external_cash_flows(
        self,
        account_id: UUID,
        started_at: datetime,
        ended_before: datetime,
    ) -> list[CashLedger]:
        """매매와 무관하게 계좌 자산을 바꾼 외부 현금흐름만 반환한다."""

        return list(
            self.session.scalars(
                select(CashLedger)
                .where(
                    CashLedger.account_id == account_id,
                    CashLedger.transaction_type.in_(
                        (
                            "INITIAL_DEPOSIT",
                            "DEPOSIT",
                            "ADDITIONAL_INVESTMENT",
                            "WITHDRAWAL",
                            "ADJUSTMENT",
                        )
                    ),
                    CashLedger.created_at >= started_at,
                    CashLedger.created_at < ended_before,
                )
                .order_by(CashLedger.created_at, CashLedger.id)
            )
        )

    def latest_snapshot(
        self, account_id: UUID, effective_on: date | None = None
    ) -> PortfolioSnapshot | None:
        query = select(PortfolioSnapshot).where(
            PortfolioSnapshot.account_id == account_id
        )
        if effective_on is not None:
            query = query.where(PortfolioSnapshot.snapshot_date <= effective_on)
        return self.session.scalar(
            query.order_by(PortfolioSnapshot.snapshot_date.desc()).limit(1)
        )

    def decision_by_idempotency(
        self, account_id: UUID, key: str
    ) -> RebalancingDecision | None:
        return self.session.scalar(
            select(RebalancingDecision).where(
                RebalancingDecision.account_id == account_id,
                RebalancingDecision.idempotency_key == key,
            )
        )

    def decision_by_proposal(
        self, account_id: UUID, proposal_key: str
    ) -> RebalancingDecision | None:
        return self.session.scalar(
            select(RebalancingDecision).where(
                RebalancingDecision.account_id == account_id,
                RebalancingDecision.proposal_key == proposal_key,
            )
        )

    def add_decision(self, decision: RebalancingDecision) -> None:
        self.session.add(decision)

    def decisions_since(
        self, account_id: UUID, created_after: datetime
    ) -> list[RebalancingDecision]:
        return list(
            self.session.scalars(
                select(RebalancingDecision)
                .where(
                    RebalancingDecision.account_id == account_id,
                    RebalancingDecision.created_at >= created_after,
                )
                .order_by(RebalancingDecision.created_at.desc())
            )
        )

    def target_weights(
        self, strategy_id: str, effective_on: date
    ) -> dict[str, Decimal]:
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
        return self.session.scalar(
            select(Order).where(
                Order.account_id == account_id, Order.idempotency_key == key
            )
        )

    def momentum_rebalance_run(
        self, account_id: UUID, year: int, quarter: int, *, lock: bool = False
    ) -> MomentumRebalanceRun | None:
        query = select(MomentumRebalanceRun).where(
            MomentumRebalanceRun.account_id == account_id,
            MomentumRebalanceRun.execution_year == year,
            MomentumRebalanceRun.execution_quarter == quarter,
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def quarter_end_trade_date(self, year: int, quarter: int):
        start_month = (quarter - 1) * 3 + 1
        start = date(year, start_month, 1)
        end_month = start_month + 2
        end = date(year, end_month + 1, 1) if end_month < 12 else date(year + 1, 1, 1)
        end = date.fromordinal(end.toordinal() - 1)
        # A partially loaded current quarter must never be treated as an
        # official decision period.
        if date.today() <= end:
            return None
        sessions = get_calendar("XKRX").sessions_in_range(start, end)
        if len(sessions) == 0:
            return None
        expected = sessions[-1].date()
        # The exchange calendar determines the date; DB data only confirms
        # that the official session has been ingested. Never fall back to an
        # earlier MAX(trade_date) when the expected session is missing.
        return self.session.scalar(select(MarketIndex.trade_date).where(
            MarketIndex.market == "KOSPI",
            MarketIndex.trade_date == expected,
        ).limit(1))

    def fund_operation_by_idempotency(
        self,
        account_id: UUID,
        key: str,
    ) -> FundOperation | None:
        return self.session.scalar(
            select(FundOperation).where(
                FundOperation.account_id == account_id,
                FundOperation.idempotency_key == key,
            )
        )

    def fund_operation_orders(
        self,
        operation_id: UUID,
    ) -> list[tuple[FundOperationOrder, Order]]:
        rows = self.session.execute(
            select(FundOperationOrder, Order)
            .join(Order, Order.id == FundOperationOrder.order_id)
            .where(FundOperationOrder.fund_operation_id == operation_id)
            .order_by(Order.requested_at, Order.stock_code)
        )
        return [(row[0], row[1]) for row in rows]

    def cash_activity_history(
        self,
        account_id: UUID,
        *,
        limit: int,
        before_created_at: datetime | None = None,
        before_id: int | None = None,
    ) -> list[CashLedger]:
        query = select(CashLedger).where(
            CashLedger.account_id == account_id,
            CashLedger.transaction_type.in_(
                (
                    "BUY",
                    "SELL",
                    "ADDITIONAL_INVESTMENT",
                    "WITHDRAWAL",
                )
            ),
        )
        if before_created_at is not None and before_id is not None:
            query = query.where(
                or_(
                    CashLedger.created_at < before_created_at,
                    (CashLedger.created_at == before_created_at)
                    & (CashLedger.id < before_id),
                )
            )
        return list(
            self.session.scalars(
                query.order_by(
                    CashLedger.created_at.desc(), CashLedger.id.desc()
                ).limit(limit)
            )
        )

    def strategies(self) -> list[Strategy]:
        return list(
            self.session.scalars(
                select(Strategy)
                .where(Strategy.is_active.is_(True))
                .order_by(Strategy.product_group, Strategy.display_order, Strategy.id)
            )
        )

    def strategy(self, strategy_id: str) -> Strategy | None:
        return self.session.get(Strategy, strategy_id)
