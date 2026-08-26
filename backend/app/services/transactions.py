"""계좌 체결 이력을 사용자 화면용 거래내역으로 변환한다."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
import binascii
from datetime import datetime
from decimal import Decimal
import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.repositories import TradingRepository
from app.schemas.api import PortfolioTransactionListResponse, PortfolioTransactionResponse


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
