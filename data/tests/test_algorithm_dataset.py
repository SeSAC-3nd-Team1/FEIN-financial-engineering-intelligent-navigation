"""Algorithm OHLCV Dataset의 거래 상태 보존 계약을 검증한다."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.build_algorithm_dataset import OUTPUT_COLUMNS, _transform


def _row(**overrides: object) -> dict[str, object]:
    """테스트에 필요한 정상 원천 행을 만든다."""

    row: dict[str, object] = {
        "stock_code": "005930",
        "trade_date": "2026-08-25",
        "open_price": 70000.0,
        "high_price": 71000.0,
        "low_price": 69500.0,
        "close_price": 70500.0,
        "volume": 1000,
    }
    row.update(overrides)
    return row


def test_transform_preserves_non_tradable_row_and_source_prices() -> None:
    """일중 가격 미형성 행은 삭제·보간하지 않고 거래 불가 상태로 보존한다."""

    frame = pd.DataFrame(
        [
            _row(),
            _row(
                trade_date="2026-08-26",
                open_price=0.0,
                high_price=0.0,
                low_price=0.0,
                close_price=70500.0,
                volume=0,
            ),
        ]
    )

    result, stats = _transform(frame, None)

    assert list(result.columns) == OUTPUT_COLUMNS
    assert len(result) == 2
    assert stats == {
        "rows": 2,
        "tradable_rows": 1,
        "non_tradable_rows": 1,
        "reason_NO_INTRADAY_PRICE": 1,
    }
    stopped = result.iloc[1]
    assert stopped["Open"] == 0.0
    assert stopped["High"] == 0.0
    assert stopped["Low"] == 0.0
    assert stopped["Close"] == 70500.0
    assert stopped["Volume"] == 0
    assert bool(stopped["is_tradable"]) is False
    assert stopped["data_status"] == "NOT_TRADABLE"
    assert stopped["quality_reason"] == "NO_INTRADAY_PRICE"


def test_transform_does_not_label_negative_prices_as_no_intraday_price() -> None:
    """음수 OHL은 0값 패턴과 구분해 일반 비양수 가격 사유로 기록한다."""

    result, stats = _transform(
        pd.DataFrame(
            [
                _row(
                    open_price=-1.0,
                    high_price=-1.0,
                    low_price=-1.0,
                )
            ]
        ),
        None,
    )

    assert result.loc[0, "quality_reason"] == "PARTIAL_NON_POSITIVE_OHL"
    assert "reason_NO_INTRADAY_PRICE" not in stats
    assert stats["reason_PARTIAL_NON_POSITIVE_OHL"] == 1


def test_transform_marks_missing_and_invalid_values_without_imputation() -> None:
    """결측·음수 값은 원본 상태로 남기고 복수 사유를 기록한다."""

    frame = pd.DataFrame(
        [
            _row(
                open_price=None,
                close_price=0.0,
                volume=-1,
            )
        ]
    )

    result, stats = _transform(frame, None)

    assert len(result) == 1
    assert pd.isna(result.loc[0, "Open"])
    assert result.loc[0, "Close"] == 0.0
    assert result.loc[0, "Volume"] == -1
    assert result.loc[0, "quality_reason"] == (
        "MISSING_OHLCV;NON_POSITIVE_CLOSE;NEGATIVE_VOLUME"
    )
    assert stats["non_tradable_rows"] == 1
    assert stats["reason_MISSING_OHLCV"] == 1
    assert stats["reason_NON_POSITIVE_CLOSE"] == 1
    assert stats["reason_NEGATIVE_VOLUME"] == 1


def test_transform_rejects_duplicate_natural_key() -> None:
    """동일 종목·날짜 충돌은 임의 제거하지 않고 생성 작업을 실패시킨다."""

    frame = pd.DataFrame([_row(), _row()])

    with pytest.raises(RuntimeError, match="duplicate symbol and Date"):
        _transform(frame, None)


def test_transform_preserves_symbol_leading_zero() -> None:
    """종목코드는 연속형 숫자가 아니므로 선행 0을 유지한다."""

    result, _ = _transform(pd.DataFrame([_row()]), "005930")

    assert result.loc[0, "symbol"] == "005930"
    assert bool(result.loc[0, "is_tradable"]) is True
    assert result.loc[0, "data_status"] == "TRADABLE"
    assert result.loc[0, "quality_reason"] == ""
