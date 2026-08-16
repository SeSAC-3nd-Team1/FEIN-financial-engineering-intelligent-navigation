"""Raw 분석부터 Processed/Features/감사까지 한 CLI에서 단계별로 실행한다.

실제 대용량 데이터 실행은 개발자 로컬 Docker에서 수행한다. 이 모듈은 실행 전 연결 점검,
Raw profile 재사용, 단계별 결과 기록을 제공해 긴 작업이 중단돼도 필요한 단계부터 재개할 수 있게 한다.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

import features.model_dataset as model_dataset
from features.runtime_loader import load_processed_operation_compact
from processing.processed_builder import build_processed_dataset
from scripts.audit_model_data_outputs import (
    audit_features,
    audit_processed,
    render_audit_markdown,
)
from scripts.profile_raw_data import profile_dataset, render_markdown
from storage import BlobStorage

DATASETS = [
    "disclosure",
    "financial_statement",
    "market_index",
    "security_product",
    "stock_dividend",
    "stock_issuance",
    "stock_master",
    "stock_price",
]
STAGES = ("check", "profile", "processed", "features", "audit", "all")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="한투 API를 제외한 금융 데이터 파이프라인을 단계별로 실행한다."
    )
    parser.add_argument("--stage", choices=STAGES, default="check")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path("reports/raw-profile"),
    )
    parser.add_argument(
        "--run-report-dir",
        type=Path,
        default=Path("reports/pipeline-runs"),
    )
    parser.add_argument("--dataset", action="append", choices=DATASETS)
    parser.add_argument("--schema-version", default="1")
    parser.add_argument("--feature-version", default="1")
    parser.add_argument("--unique-cap", type=int, default=20_000)
    parser.add_argument("--example-cap", type=int, default=5)
    parser.add_argument(
        "--refresh-profile",
        action="store_true",
        help="기존 profile JSON/Markdown이 있어도 Raw를 다시 전수 분석한다.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="동일 version의 Processed/Features Blob을 다시 생성한다.",
    )
    return parser.parse_args()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_version(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or any(ch not in "0123456789._-" for ch in cleaned):
        raise ValueError("version contains unsafe characters")
    return cleaned


def _check_container(storage: BlobStorage, container: str) -> None:
    """실행 전에 container 존재와 현재 Entra ID의 최소 조회 권한을 확인한다."""

    storage.service_client.get_container_client(container).get_container_properties()


def check_ready(
    storage: BlobStorage,
    *,
    raw_container: str,
    processed_container: str,
    features_container: str,
    datasets: list[str],
) -> dict[str, Any]:
    """대용량 payload를 내려받지 않고 실제 실행에 필요한 Azure 접근만 점검한다."""

    for container in (raw_container, processed_container, features_container):
        _check_container(storage, container)

    raw_client = storage.service_client.get_container_client(raw_container)
    raw_presence: dict[str, bool] = {}
    for dataset in datasets:
        prefix = f"data-go-kr/{dataset}/operation="
        raw_presence[dataset] = next(
            iter(raw_client.list_blobs(name_starts_with=prefix)),
            None,
        ) is not None

    missing = [dataset for dataset, exists in raw_presence.items() if not exists]
    if missing:
        raise RuntimeError(f"canonical Raw dataset not found: {missing}")

    result = {
        "checked_at": _utc_now(),
        "containers": {
            "raw": raw_container,
            "processed": processed_container,
            "features": features_container,
        },
        "raw_dataset_present": raw_presence,
    }
    print("PIPELINE CHECK OK " + json.dumps(result, ensure_ascii=False))
    return result


def _profile_path(profile_dir: Path, dataset: str) -> Path:
    return profile_dir / f"{dataset}.json"


def _load_profile(profile_dir: Path, dataset: str) -> dict[str, Any]:
    path = _profile_path(profile_dir, dataset)
    if not path.is_file():
        raise FileNotFoundError(
            f"profile report not found: {path}; run --stage profile first"
        )
    profile = json.loads(path.read_text(encoding="utf-8"))
    if profile.get("dataset") != dataset:
        raise RuntimeError(f"profile dataset mismatch: expected={dataset} path={path}")
    return profile


def _write_profile(
    profile_dir: Path,
    dataset: str,
    profile: dict[str, Any],
) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)
    _profile_path(profile_dir, dataset).write_text(
        json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (profile_dir / f"{dataset}.md").write_text(
        render_markdown(profile),
        encoding="utf-8",
    )


def _render_profile_index(profiles: list[dict[str, Any]]) -> str:
    lines = [
        "# Raw Profile Index",
        "",
        "실제 Azure canonical Raw의 `payload`를 기준으로 생성한 프로파일 목록이다.",
        "",
        "| dataset | blobs | records | operations | compressed bytes |",
        "|---|---:|---:|---:|---:|",
    ]
    for profile in profiles:
        lines.append(
            f"| `{profile['dataset']}` | {profile['total_blobs']:,} | "
            f"{profile['total_rows']:,} | {len(profile['operations'])} | "
            f"{profile['compressed_bytes']:,} |"
        )
    lines.extend(
        [
            "",
            f"- total blobs: **{sum(item['total_blobs'] for item in profiles):,}**",
            f"- total records: **{sum(item['total_rows'] for item in profiles):,}**",
            "",
            "각 dataset의 컬럼/NULL/빈값/숫자·날짜 변환 가능성/예시값은 같은 디렉터리의 개별 Markdown을 확인한다.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_profiles(
    storage: BlobStorage,
    *,
    raw_container: str,
    datasets: list[str],
    profile_dir: Path,
    unique_cap: int,
    example_cap: int,
    refresh: bool,
) -> list[dict[str, Any]]:
    """profile이 있으면 재사용하고, 없거나 refresh 요청 시에만 Raw를 다시 읽는다."""

    profiles: list[dict[str, Any]] = []
    for dataset in datasets:
        existing = _profile_path(profile_dir, dataset)
        if existing.is_file() and not refresh:
            profile = _load_profile(profile_dir, dataset)
            print(
                f"PROFILE REUSE dataset={dataset} blobs={profile['total_blobs']} "
                f"rows={profile['total_rows']}"
            )
        else:
            profile = profile_dataset(
                storage,
                container=raw_container,
                dataset=dataset,
                unique_cap=unique_cap,
                example_cap=example_cap,
            )
            _write_profile(profile_dir, dataset, profile)
            print(
                f"PROFILE COMPLETE dataset={dataset} blobs={profile['total_blobs']} "
                f"rows={profile['total_rows']} operations={len(profile['operations'])}"
            )
        profiles.append(profile)

    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "INDEX.md").write_text(
        _render_profile_index(profiles),
        encoding="utf-8",
    )
    return profiles


def build_processed(
    storage: BlobStorage,
    *,
    raw_container: str,
    processed_container: str,
    datasets: list[str],
    profile_dir: Path,
    schema_version: str,
    overwrite: bool,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for dataset in datasets:
        summaries.append(
            build_processed_dataset(
                storage,
                raw_container=raw_container,
                processed_container=processed_container,
                dataset=dataset,
                profile=_load_profile(profile_dir, dataset),
                schema_version=schema_version,
                overwrite=overwrite,
            )
        )
    print("PROCESSED COMPLETE " + json.dumps(summaries, ensure_ascii=False))
    return summaries


def build_features(
    storage: BlobStorage,
    *,
    processed_container: str,
    features_container: str,
    schema_version: str,
    feature_version: str,
    overwrite: bool,
) -> dict[str, Any]:
    # 모델 계산 단계에서는 row-level lineage 문자열을 제거한 compact loader를 사용해
    # 수백만 행에서 발생하는 메모리 사용량을 줄인다. lineage는 Processed manifest에 보존된다.
    model_dataset.load_processed_operation = load_processed_operation_compact
    result = model_dataset.build_model_datasets(
        storage,
        processed_container=processed_container,
        features_container=features_container,
        schema_version=schema_version,
        feature_version=feature_version,
        overwrite=overwrite,
    )
    print("FEATURE DATASETS COMPLETE " + json.dumps(result, ensure_ascii=False))
    return result


def build_audit(
    storage: BlobStorage,
    *,
    processed_container: str,
    features_container: str,
    schema_version: str,
    feature_version: str,
) -> dict[str, Any]:
    payload = {
        "generated_at": _utc_now(),
        "processed": audit_processed(storage, processed_container, schema_version),
        "features": audit_features(storage, features_container, feature_version),
    }
    print("PIPELINE AUDIT COMPLETE " + json.dumps(payload, ensure_ascii=False))
    return payload


def _render_run_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Financial Data Pipeline Run",
        "",
        f"- status: **{payload['status']}**",
        f"- stage: `{payload['stage']}`",
        f"- started_at: `{payload['started_at']}`",
        f"- finished_at: `{payload.get('finished_at', '-')}`",
        f"- schema_version: `v{payload['schema_version']}`",
        f"- feature_version: `v{payload['feature_version']}`",
        f"- datasets: `{', '.join(payload['datasets'])}`",
    ]
    if payload.get("error"):
        lines.extend(["", "## Error", "", f"`{payload['error']}`"])
    if payload.get("audit"):
        lines.extend(["", render_audit_markdown(payload["audit"]).strip()])
    return "\n".join(lines) + "\n"


def _write_run_report(directory: Path, payload: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    rendered_json = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    rendered_md = _render_run_markdown(payload)
    (directory / "latest.json").write_text(rendered_json, encoding="utf-8")
    (directory / "latest.md").write_text(rendered_md, encoding="utf-8")


def main() -> None:
    args = parse_args()
    if args.env_file:
        if not args.env_file.is_file():
            raise FileNotFoundError(f"env file not found: {args.env_file}")
        load_dotenv(args.env_file, override=False)
    if args.unique_cap <= 0 or args.example_cap <= 0:
        raise ValueError("caps must be positive")

    schema_version = _safe_version(args.schema_version)
    feature_version = _safe_version(args.feature_version)
    selected = args.dataset or DATASETS
    storage = BlobStorage.from_env()
    raw_container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    processed_container = os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED", "processed")
    features_container = os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features")

    run: dict[str, Any] = {
        "status": "running",
        "stage": args.stage,
        "started_at": _utc_now(),
        "schema_version": schema_version,
        "feature_version": feature_version,
        "datasets": selected,
        "overwrite": args.overwrite,
        "refresh_profile": args.refresh_profile,
    }
    _write_run_report(args.run_report_dir, run)

    try:
        if args.stage in ("check", "all"):
            run["check"] = check_ready(
                storage,
                raw_container=raw_container,
                processed_container=processed_container,
                features_container=features_container,
                datasets=selected,
            )
            _write_run_report(args.run_report_dir, run)

        if args.stage in ("profile", "all"):
            profiles = build_profiles(
                storage,
                raw_container=raw_container,
                datasets=selected,
                profile_dir=args.profile_dir,
                unique_cap=args.unique_cap,
                example_cap=args.example_cap,
                refresh=args.refresh_profile,
            )
            run["profile"] = {
                "datasets": len(profiles),
                "blobs": sum(item["total_blobs"] for item in profiles),
                "records": sum(item["total_rows"] for item in profiles),
            }
            _write_run_report(args.run_report_dir, run)

        if args.stage in ("processed", "all"):
            processed = build_processed(
                storage,
                raw_container=raw_container,
                processed_container=processed_container,
                datasets=selected,
                profile_dir=args.profile_dir,
                schema_version=schema_version,
                overwrite=args.overwrite,
            )
            run["processed"] = processed
            _write_run_report(args.run_report_dir, run)

        if args.stage in ("features", "all"):
            run["features"] = build_features(
                storage,
                processed_container=processed_container,
                features_container=features_container,
                schema_version=schema_version,
                feature_version=feature_version,
                overwrite=args.overwrite,
            )
            _write_run_report(args.run_report_dir, run)

        if args.stage in ("audit", "all"):
            run["audit"] = build_audit(
                storage,
                processed_container=processed_container,
                features_container=features_container,
                schema_version=schema_version,
                feature_version=feature_version,
            )

        run["status"] = "success"
        run["finished_at"] = _utc_now()
        _write_run_report(args.run_report_dir, run)
        print(f"PIPELINE {args.stage.upper()} SUCCESS report={args.run_report_dir / 'latest.md'}")
    except Exception as exc:
        run["status"] = "failed"
        run["finished_at"] = _utc_now()
        run["error"] = f"{type(exc).__name__}: {exc}"
        _write_run_report(args.run_report_dir, run)
        raise


if __name__ == "__main__":
    main()
