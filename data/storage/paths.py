"""Azure Blob의 Raw/Processed/Features 경로 규칙을 한 곳에서 관리한다."""

from __future__ import annotations

import re
from datetime import date


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _segment(value: str) -> str:
    """사용자/외부 입력을 Blob path segment에 안전한 형태로 정규화한다."""

    cleaned = _UNSAFE.sub("-", value.strip()).strip("-.")
    if not cleaned:
        raise ValueError("blob path segment must contain a safe character")
    return cleaned.lower()


def _version(value: str) -> str:
    """schema/feature version에 경로 구분자를 포함하지 못하게 제한한다."""

    cleaned = value.strip()
    if not cleaned or any(ch not in "0123456789._-" for ch in cleaned):
        raise ValueError("version contains unsafe characters")
    return cleaned


def build_raw_path(
    *,
    source: str,
    dataset: str,
    operation: str,
    partition_date: date,
    batch_hash: str,
) -> str:
    """canonical Raw monthly path를 생성한다.

    Raw는 ``source/dataset/operation/year/month/hash`` 구조만 허용한다. 날짜의 day 값이나
    API page 번호를 경로에 넣지 않고, 동일 payload batch가 항상 같은 경로를 갖도록
    SHA-256 ``batch_hash``를 파일명으로 사용한다.
    """

    if not re.fullmatch(r"[0-9a-fA-F]{64}", batch_hash):
        raise ValueError("batch_hash must be a SHA-256 hex digest")
    return (
        f"{_segment(source)}/{_segment(dataset)}/operation={_segment(operation)}/"
        f"year={partition_date:%Y}/month={partition_date:%m}/{batch_hash.lower()}.jsonl.gz"
    )


def build_processed_path(
    dataset: str,
    *,
    partition_date: date,
    schema_version: str,
    operation: str | None = None,
    file_name: str = "part-00000.parquet",
) -> str:
    """재생성 가능한 Processed Parquet의 schema version + 월 경로를 만든다.

    신규 금융 파이프라인은 서로 다른 API schema가 섞이지 않도록 ``operation``을 반드시
    전달한다. ``operation=None``은 기존 호출부 호환을 위해 유지하지만 신규 코드는 사용하지 않는다.
    """

    operation_part = f"operation={_segment(operation)}/" if operation else ""
    return (
        f"{_segment(dataset)}/{operation_part}schema=v{_version(schema_version)}/"
        f"year={partition_date:%Y}/month={partition_date:%m}/{_segment(file_name)}"
    )


def build_feature_path(
    dataset: str,
    *,
    partition_date: date,
    version: str,
    file_name: str = "part-00000.parquet",
) -> str:
    """Feature 계산 버전과 월을 포함한 경로를 만든다."""

    return (
        f"{_segment(dataset)}/version=v{_version(version)}/"
        f"year={partition_date:%Y}/month={partition_date:%m}/{_segment(file_name)}"
    )
