"""2018년 이후 OpenDART 모델 Raw를 월별 Processed Parquet으로 정규화한다."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import re
from typing import Any

import pandas as pd

from collectors.opendart_client import parse_corp_code_zip


FINANCIAL_PATH_RE = re.compile(
    r"^opendart/financial_multi/(?P<year>\d{4})/(?P<month>\d{2})/"
    r"(?P<day>\d{2})/(?P<hash>[0-9a-f]{64})\.json$"
)
DISCLOSURE_PATH_RE = re.compile(
    r"^opendart/disclosure_market/(?P<year>\d{4})/(?P<month>\d{2})/"
    r"(?P<day>\d{2})/(?P<hash>[0-9a-f]{64})\.json$"
)
SCHEMA_DATASETS = {
    "financial": ("opendart_financial_accounts", "financial_multi"),
    "disclosure": ("opendart_disclosures", "disclosure_market"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(paths: list[str]) -> str:
    """content-addressed Raw 경로 목록을 월별 변경 감지용 hash로 바꾼다."""

    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _month_path(
    dataset: str, operation: str, version: str, year: int, month: int
) -> str:
    return (
        f"{dataset}/operation={operation}/schema=v{version}/"
        f"year={year:04d}/month={month:02d}/part-00000.parquet"
    )


def _quality_path(
    dataset: str, operation: str, version: str, year: int, month: int
) -> str:
    return (
        f"_quality/{dataset}/operation={operation}/schema=v{version}/"
        f"year={year:04d}/month={month:02d}/manifest.json"
    )


def _group_paths(
    storage,
    container: str,
    *,
    prefix: str,
    pattern: re.Pattern[str],
    start_date: date,
    end_date: date,
) -> dict[tuple[int, int], list[str]]:
    """요청 기간과 겹치는 OpenDART Raw를 월별 bounded 작업으로 그룹화한다."""

    grouped: dict[tuple[int, int], list[str]] = defaultdict(list)
    for path in storage.list_paths(container, prefix=prefix):
        match = pattern.fullmatch(path)
        if not match:
            continue
        partition_date = date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
        if start_date <= partition_date <= end_date:
            grouped[(partition_date.year, partition_date.month)].append(path)
    return dict(grouped)


def _latest_corp_map(storage, container: str) -> dict[str, str]:
    """최신 corpCode snapshot을 공시의 corp_code→stock_code 참조 매핑으로 사용한다."""

    paths = sorted(
        path
        for path in storage.list_paths(container, prefix="opendart/corp_code/")
        if path.endswith(".zip")
    )
    if not paths:
        raise RuntimeError("OpenDART corp_code Raw not found")
    records = parse_corp_code_zip(storage.download_bytes(container, paths[-1]))
    return {
        record.corp_code: record.stock_code
        for record in records
        if record.stock_code
    }


def _amount_text(value: Any) -> str | None:
    """금액을 손실 없는 10진 문자열로 정규화해 Parquet 정밀도 추론 차이를 막는다."""

    text = str(value or "").strip().replace(",", "").replace(" ", "")
    if not text or text == "-":
        return None
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return format(Decimal(text), "f")
    except InvalidOperation:
        return None


def _financial_rows(
    payload: dict[str, Any], *, source_blob: str, corp_map: dict[str, str]
) -> list[dict[str, Any]]:
    """fnlttMultiAcnt 응답의 계정 행과 Raw lineage를 보존한다."""

    result: list[dict[str, Any]] = []
    for item in payload.get("list", []):
        if not isinstance(item, dict):
            continue
        corp_code = str(item.get("corp_code") or "").strip()
        account_name = str(item.get("account_nm") or "").strip()
        account_id = str(item.get("account_id") or "").strip()
        if not account_id:
            account_id = "name:" + re.sub(r"\s+", "", account_name)
        result.append({
            "corp_code": corp_code,
            "stock_code": str(item.get("stock_code") or corp_map.get(corp_code) or ""),
            "business_year": str(item.get("bsns_year") or ""),
            "report_code": str(item.get("reprt_code") or ""),
            "fs_div": str(item.get("fs_div") or ""),
            "fs_name": str(item.get("fs_nm") or ""),
            "statement_div": str(item.get("sj_div") or ""),
            "statement_name": str(item.get("sj_nm") or ""),
            "account_id": account_id,
            "account_name": account_name,
            "current_period_name": str(item.get("thstrm_nm") or ""),
            "current_period_start": str(item.get("thstrm_start_dt") or ""),
            "current_period_end": str(item.get("thstrm_end_dt") or ""),
            "current_amount": _amount_text(item.get("thstrm_amount")),
            "current_cumulative_amount": _amount_text(item.get("thstrm_add_amount")),
            "previous_period_name": str(item.get("frmtrm_nm") or ""),
            "previous_period_start": str(item.get("frmtrm_start_dt") or ""),
            "previous_period_end": str(item.get("frmtrm_end_dt") or ""),
            "previous_amount": _amount_text(item.get("frmtrm_amount")),
            "previous_cumulative_amount": _amount_text(item.get("frmtrm_add_amount")),
            "currency": str(item.get("currency") or "KRW"),
            "ordinal": str(item.get("ord") or ""),
            # 재무 API 자체에는 접수번호·접수일이 없으므로 공시 목록과 검증된 연결 전에는
            # 가격 시계열에 결합할 수 없다. 안전하지 않은 기준일 추정을 만들지 않는다.
            "available_at": None,
            "point_in_time_join_ready": False,
            "_source_blob": source_blob,
        })
    return result


def _disclosure_rows(
    payload: dict[str, Any], *, source_blob: str, corp_map: dict[str, str]
) -> list[dict[str, Any]]:
    """공시 목록을 실제 접수일 기반 이벤트 행으로 정규화한다."""

    result: list[dict[str, Any]] = []
    for item in payload.get("list", []):
        if not isinstance(item, dict):
            continue
        receipt_no = str(item.get("rcept_no") or "").strip()
        receipt_text = str(item.get("rcept_dt") or "").strip()
        corp_code = str(item.get("corp_code") or "").strip()
        if not receipt_no or not re.fullmatch(r"\d{8}", receipt_text):
            continue
        result.append({
            "receipt_no": receipt_no,
            "receipt_date": pd.to_datetime(receipt_text, format="%Y%m%d", errors="raise"),
            "corp_code": corp_code,
            "stock_code": str(item.get("stock_code") or corp_map.get(corp_code) or ""),
            "corp_name": str(item.get("corp_name") or ""),
            "market": str(item.get("corp_cls") or ""),
            "report_name": str(item.get("report_nm") or ""),
            "filer_name": str(item.get("flr_nm") or ""),
            "remarks": str(item.get("rm") or ""),
            "available_at": pd.to_datetime(receipt_text, format="%Y%m%d", errors="raise"),
            "point_in_time_join_ready": True,
            "_source_blob": source_blob,
        })
    return result


def _normalize_month(
    storage,
    container: str,
    *,
    kind: str,
    paths: list[str],
    corp_map: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, int]]:
    """한 달만 메모리에 유지하며 JSON parse·중복 품질을 집계한다."""

    rows: list[dict[str, Any]] = []
    source_rows = invalid_payloads = 0
    mapper = _financial_rows if kind == "financial" else _disclosure_rows
    for path in sorted(paths):
        payload = json.loads(storage.download_bytes(container, path))
        if not isinstance(payload, dict) or not isinstance(payload.get("list"), list):
            invalid_payloads += 1
            continue
        source_rows += len(payload["list"])
        rows.extend(mapper(payload, source_blob=path, corp_map=corp_map))

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame, {
            "source_rows": source_rows,
            "output_rows": 0,
            "duplicate_rows": 0,
            "invalid_payloads": invalid_payloads,
        }
    lineage_column = "_source_blob"
    exact_columns = [column for column in frame.columns if column != lineage_column]
    before = len(frame)
    frame = frame.drop_duplicates(exact_columns, keep="first")
    key = (
        ["receipt_no"]
        if kind == "disclosure"
        else [
            "corp_code", "business_year", "report_code", "fs_div",
            "statement_div", "account_id", "ordinal",
        ]
    )
    frame = frame.sort_values(key + [lineage_column]).reset_index(drop=True)
    return frame, {
        "source_rows": source_rows,
        "output_rows": len(frame),
        "duplicate_rows": before - len(frame),
        "invalid_payloads": invalid_payloads,
    }


def _write_month(
    storage,
    *,
    processed_container: str,
    dataset: str,
    operation: str,
    schema_version: str,
    year: int,
    month: int,
    frame: pd.DataFrame,
    quality: dict[str, Any],
    source_fingerprint: str,
    source_paths: list[str],
) -> dict[str, Any]:
    """월별 Parquet과 재현 가능한 품질 manifest를 함께 덮어쓴다."""

    output_path = _month_path(dataset, operation, schema_version, year, month)
    manifest_path = _quality_path(dataset, operation, schema_version, year, month)
    output = io.BytesIO()
    frame.to_parquet(output, index=False, compression="zstd")
    blob = storage.upload_bytes(
        processed_container,
        output_path,
        output.getvalue(),
        overwrite=True,
        content_type="application/vnd.apache.parquet",
        metadata={
            "source": "opendart",
            "dataset": dataset,
            "schema_version": schema_version,
            "record_count": str(len(frame)),
            "source_fingerprint": source_fingerprint,
        },
    )
    manifest = {
        "dataset": dataset,
        "operation": operation,
        "schema_version": schema_version,
        "year": year,
        "month": month,
        "rows": len(frame),
        "bytes": blob.size,
        "source_blobs": len(source_paths),
        "source_fingerprint": source_fingerprint,
        "output_path": output_path,
        **quality,
    }
    storage.upload_bytes(
        processed_container,
        manifest_path,
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        overwrite=True,
        content_type="application/json",
    )
    return manifest


def build_opendart_processed(
    storage,
    *,
    raw_container: str,
    processed_container: str,
    start_date: date,
    end_date: date,
    schema_version: str = "2",
) -> dict[str, Any]:
    """OpenDART 재무·공시를 월별 Processed로 증분 materialize한다."""

    corp_map = _latest_corp_map(storage, raw_container)
    grouped_by_kind = {
        "financial": _group_paths(
            storage,
            raw_container,
            prefix="opendart/financial_multi/",
            pattern=FINANCIAL_PATH_RE,
            start_date=start_date,
            end_date=end_date,
        ),
        "disclosure": _group_paths(
            storage,
            raw_container,
            prefix="opendart/disclosure_market/",
            pattern=DISCLOSURE_PATH_RE,
            start_date=start_date,
            end_date=end_date,
        ),
    }
    if not all(grouped_by_kind.values()):
        missing = [kind for kind, grouped in grouped_by_kind.items() if not grouped]
        raise RuntimeError(f"OpenDART model Raw not found: {missing}")

    partitions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for kind, grouped in grouped_by_kind.items():
        dataset, operation = SCHEMA_DATASETS[kind]
        for (year, month), paths in sorted(grouped.items()):
            source_fingerprint = _fingerprint(paths)
            output_path = _month_path(dataset, operation, schema_version, year, month)
            manifest_path = _quality_path(dataset, operation, schema_version, year, month)
            if storage.exists(processed_container, output_path) and storage.exists(
                processed_container, manifest_path
            ):
                previous = json.loads(
                    storage.download_bytes(processed_container, manifest_path)
                )
                if previous.get("source_fingerprint") == source_fingerprint:
                    partitions[kind].append(previous)
                    print(
                        f"OPENDART PROCESSED SKIP kind={kind} "
                        f"year={year} month={month:02d}"
                    )
                    continue
            frame, quality = _normalize_month(
                storage,
                raw_container,
                kind=kind,
                paths=paths,
                corp_map=corp_map,
            )
            if frame.empty:
                raise RuntimeError(
                    f"OpenDART normalized month is empty: {kind} {year}-{month:02d}"
                )
            manifest = _write_month(
                storage,
                processed_container=processed_container,
                dataset=dataset,
                operation=operation,
                schema_version=schema_version,
                year=year,
                month=month,
                frame=frame,
                quality=quality,
                source_fingerprint=source_fingerprint,
                source_paths=paths,
            )
            partitions[kind].append(manifest)
            print(
                f"OPENDART PROCESSED WRITE kind={kind} year={year} "
                f"month={month:02d} rows={len(frame):,}"
            )

    payload = {
        "generated_at": _utc_now(),
        "schema_version": schema_version,
        "requested_start": start_date.isoformat(),
        "requested_end": end_date.isoformat(),
        "financial": {
            "status": "normalized_not_pit_ready",
            "rows": sum(int(item["rows"]) for item in partitions["financial"]),
            "partitions": partitions["financial"],
            "point_in_time_join_ready": False,
        },
        "disclosure": {
            "status": "event_ready",
            "rows": sum(int(item["rows"]) for item in partitions["disclosure"]),
            "partitions": partitions["disclosure"],
            "point_in_time_join_ready": True,
        },
        "excluded_raw_prefixes": ["opendart/financial_multi_anomaly/"],
    }
    storage.upload_bytes(
        processed_container,
        f"_manifests/opendart-model/schema=v{schema_version}/manifest.json",
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        overwrite=True,
        content_type="application/json",
    )
    return payload


def audit_opendart_processed(
    storage,
    *,
    processed_container: str,
    schema_version: str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """OpenDART Processed manifest의 범위·품질·PIT 안전 플래그를 검증한다."""

    path = f"_manifests/opendart-model/schema=v{schema_version}/manifest.json"
    if not storage.exists(processed_container, path):
        raise RuntimeError("OpenDART processed manifest not found")
    manifest = json.loads(storage.download_bytes(processed_container, path))
    disclosure = manifest["disclosure"]
    financial = manifest["financial"]
    disclosure_months = {
        (int(item["year"]), int(item["month"]))
        for item in disclosure["partitions"]
    }
    expected_months: set[tuple[int, int]] = set()
    cursor = start_date.replace(day=1)
    while cursor <= end_date:
        expected_months.add((cursor.year, cursor.month))
        cursor = (
            cursor.replace(year=cursor.year + 1, month=1)
            if cursor.month == 12
            else cursor.replace(month=cursor.month + 1)
        )
    missing_months = sorted(expected_months - disclosure_months)
    invalid_payloads = sum(
        int(item.get("invalid_payloads", 0))
        for group in (financial, disclosure)
        for item in group["partitions"]
    )
    if missing_months or invalid_payloads:
        raise RuntimeError(
            "OpenDART processed audit failed "
            f"missing_disclosure_months={missing_months} "
            f"invalid_payloads={invalid_payloads}"
        )
    if financial.get("point_in_time_join_ready") is not False:
        raise RuntimeError("OpenDART financial must remain blocked from PIT join")
    result = {
        "status": "ok",
        "schema_version": schema_version,
        "requested_start": start_date.isoformat(),
        "requested_end": end_date.isoformat(),
        "financial_rows": int(financial["rows"]),
        "disclosure_rows": int(disclosure["rows"]),
        "disclosure_months": len(disclosure_months),
        "financial_point_in_time_join_ready": False,
    }
    print("OPENDART PROCESSED AUDIT OK " + json.dumps(result, ensure_ascii=False))
    return result
