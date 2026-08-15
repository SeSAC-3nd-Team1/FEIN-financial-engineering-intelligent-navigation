"""Parquet exports for model training and offline analysis."""

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
    """Stream a bounded query into a columnar Parquet training dataset."""

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
    """Create Parquet in a temporary directory and upload it to Blob Storage."""

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
