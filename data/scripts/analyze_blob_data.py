"""Docker data 컨테이너에서 Azure Blob Raw EDA를 실행한다."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from analysis.blob_eda import build_analysis, load_profiles, render_markdown
from scripts.profile_raw_data import profile_dataset, render_markdown as render_profile_markdown
from storage import BlobStorage


def _discover_datasets(storage: BlobStorage, container: str) -> list[str]:
    """canonical Raw prefix를 기준으로 현재 Blob에 존재하는 dataset 이름을 찾는다."""

    datasets: set[str] = set()
    for path in storage.list_paths(container, prefix="data-go-kr/"):
        parts = path.split("/", 2)
        if len(parts) >= 2 and parts[0] == "data-go-kr" and parts[1]:
            datasets.add(parts[1])
    return sorted(datasets)


def _write_profile_cache(profile: dict, output_dir: Path) -> None:
    """Live 프로파일은 Git 추적 파일 대신 ignored exports 아래에 보관한다."""

    cache_dir = output_dir / "profiles"
    cache_dir.mkdir(parents=True, exist_ok=True)
    dataset = str(profile["dataset"])
    (cache_dir / f"{dataset}.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (cache_dir / f"{dataset}.md").write_text(
        render_profile_markdown(profile),
        encoding="utf-8",
    )


def _refresh_profiles(args: argparse.Namespace) -> list[dict]:
    """Azure Blob을 직접 읽어 선택 dataset의 최신 Raw profile을 생성한다."""

    storage = BlobStorage.from_env()
    container = os.getenv("AZURE_STORAGE_CONTAINER_RAW", "raw")
    datasets = sorted(set(args.dataset or _discover_datasets(storage, container)))
    if not datasets:
        raise RuntimeError("no canonical Raw datasets found in Azure Blob Storage")

    profiles: list[dict] = []
    for dataset in datasets:
        profile = profile_dataset(
            storage,
            container=container,
            dataset=dataset,
            unique_cap=args.unique_cap,
            example_cap=args.example_cap,
        )
        _write_profile_cache(profile, args.output_dir)
        profiles.append(profile)
    return profiles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", action="append", help="분석할 dataset. 여러 번 지정 가능")
    parser.add_argument("--refresh-profile", action="store_true", help="Azure Blob을 직접 다시 프로파일링")
    parser.add_argument("--profile-dir", type=Path, default=Path("reports/raw-profile"))
    parser.add_argument("--output-dir", type=Path, default=Path("exports/blob-eda"))
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--high-missing-threshold", type=float, default=0.5)
    parser.add_argument("--unique-cap", type=int, default=20_000)
    parser.add_argument("--example-cap", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    if args.unique_cap <= 0 or args.example_cap <= 0:
        raise ValueError("caps must be positive")

    profiles = (
        _refresh_profiles(args)
        if args.refresh_profile
        else load_profiles(args.profile_dir, datasets=args.dataset)
    )
    analysis = build_analysis(
        profiles,
        high_missing_threshold=args.high_missing_threshold,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "summary.json"
    markdown_path = args.output_dir / "summary.md"
    json_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(analysis), encoding="utf-8")

    print(
        "BLOB EDA COMPLETE "
        f"datasets={analysis['dataset_count']} "
        f"records={analysis['total_records']} "
        f"invalid={analysis['total_invalid_count']} "
        f"report={markdown_path}"
    )


if __name__ == "__main__":
    main()
