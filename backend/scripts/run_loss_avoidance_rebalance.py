"""활성 AUTO 물림방지 계좌의 최신 fix2 목표를 내부 DB에 반영한다."""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import VirtualAccount
from app.services.loss_avoidance_investment import LossAvoidanceInvestmentService


LOGGER = logging.getLogger("loss_avoidance_rebalance")


def main() -> int:
    """모든 AUTO 물림방지 계좌를 멱등적으로 리밸런싱한다."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    failures = 0
    with SessionLocal() as session:
        accounts = session.scalars(
            select(VirtualAccount).where(
                VirtualAccount.operation_mode == "AUTO",
                VirtualAccount.status == "ACTIVE",
                VirtualAccount.selected_strategy_id == "low",
            )
        ).all()
        LOGGER.info("found %d active loss-avoidance AUTO accounts", len(accounts))
        for account in accounts:
            try:
                result = LossAvoidanceInvestmentService(session).rebalance(
                    account.user_id, account.id
                )
                LOGGER.info(
                    "account=%s status=%s orders_created=%s",
                    account.id,
                    result.status,
                    result.orders_created,
                )
            except Exception:
                failures += 1
                LOGGER.exception("loss-avoidance rebalance failed account=%s", account.id)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
