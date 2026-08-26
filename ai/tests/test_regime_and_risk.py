import pandas as pd
import pytest

from models.regime import RuleBasedRegimeModel
from risk.portfolio import PortfolioConstraints, construct_portfolio
from risk.stock_filter import StockRiskConfig, apply_stock_risk_filter


def test_rule_regime_covers_risk_on_off_and_warmup() -> None:
    frame = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "index_above_sma_20d": [True, False, True],
        "index_momentum_20d": [0.1, -0.1, None],
        "index_volatility_20d": [0.1, 0.3, None],
    })
    assert RuleBasedRegimeModel().predict(frame)["regime"].tolist() == [
        "risk_on", "risk_off", "neutral"
    ]


def test_stock_filter_keeps_rejection_reason_for_audit() -> None:
    frame = pd.DataFrame({
        "stock_code": ["A", "B"],
        "trade_date": ["2026-01-02"] * 2,
        "close_price": [20_000, 500],
        "market_cap": [1_000, 1_000],
        "trading_value_sma_20d": [100, 1],
        "volatility_60d": [0.2, 1.2],
        "volume_ratio_20d": [1.0, 20.0],
        "history_120d_ready": [True, False],
    })
    result = apply_stock_risk_filter(frame, StockRiskConfig(min_trading_value_20d=10))
    assert bool(result.loc[0, "risk_eligible"])
    assert not bool(result.loc[1, "risk_eligible"])
    assert "price" in result.loc[1, "risk_reason"]


def test_portfolio_enforces_position_weight_and_turnover() -> None:
    candidates = pd.DataFrame({
        "stock_code": [f"S{i}" for i in range(10)],
        "score": list(reversed(range(10))),
        "risk_eligible": [True] * 10,
    })
    constraints = PortfolioConstraints(max_positions=10, max_weight=0.15, cash_buffer=0.05, max_turnover=0.30)
    current = pd.Series({f"OLD{i}": 0.095 for i in range(10)})
    portfolio = construct_portfolio(
        candidates,
        current_weights=current,
        constraints=constraints,
    )
    assert portfolio["weight"].max() <= 0.15
    aligned = portfolio.set_index("stock_code")["weight"].reindex(
        current.index.union(candidates["stock_code"]), fill_value=0.0
    )
    turnover = (aligned - current.reindex(aligned.index, fill_value=0.0)).abs().sum() / 2
    assert turnover == pytest.approx(0.30)
