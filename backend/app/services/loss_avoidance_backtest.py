"""Algorithm v2.4 fix2를 여러 종목 포트폴리오 백테스트에 연결한다."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType

import pandas as pd

from app.core.errors import NotFoundError
from app.repositories.backtest import StockPricePoint


MODEL_FILENAME = "Algorithm(ver.2.4)_fix2.py"
DEFAULT_MODEL_PATHS = (
    Path("/models") / MODEL_FILENAME,
    Path(__file__).resolve().parents[3] / "output" / MODEL_FILENAME,
)


def _load_model() -> ModuleType:
    """운영 mount와 소스 checkout 순서로 팀 원본 fix2 모델을 로드한다."""

    configured = os.getenv("LOSS_AVOIDANCE_MODEL_PATH", "").strip()
    candidates = (Path(configured),) if configured else DEFAULT_MODEL_PATHS
    for path in candidates:
        if not path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("team_algorithm_v2_4_fix2", path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    raise NotFoundError(
        "BACKTEST_MODEL_UNAVAILABLE",
        "물림방지 Algorithm(ver.2.4)_fix2 모델을 불러올 수 없습니다.",
    )


def run_loss_avoidance_backtest(
    points: list[StockPricePoint], dates: list,
    *,
    max_symbols: int = 20,
) -> list[float]:
    """고정된 시작 universe의 종목별 fix2 equity를 동일비중으로 합산한다."""

    model = _load_model()
    grouped: dict[str, list[StockPricePoint]] = {}
    for point in points:
        grouped.setdefault(point.stock_code, []).append(point)
    curves: list[pd.Series] = []
    for symbol in list(grouped)[:max_symbols]:
        rows = []
        for point in sorted(grouped[symbol], key=lambda item: item.trade_date):
            if None in (point.open_price, point.high_price, point.low_price) or point.volume is None:
                continue
            rows.append({
                "Date": pd.Timestamp(point.trade_date),
                "Open": float(point.open_price),
                "High": float(point.high_price),
                "Low": float(point.low_price),
                "Close": float(point.close),
                "Volume": float(point.volume),
            })
        if not rows:
            continue
        frame = pd.DataFrame(rows)
        config = model.Config(initial_cash=1.0)
        monitor = model.load_loss_cut_monitor(
            True, config.stop_cooldown_bars, config.stop_reentry_total_bars
        )
        result = model.run_backtest(frame, config, loss_cut_monitor=monitor)
        if result.equity.empty:
            continue
        curve = result.equity.astype(float)
        curve.index = pd.to_datetime(curve.index).date
        first = float(curve.iloc[0])
        if first > 0:
            curves.append(curve / first)
    if not curves:
        raise NotFoundError(
            "BACKTEST_DATA_UNAVAILABLE",
            "물림방지 Algorithm(ver.2.4)_fix2 백테스트 데이터가 부족합니다.",
        )
    history = pd.concat(curves, axis=1).sort_index().ffill()
    portfolio = history.mean(axis=1, skipna=True).reindex(dates).ffill().fillna(1.0)
    return [float(value) for value in portfolio.tolist()]
