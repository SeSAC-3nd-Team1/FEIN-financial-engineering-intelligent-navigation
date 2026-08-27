import json
from pathlib import Path

import pandas as pd
import pytest

from inference.recommendation_snapshot import (
    build_recommendation_snapshot,
    export_recommendation_snapshot,
)


def feature_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": ["2026-08-25"] * 5 + ["2026-08-26"] * 5,
            "stock_code": ["A", "B", "C", "D", "E"] * 2,
            "market_cap": [500, 400, 300, 200, 100] * 2,
            "momentum_120d": [0.9, 0.8, 0.7, 0.6, 0.5, 0.1, 0.5, 0.4, 0.3, 0.9],
            "is_tradable": [True] * 9 + [False],
            "risk_eligible": [
                True,
                True,
                True,
                True,
                True,
                True,
                True,
                False,
                True,
                True,
            ],
        }
    )


def test_snapshot_uses_latest_date_and_excludes_ineligible_stocks() -> None:
    snapshot = build_recommendation_snapshot(
        feature_frame(), data_version="algorithm-ohlcv-v2", top_n=3
    )

    assert snapshot.as_of == "2026-08-26"
    assert snapshot.model_version == "price-momentum-v1"
    assert [item.symbol for item in snapshot.recommendations] == ["B", "D", "A"]
    assert sum(
        item.target_weight for item in snapshot.recommendations
    ) == pytest.approx(0.95)
    assert snapshot.to_dict()["status"] == "ready"


def test_snapshot_export_writes_generator_result(tmp_path: Path) -> None:
    output_path = tmp_path / "model_recommendation_snapshot.json"

    snapshot = export_recommendation_snapshot(
        feature_frame(),
        output_path,
        data_version="algorithm-ohlcv-v2",
        top_n=3,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload == json.loads(json.dumps(snapshot.to_dict()))
    assert sum(
        item["target_weight"] for item in payload["recommendations"]
    ) == pytest.approx(0.95)
    assert list(tmp_path.glob("*.tmp")) == []


def test_snapshot_requires_explicit_eligibility_columns() -> None:
    frame = feature_frame().drop(columns="risk_eligible")

    with pytest.raises(ValueError, match="eligibility columns missing"):
        build_recommendation_snapshot(frame, data_version="algorithm-ohlcv-v2")


def test_snapshot_rejects_latest_date_without_tradable_rows() -> None:
    frame = feature_frame()
    frame.loc[frame["trade_date"].eq("2026-08-26"), "is_tradable"] = False

    with pytest.raises(ValueError, match="no eligible stocks"):
        build_recommendation_snapshot(frame, data_version="algorithm-ohlcv-v2")
