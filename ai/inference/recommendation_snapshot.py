"""Build a deployable price-based recommendation snapshot for the MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import pandas as pd

from models.rule_rankers import MomentumRanker, RuleSelectionConfig
from risk.portfolio import PortfolioConstraints, construct_portfolio


@dataclass(frozen=True)
class RecommendationItem:
    symbol: str
    score: float
    rank: int
    target_weight: float
    reason: str


@dataclass(frozen=True)
class RecommendationSnapshot:
    as_of: str
    model_version: str
    data_version: str
    status: str
    market_regime: str
    recommendations: tuple[RecommendationItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_recommendation_snapshot(
    frame: pd.DataFrame,
    *,
    data_version: str,
    market_regime: str = "neutral",
    top_n: int = 5,
) -> RecommendationSnapshot:
    """Rank the latest tradable cross-section and assign constrained equal weights."""

    if frame.empty:
        raise ValueError("feature frame cannot be empty")
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="raise")
    latest_date = data["trade_date"].max()
    data = data.loc[data["trade_date"].eq(latest_date)].copy()
    if "is_tradable" in data:
        data = data.loc[data["is_tradable"].fillna(False).astype(bool)]
    if "risk_eligible" in data:
        data = data.loc[data["risk_eligible"].fillna(False).astype(bool)]
    if data.empty:
        raise ValueError("no eligible stocks are available on the latest date")

    universe_size = max(top_n, len(data))
    ranked = MomentumRanker(
        RuleSelectionConfig(top_n=min(top_n, len(data)), universe_size=universe_size)
    ).rank(data)
    selected = ranked.loc[ranked["selected"]].copy()
    portfolio = construct_portfolio(
        selected,
        constraints=PortfolioConstraints(
            max_positions=min(top_n, len(selected)),
            max_weight=max(0.2, 1 / max(1, min(top_n, len(selected)))),
            cash_buffer=0.05,
            max_turnover=1.0,
        ),
    )
    weights = portfolio.set_index("stock_code")["weight"].to_dict()
    items = tuple(
        RecommendationItem(
            symbol=str(row.stock_code),
            score=round(float(row.score), 8),
            rank=int(row.rank),
            target_weight=round(float(weights.get(str(row.stock_code), 0.0)), 8),
            reason="120일 가격 모멘텀 상위 종목",
        )
        for row in selected.sort_values("rank").itertuples(index=False)
    )
    if not items:
        raise ValueError("recommendation snapshot cannot be empty")
    return RecommendationSnapshot(
        as_of=(
            latest_date.date().isoformat()
            if isinstance(latest_date, pd.Timestamp)
            else date.fromisoformat(str(latest_date)).isoformat()
        ),
        model_version="price-momentum-v1",
        data_version=data_version,
        status="ready",
        market_regime=market_regime,
        recommendations=items,
    )
