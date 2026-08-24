"""Raw profile 결과를 dataset 수준 EDA 지표로 요약한다."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class DatasetSummary:
    """Blob Raw dataset 하나의 핵심 품질·규모·시간축 지표다."""

    dataset: str
    operations: int
    blobs: int
    records: int
    compressed_bytes: int
    min_basdt: str | None
    max_basdt: str | None
    temporal_shape: str
    invalid_count: int
    high_missing_fields: int
    all_empty_fields: int
    top_operation: str | None
    top_operation_rows: int
    top_operation_share: float
    records_per_blob: float
    compressed_bytes_per_record: float

    @property
    def quality_passed(self) -> bool:
        """Raw envelope/기준일 수준의 구조 오류가 없으면 통과로 본다."""

        return self.invalid_count == 0


def _validate_threshold(high_missing_threshold: float) -> None:
    if not 0.0 < high_missing_threshold <= 1.0:
        raise ValueError("high_missing_threshold must be in (0, 1]")


def _classify_temporal_shape(operations: dict[str, Any]) -> str:
    """operation별 basDt 범위를 보고 snapshot/history/mixed를 구분한다."""

    has_snapshot = False
    has_history = False
    has_date = False

    for stats in operations.values():
        min_basdt = stats.get("min_basdt")
        max_basdt = stats.get("max_basdt")
        if not min_basdt or not max_basdt:
            continue
        has_date = True
        if min_basdt == max_basdt:
            has_snapshot = True
        else:
            has_history = True

    if not has_date:
        return "unknown"
    if has_snapshot and has_history:
        return "mixed"
    if has_history:
        return "history"
    return "snapshot"


def summarize_profile(
    profile: dict[str, Any],
    *,
    high_missing_threshold: float = 0.5,
) -> DatasetSummary:
    """`profile_raw_data` JSON 하나를 EDA용 dataset summary로 변환한다."""

    _validate_threshold(high_missing_threshold)
    operations = profile.get("operations") or {}
    invalid_paths = profile.get("invalid_paths") or []

    basdt_min_values: list[str] = []
    basdt_max_values: list[str] = []
    invalid_count = len(invalid_paths)
    high_missing_fields = 0
    all_empty_fields = 0

    top_operation: str | None = None
    top_operation_rows = 0

    for operation, stats in operations.items():
        rows = int(stats.get("rows") or 0)
        if rows > top_operation_rows:
            top_operation = operation
            top_operation_rows = rows

        min_basdt = stats.get("min_basdt")
        max_basdt = stats.get("max_basdt")
        if min_basdt:
            basdt_min_values.append(str(min_basdt))
        if max_basdt:
            basdt_max_values.append(str(max_basdt))

        invalid_count += int(stats.get("malformed_json_lines") or 0)
        invalid_count += int(stats.get("invalid_payloads") or 0)
        invalid_count += int(stats.get("basdt_missing") or 0)
        invalid_count += int(stats.get("basdt_invalid") or 0)

        for field_stats in (stats.get("payload_fields") or {}).values():
            missing_rate = float(field_stats.get("null_or_empty_rate") or 0.0)
            if missing_rate >= 1.0:
                all_empty_fields += 1
            elif missing_rate >= high_missing_threshold:
                high_missing_fields += 1

    records = int(profile.get("total_rows") or 0)
    blobs = int(profile.get("total_blobs") or 0)
    compressed_bytes = int(profile.get("compressed_bytes") or 0)

    return DatasetSummary(
        dataset=str(profile.get("dataset") or "unknown"),
        operations=len(operations),
        blobs=blobs,
        records=records,
        compressed_bytes=compressed_bytes,
        min_basdt=min(basdt_min_values) if basdt_min_values else None,
        max_basdt=max(basdt_max_values) if basdt_max_values else None,
        temporal_shape=_classify_temporal_shape(operations),
        invalid_count=invalid_count,
        high_missing_fields=high_missing_fields,
        all_empty_fields=all_empty_fields,
        top_operation=top_operation,
        top_operation_rows=top_operation_rows,
        top_operation_share=round(top_operation_rows / records, 6) if records else 0.0,
        records_per_blob=round(records / blobs, 3) if blobs else 0.0,
        compressed_bytes_per_record=(
            round(compressed_bytes / records, 3) if records else 0.0
        ),
    )


def build_analysis(
    profiles: Iterable[dict[str, Any]],
    *,
    high_missing_threshold: float = 0.5,
) -> dict[str, Any]:
    """여러 Raw profile을 프로젝트 수준 EDA 결과로 묶는다."""

    _validate_threshold(high_missing_threshold)
    summaries = [
        summarize_profile(profile, high_missing_threshold=high_missing_threshold)
        for profile in profiles
    ]
    summaries.sort(key=lambda item: item.dataset)

    total_records = sum(item.records for item in summaries)
    total_blobs = sum(item.blobs for item in summaries)
    total_compressed_bytes = sum(item.compressed_bytes for item in summaries)
    total_invalid = sum(item.invalid_count for item in summaries)

    largest_by_records = max(summaries, key=lambda item: item.records, default=None)
    largest_by_storage = max(
        summaries,
        key=lambda item: item.compressed_bytes,
        default=None,
    )

    return {
        "dataset_count": len(summaries),
        "total_records": total_records,
        "total_blobs": total_blobs,
        "total_compressed_bytes": total_compressed_bytes,
        "total_invalid_count": total_invalid,
        "quality_passed_datasets": sum(item.quality_passed for item in summaries),
        "high_missing_threshold": high_missing_threshold,
        "largest_by_records": largest_by_records.dataset if largest_by_records else None,
        "largest_by_storage": largest_by_storage.dataset if largest_by_storage else None,
        "snapshot_datasets": [
            item.dataset for item in summaries if item.temporal_shape == "snapshot"
        ],
        "mixed_temporal_datasets": [
            item.dataset for item in summaries if item.temporal_shape == "mixed"
        ],
        "quality_failed_datasets": [
            item.dataset for item in summaries if not item.quality_passed
        ],
        "datasets": [
            {
                **asdict(item),
                "quality_passed": item.quality_passed,
            }
            for item in summaries
        ],
    }


def load_profiles(
    profile_dir: Path,
    *,
    datasets: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """프로파일 JSON을 읽되 INDEX/기타 JSON은 dataset 이름 기준으로 걸러낸다."""

    requested = {item.strip() for item in datasets or [] if item.strip()}
    paths = sorted(profile_dir.glob("*.json"))
    profiles: list[dict[str, Any]] = []

    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        dataset = str(payload.get("dataset") or "")
        if not dataset:
            continue
        if requested and dataset not in requested:
            continue
        profiles.append(payload)

    if requested:
        found = {str(item.get("dataset")) for item in profiles}
        missing = sorted(requested - found)
        if missing:
            raise FileNotFoundError(
                "profile JSON not found for datasets: " + ", ".join(missing)
            )
    if not profiles:
        raise FileNotFoundError(f"no profile JSON found in {profile_dir}")
    return profiles


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024.0 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    raise AssertionError("unreachable")


def render_markdown(analysis: dict[str, Any]) -> str:
    """EDA 결과를 리뷰하기 쉬운 Markdown 문서로 렌더링한다."""

    lines = [
        "# Azure Blob Raw EDA Summary",
        "",
        "## 전체 요약",
        "",
        f"- dataset: **{analysis['dataset_count']:,}개**",
        f"- Raw records: **{analysis['total_records']:,}건**",
        f"- Blob objects: **{analysis['total_blobs']:,}개**",
        f"- 압축 저장량: **{_format_bytes(analysis['total_compressed_bytes'])}**",
        f"- 구조/기준일 오류: **{analysis['total_invalid_count']:,}건**",
        f"- 품질 통과 dataset: **{analysis['quality_passed_datasets']:,}/{analysis['dataset_count']:,}**",
        f"- record 기준 최대 dataset: **{analysis['largest_by_records'] or '-'}**",
        f"- 저장량 기준 최대 dataset: **{analysis['largest_by_storage'] or '-'}**",
        "",
        "## Dataset 비교",
        "",
        "| dataset | temporal | operations | blobs | records | compressed | basDt | invalid | >= missing threshold | all-empty | top operation share |",
        "|---|---|---:|---:|---:|---:|---|---:|---:|---:|---:|",
    ]

    for item in analysis["datasets"]:
        basdt = (
            f"{item['min_basdt']} ~ {item['max_basdt']}"
            if item["min_basdt"] and item["max_basdt"]
            else "-"
        )
        lines.append(
            f"| `{item['dataset']}` | {item['temporal_shape']} | "
            f"{item['operations']:,} | {item['blobs']:,} | {item['records']:,} | "
            f"{_format_bytes(item['compressed_bytes'])} | {basdt} | "
            f"{item['invalid_count']:,} | {item['high_missing_fields']:,} | "
            f"{item['all_empty_fields']:,} | {item['top_operation_share'] * 100:.1f}% |"
        )

    lines += ["", "## 해석 포인트", ""]
    if analysis["snapshot_datasets"]:
        lines.append(
            "- snapshot 성격 dataset: "
            + ", ".join(f"`{name}`" for name in analysis["snapshot_datasets"])
            + ". `basDt`를 이벤트 발생일로 간주하지 않는다."
        )
    if analysis["mixed_temporal_datasets"]:
        lines.append(
            "- mixed 시간축 dataset: "
            + ", ".join(
                f"`{name}`" for name in analysis["mixed_temporal_datasets"]
            )
            + ". operation별 시간 의미를 분리해서 전처리한다."
        )
    if analysis["quality_failed_datasets"]:
        lines.append(
            "- 구조/기준일 오류가 발견된 dataset: "
            + ", ".join(
                f"`{name}`" for name in analysis["quality_failed_datasets"]
            )
            + ". Processed 생성 전에 원인 확인이 필요하다."
        )
    else:
        lines.append(
            "- 모든 dataset이 malformed JSON, invalid payload, basDt 누락/오류 기준을 통과했다."
        )

    threshold = analysis["high_missing_threshold"] * 100
    lines.append(
        f"- 결측률 {threshold:.0f}% 이상 필드는 자동 삭제 대상이 아니다. operation 의미를 확인한 뒤 유지/제외를 결정한다."
    )
    return "\n".join(lines) + "\n"
