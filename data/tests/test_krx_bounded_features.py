"""KRX bounded Feature가 기존 전량 계산과 같은 시간 분할을 쓰는지 검증한다."""

from __future__ import annotations

import pandas as pd

from features.model_dataset import assign_purged_time_split, compute_stock_features
from scripts.run_krx_history_pipeline import _apply_split_contract, _split_contract


def test_bounded_split_matches_full_frame_contract() -> None:
    """종목 batch가 달라도 전체 거래일 기준 split과 purge 결과는 같아야 한다."""

    dates = pd.date_range("2018-01-01", periods=80, freq="B")
    source = pd.DataFrame({
        "stock_code": [code for code in ("000001", "000002") for _ in dates],
        "trade_date": list(dates) * 2,
        "close_price": list(range(100, 180)) + list(range(200, 280)),
        "volume": [1_000] * (len(dates) * 2),
    })
    feature = compute_stock_features(source)
    expected, expected_split = assign_purged_time_split(feature)
    split = _split_contract(dates.tolist())

    actual_parts = [
        _apply_split_contract(feature.loc[feature["stock_code"] == code], split)
        for code in ("000001", "000002")
    ]
    actual = pd.concat(actual_parts).sort_index()

    assert split == expected_split
    columns = ["split", "eligible_target_5d", "eligible_target_20d"]
    pd.testing.assert_frame_equal(actual[columns], expected[columns])
