"""2018년 coverage가 확인된 모델 Raw만 Processed/Features로 전처리한다."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from collectors.ecos_config import ECOS_SERIES
from features.ecos import build_macro_features
from processing.ecos import build_ecos_processed
from processing.model_opendart import (
    audit_opendart_processed,
    build_opendart_processed,
)
from scripts.run_ecos_pipeline import audit_outputs as audit_ecos
from scripts.run_krx_history_pipeline import (
    audit as audit_krx,
    build_features as build_krx_features,
    build_processed as build_krx_processed,
)
from storage import BlobStorage


DATA_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DATA_ROOT.parent
DEFAULT_START_DATE = date(2018, 1, 1)
SUMMARY_JSON = DATA_ROOT / "reports" / "DOYOUNG_2018_PREPROCESSING_SUMMARY.json"
SUMMARY_MARKDOWN = DATA_ROOT / "reports" / "DOYOUNG_2018_PREPROCESSING_SUMMARY.md"
SOURCE_NAMES = ("krx", "ecos", "opendart")


def _seoul_today() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preprocess only model sources with verified coverage from 2018"
    )
    parser.add_argument(
        "--stage", choices=("processed", "features", "audit", "all"), default="all"
    )
    parser.add_argument("--source", action="append", choices=SOURCE_NAMES)
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=_seoul_today())
    parser.add_argument("--schema-version", default="2")
    parser.add_argument("--feature-version", default="2")
    return parser


def _read_json(storage, container: str, path: str) -> dict[str, Any]:
    if not storage.exists(container, path):
        raise RuntimeError(f"preprocessing manifest not found: {container}/{path}")
    value = json.loads(storage.download_bytes(container, path))
    if not isinstance(value, dict):
        raise RuntimeError(f"invalid preprocessing manifest: {container}/{path}")
    return value


def _write_handoff_manifest(
    storage,
    *,
    processed_container: str,
    features_container: str,
    selected: list[str],
    start_date: date,
    end_date: date,
    schema_version: str,
    feature_version: str,
    audits: dict[str, Any],
) -> dict[str, Any]:
    """모델 담당자가 READY와 안전 제한을 한 manifest에서 확인하게 한다."""

    datasets: dict[str, Any] = {}
    if "krx" in selected:
        krx = _read_json(
            storage,
            features_container,
            f"_manifests/krx-history-features/version=v{feature_version}/manifest.json",
        )
        datasets.update({
            "model_stock_daily": {
                "layer": "features",
                "status": "training_ready",
                "rows": krx["model_stock_daily"]["rows"],
                "min_date": krx["min_trade_date"],
                "max_date": krx["max_trade_date"],
                "path": f"model_stock_daily/version=v{feature_version}/",
            },
            "market_index_daily": {
                "layer": "features",
                "status": "training_ready",
                "rows": krx["market_index_daily"]["rows"],
                "min_date": krx["min_trade_date"],
                "max_date": krx["max_trade_date"],
                "path": f"market_index_daily/version=v{feature_version}/",
            },
        })
    if "ecos" in selected:
        ecos = _read_json(
            storage,
            features_container,
            f"_manifests/ecos/version=v{feature_version}/manifest.json",
        )
        datasets["macro_daily"] = {
            "layer": "features",
            "status": "training_ready_pit_conservative",
            "rows": ecos["rows"],
            "min_date": ecos["min_date"],
            "max_date": ecos["max_date"],
            "path": f"macro_daily/version=v{feature_version}/",
            "point_in_time_policy": ecos["point_in_time_policy"],
        }
    if "opendart" in selected:
        dart = _read_json(
            storage,
            processed_container,
            f"_manifests/opendart-model/schema=v{schema_version}/manifest.json",
        )
        datasets.update({
            "opendart_disclosures": {
                "layer": "processed",
                "status": "event_ready",
                "rows": dart["disclosure"]["rows"],
                "path": (
                    "opendart_disclosures/operation=disclosure_market/"
                    f"schema=v{schema_version}/"
                ),
            },
            "opendart_financial_accounts": {
                "layer": "processed",
                "status": "research_only_until_receipt_linkage",
                "rows": dart["financial"]["rows"],
                "path": (
                    "opendart_financial_accounts/operation=financial_multi/"
                    f"schema=v{schema_version}/"
                ),
                "point_in_time_join_ready": False,
            },
        })

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "schema_version": schema_version,
        "feature_version": feature_version,
        "selected_sources": selected,
        "datasets": datasets,
        "audits": audits,
        "excluded_no_2018_coverage": [
            "foreign_institutional_flow",
            "vix_vkospi",
            "sox_overseas_sector_index",
            "sp500_nasdaq",
            "historical_transaction_cost_and_spread",
        ],
        "safety": {
            "opendart_financial_price_join": "blocked_until_receipt_linkage",
            "corporate_action_adjusted_price": "not_available",
            "target_columns_are_not_model_inputs": True,
        },
    }
    storage.upload_bytes(
        features_container,
        f"_manifests/doyoung-2018/version=v{feature_version}/manifest.json",
        json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        overwrite=True,
        content_type="application/json",
    )
    return payload


def _write_local_summary(payload: dict[str, Any]) -> None:
    """실제 Azure manifest와 같은 내용을 Git 전달용 JSON/Markdown으로 기록한다."""

    SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 정도영 2018 모델 데이터 전처리 결과",
        "",
        f"- 요청 기간: {payload['requested_range']['start']} ~ {payload['requested_range']['end']}",
        f"- Processed schema: v{payload['schema_version']}",
        f"- Feature version: v{payload['feature_version']}",
        "",
        "## Dataset",
        "",
        "| dataset | layer | status | rows | path |",
        "|---|---|---|---:|---|",
    ]
    for name, value in payload["datasets"].items():
        lines.append(
            f"| `{name}` | {value['layer']} | `{value['status']}` | "
            f"{int(value['rows']):,} | `{value['path']}` |"
        )
    lines.extend([
        "",
        "## 안전 제한",
        "",
        "- OpenDART 재무는 접수번호·접수일 연결 전까지 가격 학습 데이터에 JOIN하지 않는다.",
        "- 현재 KRX 가격은 corporate action 조정계열이 아니므로 배당·분할 이벤트 보강이 필요하다.",
        "- `target_*` 컬럼은 Feature 입력에서 제외한다.",
        "",
        "## 2018 coverage 미확보로 제외",
        "",
    ])
    lines.extend(f"- `{name}`" for name in payload["excluded_no_2018_coverage"])
    SUMMARY_MARKDOWN.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """선택 source를 Processed→Features→Audit 순서로 안전하게 실행한다."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    args = _parser().parse_args(argv)
    if args.start_date != DEFAULT_START_DATE:
        raise SystemExit("model preprocessing start date must be 2018-01-01")
    if args.end_date < args.start_date:
        raise SystemExit("--end-date must not be before 2018-01-01")
    selected = args.source or list(SOURCE_NAMES)
    storage = BlobStorage.from_env()
    raw_container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    processed_container = os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED", "processed")
    features_container = os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features")
    audits: dict[str, Any] = {}

    if args.stage in {"processed", "all"}:
        if "krx" in selected:
            build_krx_processed(
                storage,
                raw_container=raw_container,
                processed_container=processed_container,
                start_date=args.start_date,
                end_date=args.end_date,
                schema_version=args.schema_version,
            )
        if "ecos" in selected:
            for name in ECOS_SERIES:
                build_ecos_processed(
                    storage,
                    raw_container=raw_container,
                    processed_container=processed_container,
                    series_name=name,
                    schema_version=args.schema_version,
                    overwrite=True,
                )
        if "opendart" in selected:
            build_opendart_processed(
                storage,
                raw_container=raw_container,
                processed_container=processed_container,
                start_date=args.start_date,
                end_date=args.end_date,
                schema_version=args.schema_version,
            )

    if args.stage in {"features", "all"}:
        if "krx" in selected:
            build_krx_features(
                storage,
                processed_container=processed_container,
                features_container=features_container,
                schema_version=args.schema_version,
                feature_version=args.feature_version,
            )
        if "ecos" in selected:
            build_macro_features(
                storage,
                processed_container=processed_container,
                features_container=features_container,
                schema_version=args.schema_version,
                feature_version=args.feature_version,
                overwrite=True,
            )
        if "opendart" in selected:
            print("OPENDART FEATURES SKIP financial receipt linkage is not ready")

    if args.stage in {"audit", "all"}:
        if "krx" in selected:
            audits["krx"] = audit_krx(
                storage,
                features_container=features_container,
                feature_version=args.feature_version,
                start_date=args.start_date,
                end_date=args.end_date,
            )
        if "ecos" in selected:
            audits["ecos"] = audit_ecos(
                storage,
                processed_container=processed_container,
                features_container=features_container,
                series_names=list(ECOS_SERIES),
                schema_version=args.schema_version,
                feature_version=args.feature_version,
            )
            ecos_manifest = _read_json(
                storage,
                features_container,
                f"_manifests/ecos/version=v{args.feature_version}/manifest.json",
            )
            ecos_first = date.fromisoformat(str(ecos_manifest["min_date"]))
            ecos_last = date.fromisoformat(str(ecos_manifest["max_date"]))
            if (
                (ecos_first - args.start_date).days > 7
                or (args.end_date - ecos_last).days > 7
            ):
                raise RuntimeError(
                    "ECOS feature coverage incomplete: "
                    f"requested={args.start_date}..{args.end_date} "
                    f"actual={ecos_first}..{ecos_last}"
                )
            audits["ecos"].update({
                "status": "ok",
                "actual_start": ecos_first.isoformat(),
                "actual_end": ecos_last.isoformat(),
            })
        if "opendart" in selected:
            audits["opendart"] = audit_opendart_processed(
                storage,
                processed_container=processed_container,
                schema_version=args.schema_version,
                start_date=args.start_date,
                end_date=args.end_date,
            )
        payload = _write_handoff_manifest(
            storage,
            processed_container=processed_container,
            features_container=features_container,
            selected=selected,
            start_date=args.start_date,
            end_date=args.end_date,
            schema_version=args.schema_version,
            feature_version=args.feature_version,
            audits=audits,
        )
        _write_local_summary(payload)
        print(
            "MODEL 2018 PREPROCESSING SUCCESS "
            f"datasets={len(payload['datasets'])} "
            f"manifest=_manifests/doyoung-2018/version=v{args.feature_version}/manifest.json"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
