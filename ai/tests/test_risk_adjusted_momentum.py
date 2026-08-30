from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from inference.risk_adjusted_recommendation_snapshot import (
    build_risk_adjusted_recommendation_snapshot,
)
from inference.generate_risk_adjusted_momentum import v2_data_lineage
from models.risk_adjusted_momentum import (
    RiskAdjustedMomentumConfig,
    RiskAdjustedMomentumModel,
)


TEST_CONFIG = RiskAdjustedMomentumConfig(
    skip_trading_days=2,
    six_month_trading_days=5,
    twelve_month_trading_days=10,
    weekly_volatility_observations=2,
    universe_size=25,
    selection_fraction=0.80,
    min_positions=19,
    max_positions=20,
)


def history(stock_count: int = 25, periods: int = 35) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-02", periods=periods)
    rows = []
    for number in range(stock_count):
        for offset, trade_date in enumerate(dates):
            rows.append(
                {
                    "stock_code": f"S{number:05d}",
                    "stock_name": f"Stock {number}",
                    "trade_date": trade_date,
                    "close_price": 10_000 * (1 + (number + 1) * offset / 10_000),
                    "listed_shares": 1_000_000,
                    "market_cap": (stock_count - number) * 1_000_000_000,
                    "is_tradable": True,
                    "risk_eligible": True,
                }
            )
    return pd.DataFrame(rows)


def test_skip_one_month_momentum_uses_trading_observation_offsets() -> None:
    frame = history(stock_count=1)
    result = RiskAdjustedMomentumModel(TEST_CONFIG).compute_features(frame)
    row = result.iloc[-1]
    close = frame["close_price"].reset_index(drop=True)

    assert row["return_6m_skip1m"] == pytest.approx(close.iloc[-3] / close.iloc[-8] - 1)
    assert row["return_12m_skip1m"] == pytest.approx(close.iloc[-3] / close.iloc[-13] - 1)
    changed_recent = frame.copy()
    changed_recent.loc[changed_recent.index[-1], "close_price"] *= 100
    changed = RiskAdjustedMomentumModel(TEST_CONFIG).compute_features(changed_recent).iloc[-1]
    assert changed["return_6m_skip1m"] == pytest.approx(row["return_6m_skip1m"])
    assert changed["return_12m_skip1m"] == pytest.approx(row["return_12m_skip1m"])


def test_volatility_adjustment_and_neutral_risk_free_policy() -> None:
    result = RiskAdjustedMomentumModel(TEST_CONFIG).compute_features(history(stock_count=1))
    row = result.iloc[-1]

    assert row["volatility_3y_weekly"] > 0
    assert row["risk_adjusted_momentum_6m"] == pytest.approx(
        row["return_6m_skip1m"] / row["volatility_3y_weekly"]
    )
    assert row["risk_free_policy"] == "neutral_no_short_rate_available"


def test_cross_sectional_zscores_are_winsorized_and_ranked() -> None:
    model = RiskAdjustedMomentumModel(TEST_CONFIG)
    features = model.compute_features(history())
    latest = features.loc[features["trade_date"].eq(features["trade_date"].max())]
    ranked = model.rank(latest)

    assert ranked["zscore_6m"].between(-3, 3).all()
    assert ranked["zscore_12m"].between(-3, 3).all()
    assert ranked["combined_z"].between(-3, 3).all()
    assert ranked["momentum_score"].gt(0).all()
    assert ranked.sort_values("rank")["combined_z"].is_monotonic_decreasing
    assert ranked.sort_values("rank")["momentum_score"].is_monotonic_decreasing
    assert int(ranked["selected"].sum()) == 20


def test_insufficient_history_and_corporate_actions_are_adjusted_or_fail_closed() -> None:
    model = RiskAdjustedMomentumModel(TEST_CONFIG)
    short = model.compute_features(history(stock_count=1, periods=8))
    assert not bool(short.iloc[-1]["v2_history_ready"])

    split = history(stock_count=1)
    event_index = split.index[-5]
    split.loc[event_index:, "listed_shares"] = 2_000_000
    split.loc[event_index:, "close_price"] /= 2
    protected = model.compute_features(split)
    assert bool(protected.loc[event_index, "price_adjustment_applied"])
    assert bool(protected.iloc[-1]["corporate_action_safe"])
    assert protected.loc[event_index, "point_in_time_adjusted_close"] == pytest.approx(
        history(stock_count=1).loc[event_index, "close_price"]
    )

    issuance = history(stock_count=1)
    issuance.loc[event_index:, "listed_shares"] = 1_200_000
    issuance_result = model.compute_features(issuance)
    assert bool(issuance_result.loc[event_index, "corporate_action_event_safe"])
    assert not bool(issuance_result.loc[event_index, "price_adjustment_applied"])

    ambiguous = history(stock_count=1)
    ambiguous.loc[event_index:, "listed_shares"] = 2_000_000
    ambiguous.loc[event_index:, "close_price"] /= 4
    rejected = model.compute_features(ambiguous)
    assert not bool(rejected.iloc[-1]["corporate_action_safe"])

    missing = history(stock_count=1)
    missing.loc[missing.index[-5], "listed_shares"] = np.nan
    protected_missing = model.compute_features(missing)
    assert not bool(protected_missing.iloc[-1]["corporate_action_safe"])


def test_risk_filter_and_tradability_are_applied_to_ranking() -> None:
    model = RiskAdjustedMomentumModel(TEST_CONFIG)
    features = model.compute_features(history())
    latest_date = features["trade_date"].max()
    latest = features.loc[features["trade_date"].eq(latest_date)].copy()
    latest.loc[latest.index[0], "risk_eligible"] = False
    latest.loc[latest.index[1], "is_tradable"] = False
    ranked = model.rank(latest)

    assert set(latest.iloc[:2]["stock_code"]).isdisjoint(set(ranked["stock_code"]))


def test_future_rows_cannot_change_an_earlier_decision_cross_section() -> None:
    frame = history()
    cutoff = pd.Timestamp("2026-02-06")
    model = RiskAdjustedMomentumModel(TEST_CONFIG)
    before = model.rank(
        model.compute_features(frame.loc[frame["trade_date"].le(cutoff)])
        .loc[lambda data: data["trade_date"].eq(cutoff)]
    )[["stock_code", "rank", "combined_z"]].reset_index(drop=True)

    changed = frame.copy()
    changed.loc[changed["trade_date"].gt(cutoff), "close_price"] *= 1000
    after = model.rank(
        model.compute_features(changed)
        .loc[lambda data: data["trade_date"].eq(cutoff)]
    )[["stock_code", "rank", "combined_z"]].reset_index(drop=True)

    pd.testing.assert_frame_equal(before, after)


def test_v2_snapshot_is_deterministic_capped_and_exactly_95_percent() -> None:
    frame = history()
    first = build_risk_adjusted_recommendation_snapshot(
        frame,
        data_version="azure-test-v2",
        config=TEST_CONFIG,
        generated_at="2026-03-01T00:00:00+00:00",
    )
    second = build_risk_adjusted_recommendation_snapshot(
        frame,
        data_version="azure-test-v2",
        config=TEST_CONFIG,
        generated_at="2026-03-01T00:00:00+00:00",
    )

    assert first == second
    assert first.model_version == "risk-adjusted-momentum-v2"
    assert first.market_regime == "neutral"
    assert len(first.recommendations) == 20
    assert max(item.target_weight for item in first.recommendations) <= 0.05
    assert sum(
        (Decimal(str(item.target_weight)) for item in first.recommendations),
        Decimal("0"),
    ) == Decimal("0.95")
    assert all("위험조정" in item.reason for item in first.recommendations)
    payload = first.to_dict()
    assert set(payload) == {
        "as_of", "generated_at", "model_version", "data_version", "status",
        "market_regime", "source", "is_stale", "recommendations",
    }
    assert len(payload["recommendations"]) <= 20
    assert set(payload["recommendations"][0]) == {
        "symbol", "stock_name", "score", "rank", "target_weight", "reason",
    }


def test_snapshot_fails_when_5_percent_cap_cannot_reach_95_percent() -> None:
    with pytest.raises(ValueError, match="at least 19"):
        build_risk_adjusted_recommendation_snapshot(
            history(stock_count=18),
            data_version="azure-test-v2",
            config=RiskAdjustedMomentumConfig(
                skip_trading_days=2,
                six_month_trading_days=5,
                twelve_month_trading_days=10,
                weekly_volatility_observations=2,
                universe_size=18,
                selection_fraction=1.0,
                min_positions=18,
                max_positions=18,
            ),
        )


def test_v2_data_lineage_preserves_versions_within_backend_limit() -> None:
    lineage = v2_data_lineage("v2", "2", "v1")

    assert lineage == "model-v2+algo-v2+master-v1+risk-v1+ca-pit-v1+rf-neutral"
    assert len(lineage) <= 100
