"""Read-only audit of canonical Raw Blob partition months versus payload date fields."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any

from storage.blob import BlobStorage

_MONTHLY_PATH = re.compile(
    r"^data-go-kr/(?P<dataset>[^/]+)/operation=(?P<operation>[^/]+)/"
    r"year=(?P<year>\d{4})/month=(?P<month>\d{2})/(?P<file>[^/]+\.jsonl\.gz)$"
)
_DATE_KEY_HINTS = ("dt", "date", "ym", "year", "yy", "month")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--max-blobs", type=int)
    return parser.parse_args()


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    if len(text) >= 8 and text[:8].isdigit():
        try:
            return datetime.strptime(text[:8], "%Y%m%d").date()
        except ValueError:
            return None
    return None


def decode(data: bytes) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in gzip.decompress(data).splitlines()
        if line.strip()
    ]


def is_dateish_key(key: str) -> bool:
    lower = key.lower()
    return any(hint in lower for hint in _DATE_KEY_HINTS)


def main() -> None:
    args = parse_args()
    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    prefix = f"data-go-kr/{args.dataset}/"
    paths = []
    for path in storage.list_paths(container, prefix=prefix):
        match = _MONTHLY_PATH.match(path)
        if match:
            paths.append(path)
    paths.sort()
    if args.max_blobs:
        paths = paths[: args.max_blobs]
    if not paths:
        raise RuntimeError(f"No canonical monthly blobs found for {args.dataset}")

    records = 0
    basdt_present = 0
    basdt_missing = 0
    basdt_mismatch = 0
    legacy_present = 0
    legacy_mismatch = 0
    mismatch_examples: list[str] = []
    key_counts: Counter[str] = Counter()
    key_examples: dict[str, list[str]] = defaultdict(list)

    for index, path in enumerate(paths, start=1):
        match = _MONTHLY_PATH.match(path)
        assert match is not None
        path_month = (int(match.group("year")), int(match.group("month")))
        rows = decode(storage.download_bytes(container, path))
        for record in rows:
            records += 1
            payload = record.get("payload") or {}
            basdt = parse_date(payload.get("basDt"))
            if basdt is None:
                basdt_missing += 1
            else:
                basdt_present += 1
                if (basdt.year, basdt.month) != path_month:
                    basdt_mismatch += 1
                    if len(mismatch_examples) < 10:
                        mismatch_examples.append(
                            f"path={path} basDt={payload.get('basDt')} "
                            f"legacy.referenceDate={(record.get('legacy') or {}).get('referenceDate')}"
                        )

            legacy_date = parse_date((record.get("legacy") or {}).get("referenceDate"))
            if legacy_date is not None:
                legacy_present += 1
                if (legacy_date.year, legacy_date.month) != path_month:
                    legacy_mismatch += 1

            for key, value in payload.items():
                if not is_dateish_key(str(key)):
                    continue
                key_counts[str(key)] += 1
                examples = key_examples[str(key)]
                text = str(value)
                if text not in examples and len(examples) < 5:
                    examples.append(text)

        if index % 100 == 0 or index == len(paths):
            print(f"PROGRESS dataset={args.dataset} blobs={index}/{len(paths)} records={records}")

    print(
        "AUDIT SUMMARY "
        f"dataset={args.dataset} blobs={len(paths)} records={records} "
        f"basDt_present={basdt_present} basDt_missing={basdt_missing} "
        f"basDt_mismatch={basdt_mismatch} legacy_present={legacy_present} "
        f"legacy_mismatch={legacy_mismatch}"
    )
    for example in mismatch_examples:
        print(f"BASDT MISMATCH {example}")
    for key, count in key_counts.most_common():
        print(
            f"DATEISH FIELD dataset={args.dataset} key={key} count={count} "
            f"examples={json.dumps(key_examples[key], ensure_ascii=False)}"
        )


if __name__ == "__main__":
    main()
