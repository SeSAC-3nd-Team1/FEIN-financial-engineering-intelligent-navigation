"""Backfill an additional historical window with resumable checkpoints.

Run the regular range-capable operations first so stock trading dates exist in the
target database. The issuance-status endpoint is then collected one trading day at
a time because its range query is not reliable on data.go.kr.
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
ISSUANCE_STATUS_OPERATION = "getStocIssuStat_V3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Add a historical date window directly to the configured DB."
    )
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--progress-every", type=int, default=25)
    return parser.parse_args()


def build_commands(
    *, start_date: date, end_date: date, rows: int, progress_every: int
) -> list[list[str]]:
    common = [
        "--start-date",
        start_date.isoformat(),
        "--end-date",
        end_date.isoformat(),
        "--rows",
        str(rows),
        "--progress-every",
        str(progress_every),
    ]
    return [
        [
            sys.executable,
            str(SCRIPT_DIR / "collect_public_data.py"),
            "--all-datasets",
            "--all-operations",
            "--exclude-operation",
            ISSUANCE_STATUS_OPERATION,
            "--all-pages",
            *common,
        ],
        [
            sys.executable,
            str(SCRIPT_DIR / "backfill_issuance_status.py"),
            *common,
        ],
    ]


def main() -> None:
    args = parse_args()
    if args.start_date > args.end_date:
        raise ValueError("--start-date must not be after --end-date")
    if args.rows < 1 or args.rows > 10_000:
        raise ValueError("--rows must be between 1 and 10000")
    if args.progress_every < 1:
        raise ValueError("--progress-every must be at least 1")

    for command in build_commands(
        start_date=args.start_date,
        end_date=args.end_date,
        rows=args.rows,
        progress_every=args.progress_every,
    ):
        subprocess.run(command, check=True)

    print(
        "historical backfill complete: "
        f"range={args.start_date}..{args.end_date}"
    )


if __name__ == "__main__":
    main()
