"""Build Backend-compatible risk-adjusted momentum v2 snapshots."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
import json
import os
from pathlib import Path
import tempfile

import pandas as pd

from inference.recommendation_snapshot import RecommendationItem, RecommendationSnapshot
from models.risk_adjusted_momentum import (
    RiskAdjustedMomentumConfig,
    RiskAdjustedMomentumModel,
)

TARGET_STOCK_WEIGHT = Decimal("0.95000000")
MAX_POSITION_WEIGHT = Decimal("0.05000000")
WEIGHT_QUANTUM = Decimal("0.00000001")


def _capped_score_market_cap_weights(selected: pd.DataFrame) -> dict[str, Decimal]:
    """Apply iterative 5% caps and serialize weights to an exact 95% Decimal sum."""

    if len(selected) * MAX_POSITION_WEIGHT < TARGET_STOCK_WEIGHT:
        raise ValueError("at least 19 selected stocks are required by the 5% cap and 95% target")
    raw = {
        str(row.stock_code): Decimal(str(float(row.market_cap)))
        * Decimal(str(float(row.momentum_score)))
        for row in selected.itertuples(index=False)
    }
    if any(value <= 0 for value in raw.values()):
        raise ValueError("selected market-cap momentum weights must be positive")

    weights: dict[str, Decimal] = {}
    active = dict(raw)
    remaining = TARGET_STOCK_WEIGHT
    while active:
        total_raw = sum(active.values(), Decimal("0"))
        proposed = {
            symbol: remaining * value / total_raw for symbol, value in active.items()
        }
        capped = [
            symbol for symbol, weight in proposed.items() if weight > MAX_POSITION_WEIGHT
        ]
        if not capped:
            weights.update(proposed)
            break
        for symbol in capped:
            weights[symbol] = MAX_POSITION_WEIGHT
            remaining -= MAX_POSITION_WEIGHT
            active.pop(symbol)
        if remaining < 0 or len(active) * MAX_POSITION_WEIGHT < remaining:
            raise RuntimeError("position cap redistribution became infeasible")

    quantized = {
        symbol: weight.quantize(WEIGHT_QUANTUM, rounding=ROUND_DOWN)
        for symbol, weight in weights.items()
    }
    residual_units = int(
        (TARGET_STOCK_WEIGHT - sum(quantized.values(), Decimal("0"))) / WEIGHT_QUANTUM
    )
    order = selected.sort_values(["rank", "stock_code"])["stock_code"].astype(str).tolist()
    for symbol in order:
        if residual_units <= 0:
            break
        if quantized[symbol] + WEIGHT_QUANTUM <= MAX_POSITION_WEIGHT:
            quantized[symbol] += WEIGHT_QUANTUM
            residual_units -= 1
    if residual_units or sum(quantized.values(), Decimal("0")) != TARGET_STOCK_WEIGHT:
        raise RuntimeError("could not serialize an exact 0.95 capped portfolio")
    return quantized


def build_risk_adjusted_recommendation_snapshot(
    frame: pd.DataFrame,
    *,
    data_version: str,
    market_regime: str = "neutral",
    config: RiskAdjustedMomentumConfig = RiskAdjustedMomentumConfig(),
    generated_at: str | None = None,
) -> RecommendationSnapshot:
    """Rank the latest point-in-time cross-section and preserve the v1 service contract."""

    if frame.empty:
        raise ValueError("feature frame cannot be empty")
    model = RiskAdjustedMomentumModel(config)
    features = model.compute_features(frame)
    latest_date = features["trade_date"].max()
    ranked = model.rank(features.loc[features["trade_date"].eq(latest_date)].copy())
    selected = ranked.loc[ranked["selected"]].copy()
    if len(selected) < config.min_positions:
        raise ValueError(
            f"latest eligible universe produced only {len(selected)} selections; "
            f"at least {config.min_positions} are required"
        )
    weights = _capped_score_market_cap_weights(selected)
    selected = selected.loc[
        selected["stock_code"].astype(str).map(weights).gt(0)
    ].copy()
    if len(selected) < config.min_positions:
        raise ValueError("capped weighting produced too few positive positions")
    items = tuple(
        RecommendationItem(
            symbol=str(row.stock_code),
            stock_name=str(row.stock_name) if hasattr(row, "stock_name") and pd.notna(row.stock_name) else None,
            score=round(float(row.momentum_score), 8),
            rank=int(row.rank),
            target_weight=float(weights[str(row.stock_code)]),
            reason="6개월·12개월 위험조정 모멘텀 상위 종목",
        )
        for row in selected.sort_values(["rank", "stock_code"]).itertuples(index=False)
    )
    if sum((Decimal(str(item.target_weight)) for item in items), Decimal("0")) != Decimal("0.95"):
        raise RuntimeError("serialized target weights must sum exactly to 0.95")

    if generated_at is None:
        from datetime import datetime, timezone

        generated_at = datetime.now(timezone.utc).isoformat()
    return RecommendationSnapshot(
        as_of=pd.Timestamp(latest_date).date().isoformat(),
        generated_at=generated_at,
        model_version=RiskAdjustedMomentumModel.MODEL_VERSION,
        data_version=data_version,
        status="ready",
        # 서비스 계약용 필드이며 v2가 별도 regime 예측을 수행했다는 뜻이 아니다.
        market_regime=market_regime,
        source="generated",
        is_stale=False,
        recommendations=items,
    )


def export_risk_adjusted_recommendation_snapshot(
    frame: pd.DataFrame,
    output_path: str | Path,
    *,
    data_version: str,
    market_regime: str = "neutral",
    config: RiskAdjustedMomentumConfig = RiskAdjustedMomentumConfig(),
) -> RecommendationSnapshot:
    """Atomically publish v2 without changing the v1 artifact path or builder."""

    snapshot = build_risk_adjusted_recommendation_snapshot(
        frame,
        data_version=data_version,
        market_regime=market_regime,
        config=config,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return snapshot
