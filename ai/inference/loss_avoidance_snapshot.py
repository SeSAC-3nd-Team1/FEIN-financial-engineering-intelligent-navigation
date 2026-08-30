"""Run Algorithm(ver.2.4) and publish its portfolio snapshot for the Backend."""

from __future__ import annotations

import importlib.util
import math
import os
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from types import ModuleType

import numpy as np
import pandas as pd

ALGORITHM_FILENAME = "Algorithm(ver.2.4)_fix2.py"
REQUIRED_COLUMNS = (
    "symbol",
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
    "is_tradable",
)
MAX_MODEL_HISTORY_ROWS = 1500


@dataclass(frozen=True)
class LossAvoidanceItem:
    symbol: str
    stock_name: str | None
    score: float
    rank: int
    target_weight: float
    reason: str


@dataclass(frozen=True)
class LossAvoidanceSnapshot:
    as_of: str
    generated_at: str
    model_version: str
    data_version: str
    status: str
    market_regime: str
    source: str
    is_stale: bool
    recommendations: tuple[LossAvoidanceItem, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def default_algorithm_path() -> Path:
    """Resolve the reference engine in a checkout or the AI container mount."""

    configured = os.getenv("ALGORITHM_V24_PATH", "").strip()
    if configured:
        return Path(configured)
    repository_path = Path(__file__).resolve().parents[2] / "output" / ALGORITHM_FILENAME
    if repository_path.exists():
        return repository_path
    return Path("/algorithm-output") / ALGORITHM_FILENAME


def load_algorithm_v24(path: str | Path | None = None) -> ModuleType:
    """Load the team's v2.4 source file without copying or rewriting it."""

    source = Path(path) if path is not None else default_algorithm_path()
    if not source.is_file():
        raise FileNotFoundError(f"Algorithm(ver.2.4) source not found: {source}")
    module_name = "team_algorithm_v2_4"
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"Algorithm(ver.2.4) cannot be loaded: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _candidate_symbols(frame: pd.DataFrame, universe_size: int) -> list[str]:
    tradable = frame.loc[frame["is_tradable"], ["symbol", "Date", "Close", "Volume"]]
    latest_date = tradable["Date"].max()
    recent_dates = tradable["Date"].drop_duplicates().nlargest(60)
    recent = tradable.loc[tradable["Date"].isin(recent_dates)].copy()
    recent["notional"] = (recent["Close"] * recent["Volume"]).replace(
        [np.inf, -np.inf], np.nan
    )
    liquidity = recent.groupby("symbol")["notional"].median()
    current = tradable.loc[tradable["Date"].eq(latest_date), "symbol"].drop_duplicates()
    liquidities = [
        (str(symbol), float(liquidity[symbol]))
        for symbol in current
        if symbol in liquidity and pd.notna(liquidity[symbol]) and float(liquidity[symbol]) > 0
    ]
    liquidities.sort(key=lambda item: (-item[1], item[0]))
    return [symbol for symbol, _ in liquidities[:universe_size]]


def build_loss_avoidance_snapshot(
    frame: pd.DataFrame,
    *,
    algorithm: ModuleType,
    data_version: str,
    top_n: int = 5,
    universe_size: int = 20,
) -> LossAvoidanceSnapshot:
    """Evaluate liquid symbols with Algorithm(ver.2.4) and adapt its weights.

    The liquidity rule only defines the executable universe. Signal, regime, risk
    state, and exposure all come from Algorithm(ver.2.4). The portfolio adapter
    preserves the engine's gross exposure and divides it by positive engine weights.
    """

    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"algorithm input columns missing: {missing}")
    if top_n < 1 or universe_size < top_n:
        raise ValueError("universe_size must be greater than or equal to top_n")

    data = frame.copy()
    data["symbol"] = data["symbol"].astype("string").str.strip().str.zfill(6)
    data["Date"] = pd.to_datetime(data["Date"], errors="raise")
    data["is_tradable"] = data["is_tradable"].fillna(False).astype(bool)
    if data.empty or not data["is_tradable"].any():
        raise ValueError("no tradable Algorithm(ver.2.4) input rows are available")

    candidates: list[dict[str, object]] = []
    symbols = _candidate_symbols(data, universe_size)
    started = time.monotonic()
    print(f"loss-avoidance: evaluating {len(symbols)} liquid symbols", flush=True)
    for index, symbol in enumerate(symbols, start=1):
        history = data.loc[
            data["symbol"].eq(symbol) & data["is_tradable"],
            ["Date", "Open", "High", "Low", "Close", "Volume"],
        ].sort_values("Date").tail(MAX_MODEL_HISTORY_ROWS)
        if len(history) < 254:
            print(f"loss-avoidance: [{index}/{len(symbols)}] {symbol} skipped (history={len(history)})", flush=True)
            continue
        result = algorithm.run_backtest(history, algorithm.Config())
        if result.decisions.empty:
            print(f"loss-avoidance: [{index}/{len(symbols)}] {symbol} skipped (no decisions)", flush=True)
            continue
        decision = result.decisions.iloc[-1]
        target = float(np.clip(float(decision["target_weight"]), 0.0, 0.95))
        variance = max(float(decision["forecast_variance"]), 1e-12)
        mu_net = float(decision["mu_net"])
        if not math.isfinite(target) or target <= 0:
            continue
        candidates.append(
            {
                "symbol": symbol,
                "as_of": pd.Timestamp(result.decisions.index[-1]),
                "raw_target": target,
                "score": mu_net / math.sqrt(variance),
                "regime": str(decision["engine_regime"]),
                "risk_reason": str(decision["risk_reason"]),
            }
        )
        print(
            f"loss-avoidance: [{index}/{len(symbols)}] {symbol} evaluated "
            f"({time.monotonic() - started:.1f}s)",
            flush=True,
        )
    if not candidates:
        raise ValueError("Algorithm(ver.2.4) produced no investable targets")

    candidates.sort(
        key=lambda item: (-float(item["score"]), str(item["symbol"]))
    )
    selected = candidates[:top_n]
    gross_exposure = min(0.95, max(float(item["raw_target"]) for item in selected))
    denominator = sum(float(item["raw_target"]) for item in selected)
    weights = [gross_exposure * float(item["raw_target"]) / denominator for item in selected]
    # Decimal conversion in the Backend expects an exact maximum of 0.95. Keep the
    # rounded residual on the final symbol so the JSON weights remain deterministic.
    rounded = [round(weight, 8) for weight in weights]
    rounded[-1] = round(gross_exposure - sum(rounded[:-1]), 8)

    regimes = Counter(str(item["regime"]) for item in selected)
    dominant_regime = regimes.most_common(1)[0][0]
    market_regime = {
        "bull": "risk_on",
        "bear": "risk_off",
        "sideways": "neutral",
    }.get(dominant_regime, "neutral")
    items = tuple(
        LossAvoidanceItem(
            symbol=str(item["symbol"]),
            stock_name=None,
            score=round(float(item["score"]), 8),
            rank=rank,
            target_weight=rounded[rank - 1],
            reason=(
                f"Algorithm(ver.2.4)_fix2 {item['regime']} regime / "
                f"risk={item['risk_reason']}"
            ),
        )
        for rank, item in enumerate(selected, start=1)
    )
    as_of = min(pd.Timestamp(item["as_of"]) for item in selected).date().isoformat()
    return LossAvoidanceSnapshot(
        as_of=as_of,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_version="algorithm-v2.4-fix2",
        data_version=data_version,
        status="ready",
        market_regime=market_regime,
        source="generated",
        is_stale=False,
        recommendations=items,
    )
