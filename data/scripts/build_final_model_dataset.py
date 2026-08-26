"""가격·시장·거시 Feature를 거래일 기준으로 시점 안전하게 결합한다."""

from __future__ import annotations

import argparse
import io
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from storage import BlobStorage

TARGET_PREFIX = "target_"
KEY_COLUMNS = ["stock_code", "trade_date"]


def _read(storage: BlobStorage, container: str, path: str) -> pd.DataFrame:
    """Blob 하나를 DataFrame으로 읽는다."""

    return pd.read_parquet(io.BytesIO(storage.download_bytes(container, path)))


def _monthly_paths(
    storage: BlobStorage, container: str, dataset: str, version: str
) -> list[str]:
    """특정 버전의 월별 Parquet 경로만 반환한다."""

    prefix = f"{dataset}/version=v{version}/"
    paths = [
        path
        for path in storage.list_paths(container, prefix=prefix)
        if path.endswith(".parquet")
    ]
    if not paths:
        raise RuntimeError(f"feature dataset not found: {dataset}/version=v{version}")
    return sorted(paths)


def _period(path: str) -> tuple[int, int]:
    """월 파티션 경로에서 연월을 추출한다."""

    parts = Path(path).parts
    try:
        return int(parts[-3].split("=", 1)[1]), int(parts[-2].split("=", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"invalid monthly feature path: {path}") from exc


def _empty_date_frame(column: str) -> pd.DataFrame:
    """해당 월에 보조 데이터가 없을 때 가격 행을 유지하는 빈 날짜 테이블을 만든다."""

    return pd.DataFrame({column: pd.Series(dtype="datetime64[ns]")})


def _market_daily(frame: pd.DataFrame) -> pd.DataFrame:
    """여러 시장지수를 날짜별 wide Feature로 바꾼다.

    종목 자연키를 보존해야 하므로 시장지수의 여러 행을 그대로 붙이지 않고, 지수명을
    컬럼명에 포함해 날짜당 한 행으로 만든다. 결측 지수는 값이 없는 상태로 유지한다.
    """

    required = {"trade_date", "index_name", "index_code"}
    missing = required - set(frame)
    if missing:
        raise ValueError(f"market feature columns missing: {sorted(missing)}")
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="raise")
    data["index_name"] = data["index_name"].astype("string")
    value_columns = [
        column
        for column in data.columns
        if column not in {"trade_date", "index_name", "index_code"}
    ]
    if data.duplicated(["trade_date", "index_code"]).any():
        raise ValueError(
            "duplicate market feature natural key: index_code + trade_date"
        )
    wide = data.pivot(index="trade_date", columns="index_code", values=value_columns)
    wide.columns = [
        "market_"
        + str(index).strip().lower().replace(" ", "_").replace(":", "_")
        + "_"
        + str(column)
        for column, index in wide.columns
    ]
    return wide.reset_index()


def join_daily_features(
    stock: pd.DataFrame,
    market: pd.DataFrame,
    macro: pd.DataFrame,
) -> pd.DataFrame:
    """동일 거래일의 시장·거시 Feature를 left join한다.

    시장/거시 데이터는 가격 행을 늘리지 않는 날짜 축 결합만 허용한다. ``merge_asof``나
    전진 보간을 사용하지 않으므로 관측되지 않은 날짜의 결측은 임의의 0으로 변하지 않는다.
    """

    missing = set(KEY_COLUMNS) - set(stock)
    if missing:
        raise ValueError(f"stock feature columns missing: {sorted(missing)}")
    result = stock.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="raise")
    market_daily = _market_daily(market)
    macro_daily = macro.copy()
    if (
        macro_daily.empty
        and "date" not in macro_daily
        and "trade_date" not in macro_daily
    ):
        macro_daily = _empty_date_frame("date")
    date_column = "date" if "date" in macro_daily else "trade_date"
    if date_column not in macro_daily:
        raise ValueError("macro feature date column missing: date or trade_date")
    macro_daily = macro_daily.rename(columns={date_column: "trade_date"})
    macro_daily["trade_date"] = pd.to_datetime(
        macro_daily["trade_date"], errors="raise"
    )
    if macro_daily["trade_date"].duplicated().any():
        raise ValueError("duplicate macro feature natural key: trade_date")
    for name, frame in (("market", market_daily), ("macro", macro_daily)):
        if frame["trade_date"].duplicated().any():
            raise ValueError(f"duplicate {name} feature key: trade_date")
    result = result.merge(
        market_daily, on="trade_date", how="left", validate="many_to_one"
    )
    result = result.merge(
        macro_daily, on="trade_date", how="left", validate="many_to_one"
    )
    if result.duplicated(KEY_COLUMNS).any():
        raise RuntimeError("joined dataset changed stock_code + trade_date uniqueness")
    return result.sort_values(KEY_COLUMNS).reset_index(drop=True)


def build_final_dataset(
    storage: BlobStorage,
    *,
    features_container: str,
    source_version: str = "2",
    output_version: str = "1",
    overwrite: bool = False,
) -> dict[str, Any]:
    """월별 입력만 메모리에 올려 최종 학습 Dataset과 manifest를 생성한다."""

    stock_paths = _monthly_paths(
        storage, features_container, "model_stock_daily", source_version
    )
    market_paths = {
        _period(path): path
        for path in _monthly_paths(
            storage, features_container, "market_index_daily", source_version
        )
    }
    macro_paths = {
        _period(path): path
        for path in _monthly_paths(
            storage, features_container, "macro_daily", source_version
        )
    }
    outputs: list[dict[str, Any]] = []
    feature_columns: set[str] = set()
    target_columns: set[str] = set()

    for stock_path in stock_paths:
        period = _period(stock_path)
        market_path = market_paths.get(period)
        macro_path = macro_paths.get(period)
        stock = _read(storage, features_container, stock_path)
        market = (
            _read(storage, features_container, market_path)
            if market_path
            else pd.DataFrame(columns=["trade_date", "index_name", "index_code"])
        )
        macro = (
            _read(storage, features_container, macro_path)
            if macro_path
            else _empty_date_frame("date")
        )
        joined = join_daily_features(stock, market, macro)
        target_columns.update(
            column for column in joined.columns if column.startswith(TARGET_PREFIX)
        )
        feature_columns.update(
            column
            for column in joined.columns
            if column not in KEY_COLUMNS and not column.startswith(TARGET_PREFIX)
        )
        output_path = stock_path.replace(
            "model_stock_daily/", "model_training_daily/"
        ).replace(f"version=v{source_version}/", f"version=v{output_version}/", 1)
        with tempfile.TemporaryDirectory(prefix="fein-final-model-") as directory:
            local = Path(directory) / "part-00000.parquet"
            joined.to_parquet(local, index=False, compression="zstd")
            blob = storage.upload_file(
                features_container,
                output_path,
                local,
                overwrite=overwrite,
                content_type="application/vnd.apache.parquet",
                metadata={
                    "dataset": "model_training_daily",
                    "feature_version": output_version,
                    "record_count": str(len(joined)),
                },
            )
        outputs.append({"path": output_path, "rows": len(joined), "bytes": blob.size})
        print(f"FINAL MODEL WRITE rows={len(joined)} path={output_path}")

    manifest = {
        "dataset": "model_training_daily",
        "feature_version": output_version,
        "source_feature_version": source_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": outputs,
        "rows": sum(item["rows"] for item in outputs),
        "key_columns": KEY_COLUMNS,
        "feature_columns": sorted(feature_columns),
        "target_columns": sorted(target_columns),
        "target_columns_are_model_inputs": False,
        "join": {
            "key": "trade_date",
            "method": "left exact-date",
            "missing_values": "preserved",
        },
        "safety": {
            "financial_price_join": "blocked",
            "corporate_action_adjusted_price": False,
        },
    }
    storage.upload_bytes(
        features_container,
        f"_manifests/model-training-daily/version=v{output_version}/manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        content_type="application/json",
        overwrite=True,
    )
    return manifest


def main() -> None:
    """환경변수 기반으로 최종 Dataset을 실행한다."""

    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(
        description="Build bounded final model training dataset"
    )
    parser.add_argument("--source-version", default="2")
    parser.add_argument("--output-version", default="1")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    storage = BlobStorage.from_env()
    manifest = build_final_dataset(
        storage,
        features_container=os.getenv("AZURE_STORAGE_CONTAINER_FEATURES", "features"),
        source_version=args.source_version,
        output_version=args.output_version,
        overwrite=args.overwrite,
    )
    print(
        f"FINAL MODEL SUCCESS rows={manifest['rows']} manifest=model-training-daily/version=v{args.output_version}"
    )


if __name__ == "__main__":
    main()
