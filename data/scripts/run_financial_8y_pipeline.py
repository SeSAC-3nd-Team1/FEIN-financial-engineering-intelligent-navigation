"""2018-01-01부터 KRX·ECOS·OpenDART를 한 번에 준비하는 상위 실행기다."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from dotenv import load_dotenv

from db.connection.session import PROJECT_ROOT
from storage import BlobStorage


DEFAULT_START_DATE = date(2018, 1, 1)
DEFAULT_SCHEMA_VERSION = "2"
DEFAULT_FEATURE_VERSION = "2"
CHECKPOINT_DIR = PROJECT_ROOT / "reports" / "checkpoints"
REPORT_DIR = PROJECT_ROOT / "reports" / "pipeline-runs"
STATE_PATH = CHECKPOINT_DIR / "financial-8y-state.json"
KRX_CHECKPOINT_PATH = CHECKPOINT_DIR / "financial-8y-krx.json"
REQUIRED_ENV = (
    "DATABASE_URL",
    "KRX_AUTH_KEY",
    "ECOS_API_KEY",
    "OPENDART_API_KEY",
    "AZURE_STORAGE_ACCOUNT_NAME",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and prepare FE!N financial data from 2018-01-01"
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--schema-version", default=DEFAULT_SCHEMA_VERSION)
    parser.add_argument("--feature-version", default=DEFAULT_FEATURE_VERSION)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="완료 checkpoint를 무시하고 ECOS/OpenDART 전체 기간을 다시 조회한다.",
    )
    parser.add_argument("--skip-krx", action="store_true")
    parser.add_argument("--skip-ecos", action="store_true")
    parser.add_argument("--skip-opendart", action="store_true")
    return parser


def _load_state() -> dict[str, Any]:
    """성공한 source 구간만 저장한 상위 pipeline 상태를 읽는다."""

    if not STATE_PATH.exists():
        return {}
    payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid pipeline state: {STATE_PATH}")
    return payload


def _save_state(state: dict[str, Any]) -> None:
    """source 성공 직후 상태를 원자적으로 기록해 다음 실행의 증분 기준으로 사용한다."""

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(STATE_PATH)


def _validate_environment() -> dict[str, str]:
    """외부 호출 전에 API key·DB·Azure Blob 설정과 Blob 접근권한을 빠르게 확인한다."""

    missing = [name for name in REQUIRED_ENV if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError(
            "financial-8y preflight missing environment variables: " + ", ".join(missing)
        )
    storage = BlobStorage.from_env()
    raw_container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    # 실제 네트워크 요청을 발생시켜 DefaultAzureCredential이 현재 실행 환경에서 유효한지 확인한다.
    storage.service_client.get_container_client(raw_container).get_container_properties()
    return {
        "storage_account": os.environ["AZURE_STORAGE_ACCOUNT_NAME"],
        "raw_container": raw_container,
        "processed_container": os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED", "processed"),
        "features_container": os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features"),
    }


def _run_step(name: str, module: str, arguments: list[str]) -> dict[str, Any]:
    """하위 CLI를 같은 Python 환경에서 실행하고 실패 시 즉시 전체 pipeline을 중단한다."""

    command = [sys.executable, "-m", module, *arguments]
    started = time.monotonic()
    print(f"FINANCIAL 8Y START step={name} module={module}")
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    elapsed = round(time.monotonic() - started, 3)
    print(f"FINANCIAL 8Y COMPLETE step={name} elapsed_seconds={elapsed}")
    return {"name": name, "module": module, "elapsed_seconds": elapsed, "status": "success"}


def _incremental_start(
    state: dict[str, Any],
    source: str,
    baseline: date,
    *,
    refresh: bool,
) -> date:
    """첫 실행은 2018년부터, 이후에는 직전 성공 종료일부터 다시 확인한다."""

    if refresh:
        return baseline
    value = state.get(source, {}).get("last_success_end")
    if not value:
        return baseline
    previous = date.fromisoformat(str(value))
    return max(baseline, previous)


def _write_report(
    *,
    start_date: date,
    end_date: date,
    storage: dict[str, str],
    steps: list[dict[str, Any]],
    state: dict[str, Any],
) -> None:
    """실행 후 사람이 확인할 Markdown과 기계용 JSON 최신 리포트를 함께 남긴다."""

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "requested_start_date": start_date.isoformat(),
        "requested_end_date": end_date.isoformat(),
        "storage": storage,
        "steps": steps,
        "state": state,
        "excluded_for_later": [
            "foreign_institutional_flow",
            "kospi200_historical_membership",
            "fred_and_overseas_macro",
        ],
    }
    (REPORT_DIR / "financial-8y-latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Financial 8Y Pipeline",
        "",
        f"- 범위: {start_date.isoformat()} ~ {end_date.isoformat()}",
        f"- Azure Storage: {storage['storage_account']}",
        f"- Raw / Processed / Features: {storage['raw_container']} / {storage['processed_container']} / {storage['features_container']}",
        "",
        "## 실행 결과",
        "",
    ]
    for step in steps:
        lines.append(
            f"- {step['name']}: {step['status']} ({step['elapsed_seconds']}s)"
        )
    lines.extend(
        [
            "",
            "## 이번 범위에서 제외",
            "",
            "- 외국인·기관 수급",
            "- KOSPI200 과거 구성종목 이력",
            "- FRED 및 해외 거시·지수",
            "",
            "OpenDART는 원문 Raw와 PostgreSQL 정규화 원장을 우선 구축하며, 공시 접수시각을 이용한 Point-in-Time Feature 결합은 별도 버전에서 수행한다.",
        ]
    )
    (REPORT_DIR / "financial-8y-latest.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    """KRX → KRX 파생 → ECOS → OpenDART 순으로 8년 이상 데이터 준비를 실행한다."""

    load_dotenv(PROJECT_ROOT.parent / ".env", override=False)
    args = _parser().parse_args(argv)
    if args.start_date > args.end_date:
        raise SystemExit("--start-date must not be after --end-date")
    if args.start_date != DEFAULT_START_DATE:
        print(
            "FINANCIAL 8Y NOTICE project baseline is "
            f"{DEFAULT_START_DATE.isoformat()}, requested={args.start_date.isoformat()}"
        )

    storage = _validate_environment()
    state = _load_state()
    steps: list[dict[str, Any]] = []
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    if not args.skip_krx:
        steps.append(
            _run_step(
                "krx_raw_and_serving",
                "scripts.sync_krx",
                [
                    "--start-date",
                    args.start_date.isoformat(),
                    "--end-date",
                    args.end_date.isoformat(),
                    "--checkpoint",
                    str(KRX_CHECKPOINT_PATH.relative_to(PROJECT_ROOT)),
                ],
            )
        )
        steps.append(
            _run_step(
                "krx_processed_features_audit",
                "scripts.run_krx_history_pipeline",
                [
                    "--stage",
                    "all",
                    "--start-date",
                    args.start_date.isoformat(),
                    "--end-date",
                    args.end_date.isoformat(),
                    "--schema-version",
                    args.schema_version,
                    "--feature-version",
                    args.feature_version,
                ],
            )
        )
        state["krx"] = {
            "last_success_end": args.end_date.isoformat(),
            "feature_version": args.feature_version,
        }
        _save_state(state)

    if not args.skip_ecos:
        ecos_start = _incremental_start(
            state, "ecos", args.start_date, refresh=args.refresh
        )
        ecos_arguments = [
            "--stage",
            "all",
            "--start-date",
            ecos_start.isoformat(),
            "--end-date",
            args.end_date.isoformat(),
            "--validate-metadata",
            "--schema-version",
            args.schema_version,
            "--feature-version",
            args.feature_version,
        ]
        # 첫 전체 백필 이후에는 마지막 Raw 시점 다음 값만 provider에서 요청한다.
        if state.get("ecos") and not args.refresh:
            ecos_arguments.append("--incremental")
        steps.append(_run_step("ecos_raw_processed_features", "scripts.run_ecos_pipeline", ecos_arguments))
        state["ecos"] = {
            "last_success_end": args.end_date.isoformat(),
            "feature_version": args.feature_version,
        }
        _save_state(state)

    if not args.skip_opendart:
        dart_start = _incremental_start(
            state, "opendart", args.start_date, refresh=args.refresh
        )
        steps.append(
            _run_step(
                "opendart_raw_and_serving",
                "scripts.backfill_opendart_8y",
                [
                    "--start-date",
                    dart_start.isoformat(),
                    "--end-date",
                    args.end_date.isoformat(),
                ],
            )
        )
        state["opendart"] = {"last_success_end": args.end_date.isoformat()}
        _save_state(state)

    _write_report(
        start_date=args.start_date,
        end_date=args.end_date,
        storage=storage,
        steps=steps,
        state=state,
    )
    print(
        "FINANCIAL 8Y SUCCESS "
        f"range={args.start_date.isoformat()}..{args.end_date.isoformat()} "
        "report=reports/pipeline-runs/financial-8y-latest.md"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
