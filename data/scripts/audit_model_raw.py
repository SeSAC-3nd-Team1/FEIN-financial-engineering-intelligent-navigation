"""Azure Blob의 OpenDART Raw 원문을 직접 읽어 완전성과 정합성을 감사한다."""

from __future__ import annotations

import argparse
import calendar
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from storage import BlobStorage
from scripts.collect_model_raw import CoverageManifest


DATA_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = DATA_ROOT.parent
AUDIT_REPORT_PATH = DATA_ROOT / "reports" / "MODEL_RAW_AUDIT.json"
DATE_PATH = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/")
STOCK_CODE = re.compile(r"[0-9A-Z]{6}")


def _month_starts(start: date, end: date) -> list[str]:
    cursor = start.replace(day=1)
    values: list[str] = []
    while cursor <= end:
        values.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return values


def _download_json(storage: BlobStorage, container: str, path: str) -> tuple[str, int, Any]:
    content = storage.download_bytes(container, path)
    return path, len(content), json.loads(content)


def audit(
    *, start: date, end: date, workers: int,
    storage: BlobStorage | None = None, container: str | None = None,
) -> dict[str, Any]:
    storage = storage or BlobStorage.from_env()
    container = container or os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    prefixes = {
        "financial": "opendart/financial_multi/",
        "financial_anomaly": "opendart/financial_multi_anomaly/",
        "disclosure": "opendart/disclosure_market/",
    }
    paths = {
        name: storage.list_paths(container, prefix=prefix)
        for name, prefix in prefixes.items()
    }
    result: dict[str, Any] = {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "listed_blobs": {name: len(values) for name, values in paths.items()},
        "parse_errors": [],
    }
    financial = {
        "bytes": 0, "rows": 0, "corp_codes": set(), "stock_codes": set(),
        "logical_row_hashes": set(),
        "business_year_mismatches": [], "invalid_stock_codes": [],
    }
    anomaly = {"bytes": 0, "rows": 0, "corp_codes": set(), "observed_years": set()}
    disclosure = {
        "bytes": 0, "rows": 0, "receipt_numbers": set(),
        "pages": defaultdict(set), "total_pages": defaultdict(set),
        "mixed_month_blobs": [], "mixed_market_blobs": [],
    }
    jobs = [(kind, path) for kind, values in paths.items() for path in values]
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as executor:
        futures = {
            executor.submit(_download_json, storage, container, path): (kind, path)
            for kind, path in jobs
        }
        for index, future in enumerate(as_completed(futures), start=1):
            kind, original_path = futures[future]
            try:
                path, size, payload = future.result()
                rows = payload.get("list", [])
                if not isinstance(payload, dict) or not isinstance(rows, list):
                    raise ValueError("payload/list has invalid type")
            except Exception as exc:  # 원문 전수 감사에서는 모든 오류를 모아 보고한다.
                result["parse_errors"].append(
                    {"path": original_path, "error": f"{type(exc).__name__}: {exc}"}
                )
                continue
            if kind == "financial":
                financial["bytes"] += size
                financial["rows"] += len(rows)
                match = DATE_PATH.search(path)
                path_year = match.group(1) if match else ""
                for row in rows:
                    corp_code = str(row.get("corp_code") or "").strip()
                    stock_code = str(row.get("stock_code") or "").strip()
                    financial["corp_codes"].add(corp_code)
                    if stock_code:
                        financial["stock_codes"].add(stock_code)
                    if stock_code and not STOCK_CODE.fullmatch(stock_code):
                        financial["invalid_stock_codes"].append(
                            {"path": path, "corp_code": corp_code, "stock_code": stock_code}
                        )
                    business_year = str(row.get("bsns_year") or "").strip()
                    account_id = str(row.get("account_id") or "").strip()
                    if not account_id:
                        account_id = "name:" + re.sub(
                            r"\s+", "", str(row.get("account_nm") or "")
                        )
                    logical_key = "\x1f".join((
                        corp_code,
                        business_year,
                        str(row.get("reprt_code") or "").strip(),
                        str(row.get("fs_div") or "").strip(),
                        str(row.get("sj_div") or "").strip(),
                        account_id,
                    ))
                    financial["logical_row_hashes"].add(
                        hashlib.blake2b(logical_key.encode(), digest_size=8).digest()
                    )
                    if path_year and business_year != path_year:
                        financial["business_year_mismatches"].append(
                            {"path": path, "corp_code": corp_code, "business_year": business_year}
                        )
            elif kind == "financial_anomaly":
                anomaly["bytes"] += size
                anomaly["rows"] += len(rows)
                anomaly["corp_codes"].update(
                    str(row.get("corp_code") or "").strip() for row in rows
                )
                anomaly["observed_years"].update(
                    str(row.get("bsns_year") or "").strip() for row in rows
                )
            else:
                disclosure["bytes"] += size
                disclosure["rows"] += len(rows)
                months = {
                    str(row.get("rcept_dt") or "")[:6] for row in rows
                    if len(str(row.get("rcept_dt") or "")) >= 6
                }
                markets = {
                    str(row.get("corp_cls") or "").strip() for row in rows
                    if str(row.get("corp_cls") or "").strip()
                }
                if len(months) != 1:
                    disclosure["mixed_month_blobs"].append(path)
                if len(markets) != 1:
                    disclosure["mixed_market_blobs"].append(path)
                if len(months) == 1 and len(markets) == 1:
                    month = next(iter(months))
                    key = (f"{month[:4]}-{month[4:]}", next(iter(markets)))
                    disclosure["pages"][key].add(int(payload.get("page_no", 0)))
                    disclosure["total_pages"][key].add(int(payload.get("total_page", 0)))
                disclosure["receipt_numbers"].update(
                    str(row.get("rcept_no") or "").strip() for row in rows
                )
            if index % 1000 == 0 or index == len(jobs):
                print(f"[AUDIT] blobs={index:,}/{len(jobs):,}", flush=True)

    expected_groups = {
        (month, market) for month in _month_starts(start, end) for market in ("Y", "K")
    }
    present_groups = set(disclosure["pages"])
    incomplete_groups = []
    for key in sorted(present_groups):
        totals = disclosure["total_pages"][key]
        expected_pages = set(range(1, max(totals, default=0) + 1))
        missing_pages = sorted(expected_pages - disclosure["pages"][key])
        if missing_pages:
            incomplete_groups.append(
                {"month": key[0], "market": key[1], "missing_pages": missing_pages}
            )
    result["financial"] = {
        "bytes": financial["bytes"],
        "rows": financial["rows"],
        "unique_logical_rows": len(financial["logical_row_hashes"]),
        "unique_corp_codes": len(financial["corp_codes"] - {""}),
        "unique_stock_codes": len(financial["stock_codes"]),
        "business_year_mismatches": financial["business_year_mismatches"],
        "invalid_stock_codes": financial["invalid_stock_codes"],
    }
    result["financial_anomaly"] = {
        "bytes": anomaly["bytes"], "rows": anomaly["rows"],
        "corp_codes": sorted(anomaly["corp_codes"] - {""}),
        "observed_years": sorted(anomaly["observed_years"] - {""}),
    }
    result["disclosure"] = {
        "bytes": disclosure["bytes"],
        "rows": disclosure["rows"],
        "unique_receipt_numbers": len(disclosure["receipt_numbers"] - {""}),
        "expected_month_market_groups": len(expected_groups),
        "present_month_market_groups": len(present_groups),
        "missing_groups": [
            {"month": month, "market": market}
            for month, market in sorted(expected_groups - present_groups)
        ],
        "incomplete_groups": incomplete_groups,
        "mixed_month_blobs": disclosure["mixed_month_blobs"],
        "mixed_market_blobs": disclosure["mixed_market_blobs"],
    }
    result["complete"] = not any((
        result["parse_errors"],
        result["financial"]["business_year_mismatches"],
        result["financial"]["invalid_stock_codes"],
        result["disclosure"]["missing_groups"],
        result["disclosure"]["incomplete_groups"],
        result["disclosure"]["mixed_month_blobs"],
        result["disclosure"]["mixed_market_blobs"],
    ))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2018, 1, 1))
    parser.add_argument(
        "--end-date", type=date.fromisoformat,
        default=datetime.now(ZoneInfo("Asia/Seoul")).date(),
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--repair-manifest", action="store_true",
        help="Blob 전수 감사 통과 시 공시 완료 checkpoint를 실제 coverage로 복원한다.",
    )
    args = parser.parse_args()
    load_dotenv(REPOSITORY_ROOT / ".env", override=False)
    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    result = audit(
        start=args.start_date, end=args.end_date, workers=args.workers,
        storage=storage, container=container,
    )
    if args.repair_manifest:
        if not result["complete"]:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            raise RuntimeError("incomplete Blob audit cannot repair coverage manifest")
        manifest = CoverageManifest(storage, container)
        repaired = 0
        for month in _month_starts(args.start_date, args.end_date):
            year, month_number = map(int, month.split("-"))
            month_start = date(year, month_number, 1)
            month_end = date(
                year, month_number, calendar.monthrange(year, month_number)[1]
            )
            range_start = max(month_start, args.start_date)
            range_end = min(month_end, args.end_date)
            for market in ("Y", "K"):
                partition = f"{range_start.isoformat()}..{range_end.isoformat()}-{market}"
                if not manifest.is_completed(
                    "opendart", "disclosure_market", "disclosure_market", partition
                ):
                    manifest.mark(
                        source="opendart", dataset="disclosure_market",
                        operation="disclosure_market", partition=partition,
                        rows=0, blob_count=0,
                    )
                    repaired += 1
        manifest.save()
        result["manifest_repaired_partitions"] = repaired
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    AUDIT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_REPORT_PATH.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
