"""모델 Feature 계산용 경량 Processed loader.

Processed에는 감사 추적을 위해 row-level lineage를 보존하지만, 수백만 행 Feature 계산 중에는
문자열 lineage가 큰 메모리를 차지한다. 모델 Dataset은 별도 manifest로 lineage를 추적하므로
Feature 계산 직전에 이 컬럼만 제거한다.
"""

from __future__ import annotations

import io
import time

import pandas as pd

_LINEAGE_COLUMNS = ("_payload_hash", "_collected_at", "_source_blob")


def _duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--:--"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _eta(elapsed: float, done: int, total: int) -> float | None:
    if done <= 0 or elapsed <= 0:
        return None
    if done >= total:
        return 0.0
    return elapsed * (total - done) / done


def load_processed_operation_compact(
    storage,
    container: str,
    dataset: str,
    operation: str,
    schema_version: str,
) -> pd.DataFrame:
    """월별 Parquet을 읽으면서 모델 계산에 불필요한 row-level lineage를 제거한다."""

    prefix = f"{dataset}/operation={operation.lower()}/schema=v{schema_version}/"
    frames: list[pd.DataFrame] = []
    client = storage.service_client.get_container_client(container)
    blobs = [
        blob
        for blob in client.list_blobs(name_starts_with=prefix)
        if str(blob.name).endswith(".parquet")
    ]
    if not blobs:
        raise RuntimeError(
            f"processed dataset not found: {dataset}/{operation}/schema=v{schema_version}"
        )

    total_bytes = sum(int(blob.size or 0) for blob in blobs)
    done_bytes = 0
    rows = 0
    started = time.monotonic()
    print(
        "FEATURE LOAD START "
        f"dataset={dataset} operation={operation} files={len(blobs)} bytes={total_bytes:,}"
    )

    for index, blob in enumerate(blobs, start=1):
        path = str(blob.name)
        frame = pd.read_parquet(io.BytesIO(storage.download_bytes(container, path)))
        frame = frame.drop(columns=list(_LINEAGE_COLUMNS), errors="ignore")
        rows += len(frame)
        frames.append(frame)
        done_bytes += int(blob.size or 0)

        elapsed = time.monotonic() - started
        remaining = _eta(elapsed, done_bytes, total_bytes)
        percent = (done_bytes / total_bytes * 100.0) if total_bytes else 100.0
        print(
            "FEATURE LOAD PROGRESS "
            f"dataset={dataset} operation={operation} files={index}/{len(blobs)} "
            f"percent={percent:.1f}% rows={rows:,} "
            f"elapsed={_duration(elapsed)} eta={_duration(remaining)}"
        )

    result = pd.concat(frames, ignore_index=True)
    print(
        "FEATURE LOAD COMPLETE "
        f"dataset={dataset} operation={operation} rows={len(result):,} "
        f"elapsed={_duration(time.monotonic() - started)}"
    )
    return result
