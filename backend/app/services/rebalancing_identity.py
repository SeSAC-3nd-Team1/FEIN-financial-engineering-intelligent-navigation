"""Canonical identity for a server-generated rebalancing proposal."""

from decimal import Decimal
from datetime import date


def proposal_key(
    strategy_id: str | None,
    stock_code: str,
    action: str,
    current_weight: Decimal,
    target_weight: Decimal,
    weight_diff: Decimal,
    recommended_amount: Decimal,
    baseline_date: date,
) -> str:
    return "|".join(
        (
            str(strategy_id or ""),
            stock_code,
            action,
            str(current_weight),
            str(target_weight),
            str(weight_diff),
            str(recommended_amount),
            baseline_date.isoformat(),
        )
    )
