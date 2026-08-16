"""Processed 금융 데이터에서 모델 담당자가 바로 사용할 Feature Dataset을 만든다."""
from __future__ import annotations
import io, json, math, os, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

def load_processed_operation(storage,container:str,dataset:str,operation:str,schema_version:str)->pd.DataFrame:
    prefix=f"{dataset}/operation={operation.lower()}/schema=v{schema_version}/"; frames=[]
    for blob in storage.service_client.get_container_client(container).list_blobs(name_starts_with=prefix):
        path=str(blob.name)
        if path.endswith(".parquet"): frames.append(pd.read_parquet(io.BytesIO(storage.download_bytes(container,path))))
    if not frames: raise RuntimeError(f"processed dataset not found: {dataset}/{operation}/schema=v{schema_version}")
    return pd.concat(frames,ignore_index=True)

def _resolve_duplicate_prices(frame:pd.DataFrame)->pd.DataFrame:
    key=["stock_code","trade_date"]; mask=frame.duplicated(key,keep=False)
    if not mask.any(): return frame
    compare=[c for c in ["open_price","high_price","low_price","close_price","volume","trading_value","market_cap"] if c in frame]
    conflicts=frame.loc[mask].groupby(key,dropna=False)[compare].nunique(dropna=False)
    if not conflicts.empty and (conflicts>1).any(axis=None): raise RuntimeError("conflicting stock price duplicates found for stock_code + trade_date")
    return frame.drop_duplicates(key,keep="first")

def compute_stock_features(frame:pd.DataFrame)->pd.DataFrame:
    required={"stock_code","trade_date","close_price","volume"}; missing=required-set(frame)
    if missing: raise ValueError(f"stock price processed columns missing: {sorted(missing)}")
    data=frame.copy(); data["trade_date"]=pd.to_datetime(data["trade_date"],errors="raise")
    for c in ["open_price","high_price","low_price","close_price","volume","trading_value","market_cap","listed_shares"]:
        if c in data: data[c]=pd.to_numeric(data[c],errors="coerce")
    data=_resolve_duplicate_prices(data).sort_values(["stock_code","trade_date"]).reset_index(drop=True)
    grouped=data.groupby("stock_code",sort=False); close=grouped["close_price"]; volume=grouped["volume"]
    data["return_1d"]=close.pct_change(fill_method=None)
    for h in (5,20,60,120): data[f"momentum_{h}d"]=data["close_price"]/close.shift(h)-1.0
    for w in (5,20,60): data[f"sma_{w}d"]=close.transform(lambda s,w=w:s.rolling(w,min_periods=w).mean())
    data["price_to_sma_20d"]=data["close_price"]/data["sma_20d"]-1.0
    data["volatility_20d"]=grouped["return_1d"].transform(lambda s:s.rolling(20,min_periods=20).std()*math.sqrt(252))
    data["volatility_60d"]=grouped["return_1d"].transform(lambda s:s.rolling(60,min_periods=60).std()*math.sqrt(252))
    data["volume_sma_20d"]=volume.transform(lambda s:s.rolling(20,min_periods=20).mean()); data["volume_ratio_20d"]=data["volume"]/data["volume_sma_20d"].replace(0,np.nan)
    if "trading_value" in data: data["trading_value_sma_20d"]=grouped["trading_value"].transform(lambda s:s.rolling(20,min_periods=20).mean())
    if "market_cap" in data: data["log_market_cap"]=np.log(data["market_cap"].where(data["market_cap"]>0))
    for h in (5,20):
        data[f"target_date_{h}d"]=grouped["trade_date"].shift(-h); data[f"target_return_{h}d"]=close.shift(-h)/data["close_price"]-1.0
    data["target_up_20d"]=(data["target_return_20d"]>0).astype("Int8"); data.loc[data["target_return_20d"].isna(),"target_up_20d"]=pd.NA
    return data

def assign_purged_time_split(frame:pd.DataFrame)->tuple[pd.DataFrame,dict[str,str]]:
    data=frame.copy(); dates=pd.Index(sorted(data["trade_date"].dropna().unique()))
    if len(dates)<30: raise RuntimeError("not enough unique trade dates for temporal split")
    train_end=pd.Timestamp(dates[int(len(dates)*.70)-1]); valid_end=pd.Timestamp(dates[int(len(dates)*.85)-1]); test_end=pd.Timestamp(dates[-1])
    data["split"]="test"; data.loc[data["trade_date"]<=train_end,"split"]="train"; data.loc[(data["trade_date"]>train_end)&(data["trade_date"]<=valid_end),"split"]="validation"
    end=data["split"].map({"train":train_end,"validation":valid_end,"test":test_end})
    data["eligible_target_20d"]=data["target_date_20d"].notna()&(data["target_date_20d"]<=end); data["eligible_target_5d"]=data["target_date_5d"].notna()&(data["target_date_5d"]<=end)
    return data,{"train_end":train_end.date().isoformat(),"validation_end":valid_end.date().isoformat(),"test_end":test_end.date().isoformat(),"split_method":"chronological_70_15_15_with_target_horizon_purge"}
assign_time_split=assign_purged_time_split

def compute_financial_features(frame:pd.DataFrame)->pd.DataFrame:
    data=frame.copy()
    if "base_date" in data: data["base_date"]=pd.to_datetime(data["base_date"],errors="coerce")
    for c in ["sales","operating_profit","net_income","total_assets","total_liabilities","total_equity","capital","reported_debt_ratio","comprehensive_income"]:
        if c in data: data[c]=pd.to_numeric(data[c],errors="coerce")
    if {"total_liabilities","total_equity"}<=set(data): data["debt_ratio"]=data["total_liabilities"]/data["total_equity"].replace(0,np.nan)
    if {"net_income","total_assets"}<=set(data): data["roa"]=data["net_income"]/data["total_assets"].replace(0,np.nan)
    if {"net_income","total_equity"}<=set(data): data["roe"]=data["net_income"]/data["total_equity"].replace(0,np.nan)
    if {"operating_profit","sales"}<=set(data): data["operating_margin"]=data["operating_profit"]/data["sales"].replace(0,np.nan)
    if {"net_income","sales"}<=set(data): data["net_margin"]=data["net_income"]/data["sales"].replace(0,np.nan)
    data["point_in_time_join_ready"]=False; return data

def compute_market_features(frame:pd.DataFrame)->pd.DataFrame:
    required={"trade_date","index_name","close_index"}; missing=required-set(frame)
    if missing: raise ValueError(f"market index processed columns missing: {sorted(missing)}")
    data=frame.copy(); data["trade_date"]=pd.to_datetime(data["trade_date"],errors="coerce"); data["close_index"]=pd.to_numeric(data["close_index"],errors="coerce"); data=data.sort_values(["index_name","trade_date"]).reset_index(drop=True); grouped=data.groupby("index_name",sort=False)
    data["index_return_1d"]=grouped["close_index"].pct_change(fill_method=None); data["index_momentum_20d"]=data["close_index"]/grouped["close_index"].shift(20)-1.0; data["index_sma_20d"]=grouped["close_index"].transform(lambda s:s.rolling(20,min_periods=20).mean()); data["index_above_sma_20d"]=data["close_index"]>data["index_sma_20d"]; data["index_volatility_20d"]=grouped["index_return_1d"].transform(lambda s:s.rolling(20,min_periods=20).std()*math.sqrt(252)); return data

def _write_monthly(storage,container,dataset,frame,date_column,version,metadata,overwrite):
    data=frame.copy(); data[date_column]=pd.to_datetime(data[date_column],errors="coerce"); data=data.loc[data[date_column].notna()].copy(); data["_year"]=data[date_column].dt.year; data["_month"]=data[date_column].dt.month; outputs=[]
    for (year,month),monthly in data.groupby(["_year","_month"],sort=True):
        output=monthly.drop(columns=["_year","_month"]).reset_index(drop=True); path=f"{dataset}/version=v{version}/year={int(year):04d}/month={int(month):02d}/part-00000.parquet"
        with tempfile.TemporaryDirectory(prefix="fein-feature-") as directory:
            local=Path(directory)/"part-00000.parquet"; output.to_parquet(local,index=False,compression="zstd"); result=storage.upload_file(container,path,local,content_type="application/vnd.apache.parquet",overwrite=overwrite,metadata={**metadata,"record_count":str(len(output))})
        outputs.append({"path":path,"rows":len(output),"bytes":result.size}); print(f"FEATURE WRITE dataset={dataset} rows={len(output)} path={path}")
    return outputs

def build_model_datasets(storage,*,processed_container:str,features_container:str,schema_version:str="1",feature_version:str="1",overwrite:bool=False)->dict[str,Any]:
    git_sha=os.getenv("GIT_SHA","unknown"); result={}
    stock,split=assign_purged_time_split(compute_stock_features(load_processed_operation(storage,processed_container,"stock_price","getstockpriceinfo",schema_version)))
    result["model_stock_daily"]={"files":_write_monthly(storage,features_container,"model_stock_daily",stock,"trade_date",feature_version,{"layer":"features","dataset":"model_stock_daily","feature_version":feature_version,"processed_schema_version":schema_version,"git_sha":git_sha},overwrite),"rows":len(stock),"split":split}
    market=compute_market_features(load_processed_operation(storage,processed_container,"market_index","getstockmarketindex",schema_version)); result["market_index_daily"]={"files":_write_monthly(storage,features_container,"market_index_daily",market,"trade_date",feature_version,{"layer":"features","dataset":"market_index_daily","feature_version":feature_version,"processed_schema_version":schema_version,"git_sha":git_sha},overwrite),"rows":len(market)}
    financial=compute_financial_features(load_processed_operation(storage,processed_container,"financial_statement","getsummfinastat_v2",schema_version)); result["financial_snapshot"]={"files":_write_monthly(storage,features_container,"financial_snapshot",financial,"base_date",feature_version,{"layer":"features","dataset":"financial_snapshot","feature_version":feature_version,"processed_schema_version":schema_version,"git_sha":git_sha,"point_in_time_join":"not_ready"},overwrite),"rows":len(financial),"point_in_time_join_ready":False}
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"feature_version":feature_version,"processed_schema_version":schema_version,"git_sha":git_sha,"look_ahead_policy":"financial_snapshot_not_joined_until_publication_availability_date_is_resolved",**result}; storage.upload_bytes(features_container,f"_manifests/model-datasets/version=v{feature_version}/manifest.json",json.dumps(payload,ensure_ascii=False,indent=2).encode(),content_type="application/json",overwrite=True); return payload
