"""최종 모델 학습 Dataset의 날짜 결합과 컬럼 계약을 검증한다."""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.build_final_model_dataset import join_daily_features


def _stock() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "stock_code": ["000001", "000001"],
            "trade_date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
            "close_price": [100.0, 101.0],
            "target_return_5d": [0.1, None],
        }
    )


def test_join_preserves_natural_key_and_missing_values() -> None:
    """시장·거시 결측은 0이 아니라 결측으로 남고 가격 행 수가 유지되어야 한다."""

    market = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-01-02"]),
            "index_code": ["KOSPI:KOSPI:KOSPI"],
            "index_name": ["KOSPI"],
            "close_index": [2500.0],
        }
    )
    macro = pd.DataFrame(
        {"date": pd.to_datetime(["2026-01-02"]), "usd_krw": [1450.0]}
    )

    result = join_daily_features(_stock(), market, macro)

    assert len(result) == 2
    assert result[["stock_code", "trade_date"]].duplicated().sum() == 0
    assert result.loc[1, "market_kospi_kospi_kospi_close_index"] != 0
    assert pd.isna(result.loc[1, "market_kospi_kospi_kospi_close_index"])
    assert pd.isna(result.loc[1, "usd_krw"])
    assert "target_return_5d" in result


def test_join_rejects_duplicate_market_key() -> None:
    """동일 지수·거래일 충돌은 임의 선택하지 않고 실패해야 한다."""

    market = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2026-01-02", "2026-01-02"]),
            "index_code": ["KOSPI", "KOSPI"],
            "index_name": ["KOSPI", "KOSPI"],
            "close_index": [2500.0, 2501.0],
        }
    )
    with pytest.raises(ValueError, match="duplicate market feature"):
        join_daily_features(_stock(), market, pd.DataFrame({"date": pd.to_datetime([])}))
