"""모델 학습과 오프라인 분석용 Parquet 생성 공통 함수를 제공한다."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import Engine
from sqlalchemy.sql import Executable

from storage import BlobObject, BlobStorage


def export_query_to_parquet(
    engine: Engine,
    query: Executable | str,
    output_path: str | Path,
    *,
    params: dict[str, Any] | None = None,
    compression: str = "zstd",
    chunk_size: int = 100_000,
) -> Path:
    """범위가 제한된 SQL 결과를 chunk 단위로 읽어 하나의 Parquet 파일로 쓴다.

    전체 조회 결과를 DataFrame 하나에 올리지 않고 ``chunksize``로 스트리밍해 대용량
    데이터에서도 메모리 사용량을 제한한다. 첫 chunk의 Arrow schema를 이후 chunk에도
    동일하게 적용해 파일 내부 schema를 일관되게 유지한다.
    """

    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    with engine.connect() as connection:
        for frame in pd.read_sql_query(
            query, connection, params=params, chunksize=chunk_size
        ):
            table = pa.Table.from_pandas(frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(
                    destination, table.schema, compression=compression
                )
            writer.write_table(table)

    # 조회 결과가 0건이어도 호출 계약상 Parquet 파일은 생성해 downstream이 파일 없음과
    # 빈 데이터셋을 구분할 수 있게 한다.
    if writer is None:
        pd.DataFrame().to_parquet(destination, index=False, compression=compression)
    else:
        writer.close()
    return destination


def export_query_to_blob_parquet(
    engine: Engine,
    query: Executable | str,
    *,
    storage: BlobStorage,
    container: str,
    blob_path: str,
    params: dict[str, Any] | None = None,
    metadata: dict[str, str] | None = None,
    chunk_size: int = 100_000,
) -> BlobObject:
    """임시 로컬 Parquet을 만든 뒤 Blob에 업로드하고 임시 파일을 자동 정리한다.

    로컬 디스크는 변환 과정의 임시 작업공간일 뿐 source of truth가 아니므로
    ``TemporaryDirectory``를 사용해 성공/실패와 관계없이 잔여 파일을 남기지 않는다.
    """

    with tempfile.TemporaryDirectory(prefix="fein-parquet-") as directory:
        output = export_query_to_parquet(
            engine,
            query,
            Path(directory) / "dataset.parquet",
            params=params,
            chunk_size=chunk_size,
        )
        return storage.upload_file(
            container,
            blob_path,
            output,
            metadata=metadata,
            content_type="application/vnd.apache.parquet",
        )
