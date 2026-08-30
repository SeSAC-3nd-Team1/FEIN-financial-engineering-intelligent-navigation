"""Precompute the production MVP backtest presets into a JSON artifact."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys

from app.db.session import SessionLocal
from app.repositories.backtest import BacktestRepository
from app.schemas.api import BacktestRunRequest
from app.services.backtest import BacktestService


PRESETS = (
    ("corona-crash", "코로나 폭락", date(2020, 1, 20), date(2020, 6, 30), "시장이 급격하게 하락했던 시기에 이 전략이 얼마나 버텼는지 확인해보세요."),
    ("downturn-2022", "2022 하락장", date(2022, 1, 1), date(2022, 12, 30), "시장이 장기간 약세를 보였을 때 전략의 수익과 위험을 확인해보세요."),
)


def main() -> int:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else ".deploy-artifacts/backtest-results.json")
    service = BacktestService(BacktestRepository(SessionLocal()))
    available = service.available_range("momentum")
    periods = list(PRESETS)
    recent_start = date.fromisoformat(available.max_date.isoformat()).replace(
        year=available.max_date.year - 5
    )
    periods.append(("recent-5y", "최근 5년", max(recent_start, available.min_date), available.max_date, "상승과 하락을 포함한 장기적인 성과를 확인해보세요."))

    results: dict[str, dict[str, object]] = {}
    try:
        for period_id, label, start, end, description in periods:
            if start < available.min_date or end > available.max_date:
                print(f"Skipping unavailable preset: {period_id} ({start}..{end})")
                continue
            request = BacktestRunRequest.model_validate({
                "strategyId": "momentum",
                "periodId": period_id,
                "periodLabel": label,
                "periodDescription": description,
                "startDate": start,
                "endDate": end,
            })
            results[period_id] = service.run(request).model_dump(mode="json", by_alias=True)
            print(f"Generated preset: {period_id}")
    finally:
        service.repository.session.close()

    if not results:
        raise RuntimeError("No production backtest preset could be generated")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"version": 1, "strategyId": "momentum", "periods": results}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(results)} precomputed backtest presets to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
