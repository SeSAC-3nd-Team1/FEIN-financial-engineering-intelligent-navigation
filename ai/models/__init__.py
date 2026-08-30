"""Trainable models and deterministic model baselines."""

from models.regime import MarketRegime, RegimeConfig, RuleBasedRegimeModel
from models.risk_adjusted_momentum import (
    RiskAdjustedMomentumConfig,
    RiskAdjustedMomentumModel,
)
from models.rule_rankers import LowVolatilityRanker, MomentumRanker, RuleSelectionConfig

# The service imports the deterministic v2 factor from this package.  Keep the
# optional LightGBM training dependency out of that runtime path.
try:
    from models.ml_rankers import LightGBMStockRanker, RankerConfig, RidgeStockRanker
except ModuleNotFoundError as exc:
    if exc.name != "lightgbm":
        raise
    LightGBMStockRanker = RankerConfig = RidgeStockRanker = None  # type: ignore[assignment]

__all__ = [
    "LowVolatilityRanker",
    "MarketRegime",
    "MomentumRanker",
    "RegimeConfig",
    "RiskAdjustedMomentumConfig",
    "RiskAdjustedMomentumModel",
    "RuleBasedRegimeModel",
    "RuleSelectionConfig",
]

if LightGBMStockRanker is not None:
    __all__.extend(["LightGBMStockRanker", "RankerConfig", "RidgeStockRanker"])
