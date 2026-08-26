"""Azure Raw 분석 집계와 시각화 보조 함수의 기본 계약을 검증한다."""

from __future__ import annotations

from pathlib import Path

from scripts.analyze_raw_data import (
    _svg_bar,
    analyze_market_index,
    analyze_stock_price,
)


def test_stock_analysis_preserves_string_codes_and_counts_months() -> None:
    result = analyze_stock_price(
        iter(
            [
                {"basDt": "20260102", "srtnCd": "005930", "clpr": "100", "trqu": "10"},
                {"basDt": "20260105", "srtnCd": "005930", "clpr": "110", "trqu": "20"},
                {"basDt": "bad", "srtnCd": "", "clpr": "0", "trqu": "0"},
            ]
        )
    )

    assert result["rows"] == 2
    assert result["invalid_rows"] == 1
    assert result["unique_stocks"] == 1
    assert result["monthly_rows"] == {"2026-01": 2}
    assert result["close_distribution"]["median"] == 100.0


def test_market_analysis_counts_index_names() -> None:
    result = analyze_market_index(
        iter(
            [
                {"basDt": "20260102", "idxNm": "KOSPI"},
                {"basDt": "20260102", "idxNm": "KOSDAQ"},
            ]
        )
    )

    assert result["rows"] == 2
    assert result["unique_indices"] == 2
    assert result["monthly_rows"] == {"2026-01": 2}


def test_svg_bar_writes_visualization(tmp_path: Path) -> None:
    output = tmp_path / "rows.svg"

    _svg_bar({"2026-01": 3, "2026-02": 5}, "Rows", output)

    assert output.exists()
    assert "2026-01" in output.read_text(encoding="utf-8")
