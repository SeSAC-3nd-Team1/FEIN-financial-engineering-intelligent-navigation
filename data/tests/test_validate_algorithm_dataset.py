"""Algorithm Dataset 전달 검증기의 계약 검사를 검증한다."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.validate_algorithm_dataset import validate_frame


def _frame() -> pd.DataFrame:
    """정상행과 거래 불가행을 포함한 최소 전달 Dataset을 만든다."""

    return pd.DataFrame(
        {
            "symbol": pd.Series(["005930", "005930"], dtype="string"),
            "Date": pd.to_datetime(["2026-08-24", "2026-08-25"]),
            "Open": [70000.0, 0.0],
            "High": [71000.0, 0.0],
            "Low": [69500.0, 0.0],
            "Close": [70500.0, 70500.0],
            "Volume": [1000, 0],
            "is_tradable": [True, False],
            "data_status": ["TRADABLE", "NOT_TRADABLE"],
            "quality_reason": ["", "NO_INTRADAY_PRICE"],
        }
    )


def test_validate_frame_accepts_status_preserving_contract() -> None:
    """원천 행과 거래 상태가 일치하면 집계 결과를 반환한다."""

    result = validate_frame(_frame(), "sample.parquet")

    assert result["rows"] == 2
    assert result["tradable_rows"] == 1
    assert result["non_tradable_rows"] == 1
    assert result["reason_counts"] == {"NO_INTRADAY_PRICE": 1}
    assert result["symbols"] == {"005930"}


def test_validate_frame_rejects_status_mismatch() -> None:
    """거래 가능 flag와 상태 문자열의 불일치는 전달 전에 실패해야 한다."""

    frame = _frame()
    frame.loc[1, "data_status"] = "TRADABLE"

    with pytest.raises(RuntimeError, match="data_status mismatch"):
        validate_frame(frame, "sample.parquet")


def test_validate_frame_rejects_duplicate_key() -> None:
    """동일 종목·날짜 중복은 Algorithm에서 임의 처리하지 않도록 차단한다."""

    frame = pd.concat([_frame().iloc[[0]], _frame().iloc[[0]]], ignore_index=True)

    with pytest.raises(RuntimeError, match="duplicate symbol and Date"):
        validate_frame(frame, "sample.parquet")
