"""Run the selected model's rebalance for every active AUTO account."""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app.core.errors import ServiceError
from app.db.session import SessionLocal
from app.models import VirtualAccount
from app.services.loss_avoidance_investment import LossAvoidanceInvestmentService
from app.services.momentum_investment import MomentumInvestmentService


LOGGER = logging.getLogger("auto_model_rebalance")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", choices=("momentum", "low"), required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    service_type = (
        MomentumInvestmentService if args.strategy == "momentum" else LossAvoidanceInvestmentService
    )
    failures = 0
    skipped = 0
    with SessionLocal() as session:
        accounts = session.scalars(
            select(VirtualAccount).where(
                VirtualAccount.operation_mode == "AUTO",
                VirtualAccount.status == "ACTIVE",
                VirtualAccount.selected_strategy_id == args.strategy,
            )
        ).all()
        LOGGER.info("strategy=%s active_auto_accounts=%d", args.strategy, len(accounts))
        for account in accounts:
            try:
                result = service_type(session).rebalance(account.user_id, account.id)
                LOGGER.info(
                    "strategy=%s account=%s status=%s orders_created=%s",
                    args.strategy,
                    account.id,
                    result.status,
                    result.orders_created,
                )
            except ServiceError as exc:
                # Momentum is intentionally checked every market day so the same
                # runner works for both models; it is a no-op until the official
                # quarter-end snapshot is available.
                if (
                    args.strategy == "momentum"
                    and exc.code == "MOMENTUM_QUARTER_END_SNAPSHOT_REQUIRED"
                ):
                    skipped += 1
                    LOGGER.info("strategy=momentum account=%s skipped: %s", account.id, exc.message)
                    continue
                failures += 1
                LOGGER.exception("strategy=%s account=%s failed", args.strategy, account.id)
            except Exception:
                failures += 1
                LOGGER.exception("strategy=%s account=%s failed", args.strategy, account.id)
    LOGGER.info("strategy=%s completed skipped=%d failures=%d", args.strategy, skipped, failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
