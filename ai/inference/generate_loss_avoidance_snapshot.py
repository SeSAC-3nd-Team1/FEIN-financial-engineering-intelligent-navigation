"""Generate the Backend loss-avoidance artifact from Azure algorithm OHLCV."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

import pandas as pd

from data_access import FeatureStore, FeatureStoreConfig
from inference.loss_avoidance_snapshot import (
    REQUIRED_COLUMNS,
        SECURITY_MASTER_COLUMNS,
    build_loss_avoidance_snapshot,

    load_algorithm_v24,
)


DEFAULT_OUTPUT_PATH = Path("/model-artifacts/loss_avoidance_snapshot.json")


def _read_algorithm_history(store: FeatureStore, version: str) -> pd.DataFrame:
    files = tuple(store.parquet_files("algorithm_ohlcv", version))
    if not files:
        raise RuntimeError("Azure Feature dataset has no algorithm_ohlcv Parquet files")
    print(f"loss-avoidance: reading {len(files)} Azure OHLCV partitions", flush=True)
    frame = pd.concat(
        [
            store.read_partition(
                file.path,
                columns=REQUIRED_COLUMNS,
                etag=file.etag,
            )
            for file in files
        ],
        ignore_index=True,
    )
    print(f"loss-avoidance: loaded {len(frame):,} OHLCV rows", flush=True)
    return frame


def _read_security_master(store: FeatureStore, version: str) -> pd.DataFrame:
    files = tuple(store.parquet_files("security_master_latest", version))
    if not files:
        raise RuntimeError("Azure Feature dataset has no security_master_latest Parquet files")
    return pd.concat(
        [
            store.read_partition(file.path, columns=SECURITY_MASTER_COLUMNS, etag=file.etag)
            for file in files
        ],
        ignore_index=True,
    )


def _publish(snapshot, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Algorithm(ver.2.4)_fix2 and publish a loss-avoidance snapshot."
    )
    parser.add_argument("--algorithm-version", default="2")
    parser.add_argument("--security-master-version", default=os.getenv("SECURITY_MASTER_VERSION", "2"))
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--universe-size", type=int, default=20)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.getenv("LOSS_AVOIDANCE_SNAPSHOT_PATH", str(DEFAULT_OUTPUT_PATH))),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()

    print("loss-avoidance: starting Algorithm(ver.2.4)_fix2", flush=True)

    store = FeatureStore(FeatureStoreConfig.from_env())

    snapshot = build_loss_avoidance_snapshot(
        _read_algorithm_history(store, args.algorithm_version),
        algorithm=load_algorithm_v24(),
        data_version=f"algorithm_ohlcv-v{args.algorithm_version.removeprefix('v')}",
        top_n=args.top_n,
        universe_size=args.universe_size,
        security_master=_read_security_master(store, args.security_master_version),
    )
    _publish(snapshot, args.output)
    print(
        f"exported {len(snapshot.recommendations)} Algorithm(ver.2.4)_fix2 targets "
        f"for {snapshot.as_of} to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
