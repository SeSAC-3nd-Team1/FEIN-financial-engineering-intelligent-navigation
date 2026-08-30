import numpy as np
import pandas as pd
import pytest

from inference.generate_risk_adjusted_momentum import build_v2_feature_history_from_frames
from inference.risk_adjusted_recommendation_snapshot import _capped_score_market_cap_weights
from models.risk_adjusted_momentum import RiskAdjustedMomentumConfig, RiskAdjustedMomentumModel
from risk import apply_stock_risk_filter
from shared.momentum_features import add_momentum_features


def test_live_and_backend_targets_match_on_same_point_in_time_fixture() -> None:
    dates = pd.bdate_range(end="2026-06-30", periods=900)
    symbols = [f"{index:06d}" for index in range(25)]
    rows = []
    for index, symbol in enumerate(symbols):
        steps = np.arange(len(dates))
        close = 2_000.0 * np.exp(
            (0.0001 + index * 0.00001) * steps
            + 0.01 * np.sin(steps / 17.0 + index)
        )
        for day, price in zip(dates, close):
            rows.append(
                {
                    "stock_code": symbol,
                    "trade_date": day,
                    "open_price": price,
                    "high_price": price * 1.01,
                    "low_price": price * 0.99,
                    "close_price": price,
                    "volume": 100_000 + index,
                    "trading_value": price * (100_000 + index),
                    "listed_shares": 10_000_000 + index,
                    "market_cap": price * (10_000_000 + index),
                }
            )
    raw = pd.DataFrame(rows)
    feature_history = add_momentum_features(raw)
    model_frame = feature_history[
        [
            "stock_code", "trade_date", "close_price", "listed_shares",
            "market_cap", "momentum_120d", "trading_value_sma_20d",
            "volatility_60d", "volume_ratio_20d", "history_120d_ready",
        ]
    ].copy()
    # The pure helper receives the canonicalized form produced by the
    # production store loader (symbol/Date are renamed before delegation).
    algorithm_frame = feature_history[["stock_code", "trade_date", "is_tradable"]].copy()
    master = pd.DataFrame({"reference_date": [dates[-1]] * len(symbols), "stock_code": symbols, "stock_name": symbols})
    live = build_v2_feature_history_from_frames(model_frame, algorithm_frame, master)
    backend = apply_stock_risk_filter(feature_history.copy())
    model = RiskAdjustedMomentumModel(
        RiskAdjustedMomentumConfig(weekly_volatility_observations=20)
    )
    live_features = model.compute_features(live)
    backend_features = model.compute_features(backend)
    assert not live_features.empty, (live.shape, live["trade_date"].min(), live["trade_date"].max())
    assert int(live_features["trade_date"].eq(dates[-1]).sum()) == 25, (live_features["trade_date"].min(), live_features["trade_date"].max())
    last_features = live_features.loc[live_features["trade_date"].eq(dates[-1])]
    assert int(last_features["v2_history_ready"].sum()) >= 19
    assert int(last_features["corporate_action_safe"].sum()) >= 19
    live_ranked = model.rank(live_features.loc[lambda data: data["trade_date"].eq(dates[-1])])
    backend_ranked = model.rank(backend_features.loc[lambda data: data["trade_date"].eq(dates[-1])])
    assert int(live_ranked["risk_eligible"].sum()) >= 19
    live_target = _capped_score_market_cap_weights(live_ranked.loc[live_ranked["selected"]])
    backend_target = _capped_score_market_cap_weights(backend_ranked.loc[backend_ranked["selected"]])

    assert set(live_target) == set(backend_target)
    for symbol in live_target:
        assert live_target[symbol] == pytest.approx(backend_target[symbol], abs=1e-8)
