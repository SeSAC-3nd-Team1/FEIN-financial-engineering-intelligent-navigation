"""Parquet exports for model training and offline analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.sql import Executable


def export_query_to_parquet(
    engine: Engine,
    query: Executable | str,
    output_path: str | Path,
    *,
    params: dict[str, Any] | None = None,
    compression: str = "zstd",
) -> Path:
    """Execute a bounded query and write a columnar Parquet training dataset."""

    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with engine.connect() as connection:
        frame = pd.read_sql_query(query, connection, params=params)
    frame.to_parquet(destination, index=False, compression=compression)
    return destination
