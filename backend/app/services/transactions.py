"""계좌 체결 이력을 사용자 화면용 거래내역으로 변환한다."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
import binascii
from datetime import datetime
from decimal import Decimal
import json
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.errors import NotFoundError, ServiceError
from app.models import MarketStock, Order
from app.repositories import TradingRepository
from app.schemas.api import (
    PortfolioActivityListResponse,
    PortfolioActivityResponse,
    PortfolioTransactionListResponse,
    PortfolioTransactionResponse,
)


def encode_transaction_cursor(executed_at: datetime, execution_id: int) -> str:
    payload = json.dumps(
        {"executed_at": executed_at.isoformat(), "id": execution_id},
        separators=(",", ":"),
    ).encode()
    return urlsafe_b64encode(payload).decode().rstrip("=")


def decode_transaction_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(urlsafe_b64decode(cursor + padding))
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("executed_at"), str)
            or not isinstance(payload.get("id"), int)
            or isinstance(payload.get("id"), bool)
        ):
            raise ValueError
        executed_at = datetime.fromisoformat(payload["executed_at"])
        execution_id = payload["id"]
        if executed_at.tzinfo is None or execution_id <= 0:
            raise ValueError
        return executed_at, execution_id
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ServiceError(
            "INVALID_TRANSACTION_CURSOR",
            "거래내역 cursor가 올바르지 않습니다.",
            422,
        ) from exc


class TransactionHistoryService:
    def __init__(self, session: Session) -> None:
        self.repo = TradingRepository(session)

    def list(
        self,
        user_id: int,
        account_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> PortfolioTransactionListResponse:
        if not self.repo.owned_account(account_id, user_id):
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")

        before_executed_at = None
        before_id = None
        if cursor:
            before_executed_at, before_id = decode_transaction_cursor(cursor)
        records = self.repo.execution_history(
            account_id,
            limit=limit + 1,
            before_executed_at=before_executed_at,
            before_id=before_id,
        )
        has_more = len(records) > limit
        page = records[:limit]
        items = [
            PortfolioTransactionResponse(
                id=record.execution.id,
                order_id=record.execution.order_id,
                stock_code=record.execution.stock_code,
                stock_name=record.stock_name,
                side=record.execution.side,
                quantity=record.execution.quantity,
                execution_price=record.execution.execution_price,
                transaction_amount=(
                    record.execution.quantity * record.execution.execution_price
                ).quantize(Decimal("0.01")),
                executed_at=record.execution.executed_at,
            )
            for record in page
        ]
        next_cursor = (
            encode_transaction_cursor(page[-1].execution.executed_at, page[-1].execution.id)
            if has_more and page else None
        )
        return PortfolioTransactionListResponse(
            account_id=account_id,
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
        )


def encode_activity_cursor(created_at: datetime, ledger_id: int) -> str:
    payload = json.dumps(
        {"created_at": created_at.isoformat(), "id": ledger_id},
        separators=(",", ":"),
    ).encode()
    return urlsafe_b64encode(payload).decode().rstrip("=")


def decode_activity_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(urlsafe_b64decode(cursor + padding))
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("created_at"), str)
            or not isinstance(payload.get("id"), int)
            or isinstance(payload.get("id"), bool)
        ):
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        ledger_id = payload["id"]
        if created_at.tzinfo is None or ledger_id <= 0:
            raise ValueError
        return created_at, ledger_id
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ServiceError(
            "INVALID_ACTIVITY_CURSOR",
            "통합 거래내역 cursor가 올바르지 않습니다.",
            422,
        ) from exc


class ActivityHistoryService:
    """가상 현금 원장을 기준으로 매매·추가투자·출금을 한 타임라인으로 반환한다."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = TradingRepository(session)

    def list(
        self,
        user_id: int,
        account_id: UUID,
        *,
        limit: int,
        cursor: str | None,
    ) -> PortfolioActivityListResponse:
        if not self.repo.owned_account(account_id, user_id):
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        before_created_at = None
        before_id = None
        if cursor:
            before_created_at, before_id = decode_activity_cursor(cursor)
        ledgers = self.repo.cash_activity_history(
            account_id,
            limit=limit + 1,
            before_created_at=before_created_at,
            before_id=before_id,
        )
        has_more = len(ledgers) > limit
        page = ledgers[:limit]
        order_ids = []
        for ledger in page:
            if ledger.reference_type != "ORDER":
                continue
            try:
                order_ids.append(UUID(ledger.reference_id))
            except ValueError:
                continue
        order_rows = self.session.execute(
            select(Order, MarketStock.stock_name)
            .outerjoin(MarketStock, MarketStock.stock_code == Order.stock_code)
            .where(Order.id.in_(order_ids))
        ) if order_ids else []
        orders = {row[0].id: (row[0], row[1]) for row in order_rows}

        items = []
        for ledger in page:
            order = None
            stock_name = None
            if ledger.reference_type == "ORDER":
                try:
                    order, stock_name = orders.get(
                        UUID(ledger.reference_id), (None, None)
                    )
                except ValueError:
                    pass
            price = Decimal(order.requested_price) if order and order.requested_price else None
            items.append(
                PortfolioActivityResponse(
                    id=ledger.id,
                    type=ledger.transaction_type,
                    cash_amount=ledger.amount,
                    transaction_amount=abs(Decimal(ledger.amount)),
                    balance_after=ledger.balance_after,
                    reference_id=ledger.reference_id,
                    order_id=order.id if order else None,
                    stock_code=order.stock_code if order else None,
                    stock_name=stock_name,
                    quantity=order.quantity if order else None,
                    execution_price=price,
                    occurred_at=ledger.created_at,
                )
            )
        next_cursor = (
            encode_activity_cursor(page[-1].created_at, page[-1].id)
            if has_more and page
            else None
        )
        return PortfolioActivityListResponse(
            account_id=account_id,
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
        )
