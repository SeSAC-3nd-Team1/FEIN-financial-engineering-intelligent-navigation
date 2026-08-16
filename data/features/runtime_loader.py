"""모델 Feature 계산용 경량 Processed loader.

Processed에는 감사 추적을 위해 row-level lineage를 보존하지만, 수백만 행 Feature 계산 중에는
문자열 lineage가 큰 메모리를 차지한다. 모델 Dataset은 별도 manifest로 lineage를 추적하므로
Feature 계산 직전에 이 컬럼만 제거한다.
"""

from __future__ import annotations

import io

import pandas as pd

_LINEAGE_COLUMNS = ("_payload_hash", "_collected_at", "_source_blob")


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
    for blob in client.list_blobs(name_starts_with=prefix):
        path = str(blob.name)
        if not path.endswith(".parquet"):
            continue
        frame = pd.read_parquet(io.BytesIO(storage.download_bytes(container, path)))
        frame = frame.drop(columns=list(_LINEAGE_COLUMNS), errors="ignore")
        frames.append(frame)

    if not frames:
        raise RuntimeError(
            f"processed dataset not found: {dataset}/{operation}/schema=v{schema_version}"
        )
    return pd.concat(frames, ignore_index=True)
