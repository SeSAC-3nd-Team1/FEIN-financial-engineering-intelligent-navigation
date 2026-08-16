"""Raw profile → Processed → 모델 Feature Dataset을 한 번에 실행한다."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from dotenv import load_dotenv
from features.model_dataset import build_model_datasets
from processing.processed_builder import build_processed_dataset
from storage import BlobStorage
DATASETS=["disclosure","financial_statement","market_index","security_product","stock_dividend","stock_issuance","stock_master","stock_price"]
def parse_args():
    p=argparse.ArgumentParser(); p.add_argument("--env-file",type=Path); p.add_argument("--profile-dir",type=Path,default=Path("reports/raw-profile")); p.add_argument("--dataset",action="append",choices=DATASETS); p.add_argument("--schema-version",default="1"); p.add_argument("--feature-version",default="1"); p.add_argument("--skip-processed",action="store_true"); p.add_argument("--skip-features",action="store_true"); p.add_argument("--overwrite",action="store_true"); return p.parse_args()
def main():
    args=parse_args();
    if args.env_file: load_dotenv(args.env_file,override=False)
    storage=BlobStorage.from_env(); raw=os.getenv("AZURE_STORAGE_CONTAINER_RAW","raw"); processed=os.getenv("AZURE_STORAGE_CONTAINER_PROCESSED","processed"); features=os.getenv("AZURE_STORAGE_CONTAINER_FEATURES","features"); selected=args.dataset or DATASETS; summaries=[]
    if not args.skip_processed:
        for dataset in selected:
            path=args.profile_dir/f"{dataset}.json"
            if not path.is_file(): raise FileNotFoundError(f"profile report not found: {path}")
            summaries.append(build_processed_dataset(storage,raw_container=raw,processed_container=processed,dataset=dataset,profile=json.loads(path.read_text(encoding="utf-8")),schema_version=args.schema_version,overwrite=args.overwrite))
        print("PROCESSED COMPLETE "+json.dumps(summaries,ensure_ascii=False))
    if not args.skip_features:
        print("FEATURE DATASETS COMPLETE "+json.dumps(build_model_datasets(storage,processed_container=processed,features_container=features,schema_version=args.schema_version,feature_version=args.feature_version,overwrite=args.overwrite),ensure_ascii=False))
if __name__=="__main__": main()
