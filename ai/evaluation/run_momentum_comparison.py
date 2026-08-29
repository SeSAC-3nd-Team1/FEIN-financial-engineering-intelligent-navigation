"""Run the v1/v2/KOSPI quarterly comparison on Azure Feature datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_access import FeatureStore, FeatureStoreConfig
from evaluation.momentum_backtest import BacktestUnavailableError, compare_momentum_strategies
from inference.generate_latest_recommendations import _read_all_partitions
from inference.generate_risk_adjusted_momentum import build_v2_feature_history

MARKET_COLUMNS = ("trade_date", "index_name", "close_index")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare price-momentum-v1, risk-adjusted-momentum-v2, and KOSPI."
    )
    parser.add_argument("--model-version", default="2")
    parser.add_argument("--algorithm-version", default="2")
    parser.add_argument("--master-version", default="1")
    parser.add_argument("--market-version", default="2")
    parser.add_argument("--benchmark-name", default="코스피")
    parser.add_argument("--transaction-cost-bps", type=float, default=0.0)
    parser.add_argument(
        "--start-date",
        help="Common evaluation start date; earlier rows remain available only for feature warm-up.",
    )
    parser.add_argument("--end-date", help="Common inclusive evaluation end date.")
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    store = FeatureStore(FeatureStoreConfig.from_env())
    stock = build_v2_feature_history(
        store,
        model_version=args.model_version,
        algorithm_version=args.algorithm_version,
        master_version=args.master_version,
    )
    market = _read_all_partitions(
        store, "market_index_daily", args.market_version, MARKET_COLUMNS
    )
    exit_code = 0
    try:
        result = compare_momentum_strategies(
            stock,
            market,
            benchmark_name=args.benchmark_name,
            transaction_cost_bps=args.transaction_cost_bps,
            evaluation_start=args.start_date,
            evaluation_end=args.end_date,
        )
        payload = {"status": "ready", **result.to_dict()}
    except BacktestUnavailableError as exc:
        # 수정주가 안전 조건을 만족하지 못하면 부분 지표도 성공 결과처럼 발행하지 않는다.
        payload = {
            "status": "unavailable",
            "reason": str(exc),
            "rebalance_frequency": "QUARTERLY",
            "transaction_cost_bps": args.transaction_cost_bps,
            "requested_start_date": args.start_date,
            "requested_end_date": args.end_date,
            "price_policy": "point-in-time split-adjusted; fail-closed on unresolved held-security events",
        }
        exit_code = 2
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
