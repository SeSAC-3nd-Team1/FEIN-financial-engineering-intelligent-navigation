from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from inference.loss_avoidance_snapshot import (
    build_loss_avoidance_snapshot,
    load_algorithm_v23,
)


class FakeAlgorithm:
    class Config:
        pass

    @staticmethod
    def run_backtest(history, _config):
        symbol_score = float(history.iloc[-1]["Close"]) / 100
        decisions = pd.DataFrame(
            [
                {
                    "target_weight": 0.70 if symbol_score > 1 else 0.35,
                    "forecast_variance": 0.04,
                    "mu_net": symbol_score,
                    "engine_regime": "bull",
                    "risk_reason": "OK",
                }
            ],
            index=[pd.Timestamp(history.iloc[-1]["Date"])],
        )
        return SimpleNamespace(decisions=decisions)


def input_frame() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=260, freq="D")
    rows = []
    for symbol, close, volume in (("005930", 200.0, 1000), ("000660", 100.0, 2000)):
        rows.extend(
            {
                "symbol": symbol,
                "Date": day,
                "Open": close,
                "High": close + 1,
                "Low": close - 1,
                "Close": close,
                "Volume": volume,
                "is_tradable": True,
            }
            for day in dates
        )
    return pd.DataFrame(rows)


def test_algorithm_snapshot_uses_engine_outputs_and_preserves_exposure() -> None:
    snapshot = build_loss_avoidance_snapshot(
        input_frame(),
        algorithm=FakeAlgorithm(),  # type: ignore[arg-type]
        data_version="algorithm_ohlcv-v2",
        top_n=2,
        universe_size=2,
    )

    assert snapshot.model_version == "algorithm-v2.3"
    assert snapshot.source == "generated"
    assert [item.symbol for item in snapshot.recommendations] == ["005930", "000660"]
    assert sum(item.target_weight for item in snapshot.recommendations) == 0.7
    assert all("Algorithm(ver.2.3)" in item.reason for item in snapshot.recommendations)


def test_team_algorithm_source_is_loaded_without_copying() -> None:
    source = Path(__file__).resolve().parents[2] / "output" / "Algorithm(ver.2.3).py"

    algorithm = load_algorithm_v23(source)

    assert algorithm.Config().min_train_rows == 252
    assert callable(algorithm.run_backtest)
