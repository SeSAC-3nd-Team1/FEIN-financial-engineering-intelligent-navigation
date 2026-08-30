"""Azure Blob canonical Raw를 스트리밍 분석하고 재현 가능한 시각화 산출물을 만든다."""

from __future__ import annotations

import argparse
import gzip
import html
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

from storage import BlobStorage

DATASETS = ("stock_price", "market_index", "financial_statement")


def _payloads(
    storage: BlobStorage, container: str, dataset: str
) -> Iterable[dict[str, Any]]:
    """dataset의 canonical JSONL.gz를 한 Blob씩 읽어 payload만 순회한다."""

    prefix = f"data-go-kr/{dataset}/"
    for path in storage.list_paths(container, prefix=prefix):
        if not path.endswith(".jsonl.gz"):
            continue
        for line in gzip.decompress(
            storage.download_bytes(container, path)
        ).splitlines():
            if not line.strip():
                continue
            envelope = json.loads(line)
            payload = envelope.get("payload")
            if isinstance(payload, dict):
                yield payload


def _number(value: Any) -> float | None:
    """쉼표가 포함된 공공 API 숫자 문자열을 유한 실수로 변환한다."""

    if value is None or str(value).strip() == "":
        return None
    try:
        result = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    return result if result == result and abs(result) != float("inf") else None


def _date(value: Any) -> str | None:
    """YYYYMMDD 또는 ISO 날짜를 정규화한다."""

    text = str(value or "").strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _month(value: Any) -> str | None:
    parsed = _date(value)
    return parsed[:7] if parsed else None


def _quantiles(values: list[float]) -> dict[str, float | None]:
    """분포 시각화에 필요한 다섯 수치만 계산한다."""

    if not values:
        return {key: None for key in ("min", "p25", "median", "p75", "max")}
    ordered = sorted(values)

    def pick(ratio: float) -> float:
        return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * ratio))]

    return {
        "min": ordered[0],
        "p25": pick(0.25),
        "median": pick(0.5),
        "p75": pick(0.75),
        "max": ordered[-1],
    }


def analyze_stock_price(payloads: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """주가 Raw의 coverage, 종목 universe, 가격·거래량 분포를 집계한다."""

    months: Counter[str] = Counter()
    stocks: set[str] = set()
    close_values: list[float] = []
    volume_values: list[float] = []
    monthly_rows: Counter[str] = Counter()
    daily_rows: Counter[str] = Counter()
    invalid_rows = 0
    for payload in payloads:
        trade_date = _date(payload.get("basDt"))
        close = _number(payload.get("clpr"))
        volume = _number(payload.get("trqu"))
        code = str(payload.get("srtnCd") or "").strip()
        if not trade_date or not code:
            invalid_rows += 1
            continue
        month = trade_date[:7]
        months[month] += 1
        monthly_rows[month] += 1
        daily_rows[trade_date] += 1
        stocks.add(code)
        if close is not None:
            close_values.append(close)
        if volume is not None:
            volume_values.append(volume)
    return {
        "rows": sum(months.values()),
        "invalid_rows": invalid_rows,
        "min_date": min(months) if months else None,
        "max_date": max(months) if months else None,
        "unique_stocks": len(stocks),
        "monthly_rows": dict(sorted(monthly_rows.items())),
        "daily_rows": dict(sorted(daily_rows.items())),
        "close_distribution": _quantiles(close_values),
        "volume_distribution": _quantiles(volume_values),
    }


def analyze_market_index(payloads: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """시장지수별 관측 범위와 일별 지수 개수를 집계한다."""

    indices: Counter[str] = Counter()
    months: Counter[str] = Counter()
    for payload in payloads:
        date = _date(payload.get("basDt"))
        name = str(payload.get("idxNm") or payload.get("idxNmEng") or "unknown").strip()
        if date:
            months[date[:7]] += 1
            indices[name] += 1
    return {
        "rows": sum(indices.values()),
        "unique_indices": len(indices),
        "index_rows": indices.most_common(20),
        "monthly_rows": dict(sorted(months.items())),
    }


def analyze_financial(payloads: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """재무 Raw의 기준일 범위와 주요 재무 필드 결측 구조를 집계한다.

    이 API의 실제 기준일 필드는 ``basDt``이며 ``baseDate``로 추정하면 기간이
    비어 있는 것처럼 보이므로, Raw schema에 존재하는 이름을 그대로 사용한다.
    """

    rows = 0
    dates: list[str] = []
    field_presence: Counter[str] = Counter()
    for payload in payloads:
        rows += 1
        parsed = _date(payload.get("basDt"))
        if parsed:
            dates.append(parsed)
        for field in ("fnclDcdNm", "thstrmAmount", "frmtrmAmount", "accountNm"):
            if str(payload.get(field) or "").strip():
                field_presence[field] += 1
    return {
        "rows": rows,
        "min_base_date": min(dates) if dates else None,
        "max_base_date": max(dates) if dates else None,
        "field_presence": dict(field_presence),
    }


def _svg_bar(values: dict[str, int], title: str, output: Path) -> None:
    """외부 시각화 패키지 없이 월별 건수 막대그래프 SVG를 생성한다."""

    items = list(values.items())
    width, height = 1200, 520
    max_value = max(values.values(), default=1)
    bar_width = max(4, (width - 100) / max(1, len(items)))
    bars = []
    for index, (label, value) in enumerate(items):
        x = 50 + index * bar_width
        bar_height = 380 * value / max_value
        y = 430 - bar_height
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(2, bar_width-1):.1f}" height="{bar_height:.1f}" fill="#2563eb"><title>{html.escape(label)}: {value:,}</title></rect>'
        )
        if len(items) <= 36 or index % max(1, len(items) // 18) == 0:
            bars.append(
                f'<text x="{x:.1f}" y="455" font-size="11" transform="rotate(45 {x:.1f} 455)">{html.escape(label)}</text>'
            )
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="white"/><text x="50" y="35" font-size="22" font-weight="bold">{html.escape(title)}</text><line x1="50" y1="430" x2="1150" y2="430" stroke="#333"/>{"".join(bars)}</svg>'
    output.write_text(svg, encoding="utf-8")


def render_markdown(result: dict[str, Any]) -> str:
    """집계 결과를 인사이트 중심의 Markdown 보고서로 렌더링한다."""

    stock = result.get("stock_price", {})
    market = result.get("market_index", {})
    financial = result.get("financial_statement", {})
    monthly = stock.get("monthly_rows", {})
    peak_month = max(monthly, key=monthly.get) if monthly else None
    lines = [
        "# Azure Raw 금융 데이터 분석 결과",
        "",
        f"- 생성 시각: `{result['generated_at']}`",
        "- 원본: Azure Blob canonical Raw",
        "",
        "## 핵심 인사이트",
        "",
        f"1. 주가 Raw는 `{stock.get('min_date')}` ~ `{stock.get('max_date')}` 월 범위이며 관측 종목 수는 **{stock.get('unique_stocks', 0):,}개**다.",
        (
            f"2. 주가 행이 가장 많은 월은 `{peak_month}` (**{monthly.get(peak_month, 0):,}건**)이다."
            if peak_month
            else "2. 주가 월별 건수를 계산할 수 없다."
        ),
        f"3. 시장지수 Raw는 **{market.get('unique_indices', 0):,}개** 지수명을 포함한다.",
        "4. 재무 `basDt`는 기준일일 뿐 실제 공시 가능일이 아니므로 가격과 직접 결합해 인과적 모델 입력으로 사용하면 안 된다.",
        "",
        "## 데이터 품질 및 해석 한계",
        "",
        "- Raw는 분석 중 수정하지 않았으며 빈 값은 0으로 대체하지 않았다.",
        "- 주가 관측 종목 수는 기간별 Universe 변화와 survivorship bias의 영향을 받을 수 있다.",
        "- 재무 `basDt`는 관측 기준일이지 재무정보의 실제 공개일을 의미하지 않는다.",
        "- 분포는 극단값 영향을 받으므로 평균 대신 분위수로 요약했다.",
        "",
        "## 집계 요약",
        "",
        "| dataset | rows | date/base_date range | 주요 지표 |",
        "|---|---:|---|---|",
        f"| stock_price | {stock.get('rows', 0):,} | {stock.get('min_date')} ~ {stock.get('max_date')} | stocks={stock.get('unique_stocks', 0):,} |",
        f"| market_index | {market.get('rows', 0):,} | monthly coverage | indices={market.get('unique_indices', 0):,} |",
        f"| financial_statement | {financial.get('rows', 0):,} | {financial.get('min_base_date')} ~ {financial.get('max_base_date')} | fields={len(financial.get('field_presence', {}))} |",
        "",
        "## 시각화",
        "",
        "- `stock_price_monthly_rows.svg`: 주가 월별 관측 건수",
        "- `market_index_monthly_rows.svg`: 시장지수 월별 관측 건수",
    ]
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Azure canonical Raw datasets")
    parser.add_argument("--dataset", action="append", choices=DATASETS)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/raw-analysis"))
    parser.add_argument("--env-file", type=Path)
    return parser.parse_args()


def main() -> None:
    """Azure Raw를 분석하고 보고서·SVG 시각화를 로컬에 생성한다."""

    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    selected = args.dataset or list(DATASETS)
    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "container": container,
        "datasets": selected,
    }
    analyzers = {
        "stock_price": analyze_stock_price,
        "market_index": analyze_market_index,
        "financial_statement": analyze_financial,
    }
    for dataset in selected:
        print(f"RAW ANALYSIS START dataset={dataset}")
        result[dataset] = analyzers[dataset](_payloads(storage, container, dataset))
        print(
            f"RAW ANALYSIS COMPLETE dataset={dataset} rows={result[dataset]['rows']:,}"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "analysis.md").write_text(
        render_markdown(result), encoding="utf-8"
    )
    if "stock_price" in result:
        _svg_bar(
            result["stock_price"]["monthly_rows"],
            "Stock price Raw rows by month",
            args.output_dir / "stock_price_monthly_rows.svg",
        )
    if "market_index" in result:
        _svg_bar(
            result["market_index"]["monthly_rows"],
            "Market index Raw rows by month",
            args.output_dir / "market_index_monthly_rows.svg",
        )
    print(f"RAW ANALYSIS SUCCESS output={args.output_dir}")


if __name__ == "__main__":
    main()
