"""canonical Raw Blob의 월 partition과 payload 날짜 필드가 일치하는지 읽기 전용으로 점검한다."""

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
    """감사 대상의 여러 날짜 표기를 ``date``로 읽되 해석 불가 값은 None으로 둔다."""

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
    """gzip JSONL object 하나를 레코드 목록으로 복원한다."""

    return [
        json.loads(line)
        for line in gzip.decompress(data).splitlines()
        if line.strip()
    ]


def is_dateish_key(key: str) -> bool:
    """payload schema 탐색용으로 날짜 의미가 있을 가능성이 높은 key를 찾는다."""

    lower = key.lower()
    return any(hint in lower for hint in _DATE_KEY_HINTS)


def main() -> None:
    args = parse_args()
    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    prefix = f"data-go-kr/{args.dataset}/"

    # canonical monthly layout과 정확히 일치하는 object만 감사한다. legacy 경로나 다른
    # 파생 파일이 섞이면 현재 Raw 규칙 검증 결과를 왜곡할 수 있기 때문이다.
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

            # 현재 Raw partition의 authoritative date는 payload.basDt 하나뿐이다.
            # legacy.referenceDate는 과거 migration 상태를 관찰하기 위한 비교값일 뿐
            # 현재 partition 정합성 판정에는 사용하지 않는다.
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

            # 향후 schema profiling에 참고할 수 있도록 날짜처럼 보이는 필드의 빈도와
            # 소수의 대표값만 수집한다. 모든 고유값을 메모리에 쌓지 않는다.
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
