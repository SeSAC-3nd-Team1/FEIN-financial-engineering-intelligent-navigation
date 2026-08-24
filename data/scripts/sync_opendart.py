"""OpenDART 기업·재무·공시 데이터를 수동 동기화하는 CLI다."""

from __future__ import annotations

import argparse
from datetime import date
import os

from dotenv import load_dotenv
from sqlalchemy import select

from collectors.opendart_client import OpenDartClient, parse_corp_code_zip
from db.connection.session import PROJECT_ROOT, session_scope
from db.models.opendart import Company
from loaders.opendart import OpenDartRepository
from processing.opendart import (
    company_row,
    corp_code_rows,
    disclosure_rows,
    financial_account_rows,
    financial_summary_row,
)
from storage.opendart import OpenDartRawWriter


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synchronize OpenDART data")
    parser.add_argument("--skip-blob", action="store_true", help="Skip Azure Raw upload for local diagnostics")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("corp-codes")

    company = subparsers.add_parser("company")
    company.add_argument("--stock-code", required=True)

    companies = subparsers.add_parser("companies")
    companies.add_argument("--limit", type=int, help="Limit listed companies for an operational batch")

    financials = subparsers.add_parser("financials")
    financials.add_argument("--stock-code", required=True)
    financials.add_argument("--year", required=True)
    financials.add_argument("--report-code", default="11011", choices=["11013", "11012", "11014", "11011"])
    financials.add_argument("--fs-div", default="CFS", choices=["CFS", "OFS"])

    disclosures = subparsers.add_parser("disclosures")
    disclosures.add_argument("--stock-code", required=True)
    disclosures.add_argument("--start-date")
    disclosures.add_argument("--end-date")
    disclosures.add_argument("--type")
    disclosures.add_argument("--limit", type=int, default=100)
    return parser


def _company_by_stock(session, stock_code: str) -> Company:
    company = session.scalar(select(Company).where(Company.stock_code == stock_code))
    if company is None:
        raise ValueError(f"Unknown stock_code={stock_code}; run corp-codes first")
    return company


def main(argv: list[str] | None = None) -> int:
    """선택한 dataset을 Raw 보존한 뒤 하나의 DB transaction으로 UPSERT한다."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    args = _parser().parse_args(argv)
    client = OpenDartClient(
        os.getenv("OPENDART_API_KEY", ""),
        timeout_seconds=float(os.getenv("OPENDART_TIMEOUT_SECONDS", "10")),
    )
    raw = None if args.skip_blob else OpenDartRawWriter.from_env()
    today = date.today()

    if args.command == "corp-codes":
        content = client.download_corp_codes()
        records = parse_corp_code_zip(content)
        if raw:
            raw.upload_bytes(
                dataset="corp_code", content=content, partition_date=today,
                extension="zip", content_type="application/zip",
            )
        with session_scope() as session:
            affected = OpenDartRepository(session).upsert_companies(corp_code_rows(records))
        print(f"corp-codes complete: records={len(records)} upserted={affected}")
        return 0

    if args.command == "companies":
        with session_scope() as session:
            query = select(Company.corp_code, Company.stock_code).where(Company.stock_code.is_not(None)).order_by(Company.stock_code)
            if args.limit:
                query = query.limit(max(1, args.limit))
            targets = list(session.execute(query))
        affected = 0
        failures = 0
        for corp_code, stock_code in targets:
            try:
                payload = client.company(corp_code)
                if raw:
                    raw.upload_json(dataset="company", payload=payload, partition_date=today, stock_code=stock_code)
                with session_scope() as session:
                    affected += OpenDartRepository(session).upsert_companies([company_row(payload)])
            except Exception as exc:
                # 한 기업의 provider/DB/Blob 실패가 나머지 상장사 수집을 막지 않게 격리한다.
                failures += 1
                print(f"FAILED company stock_code={stock_code} error={type(exc).__name__}")
        print(f"companies complete: targets={len(targets)} upserted={affected} failures={failures}")
        return 1 if failures else 0

    stock_code = args.stock_code.strip()
    with session_scope() as session:
        company = _company_by_stock(session, stock_code)
        corp_code = company.corp_code

    if args.command == "company":
        payload = client.company(corp_code)
        if raw:
            raw.upload_json(dataset="company", payload=payload, partition_date=today, stock_code=stock_code)
        with session_scope() as session:
            affected = OpenDartRepository(session).upsert_companies([company_row(payload)])
    elif args.command == "financials":
        payload = client.financials(corp_code, args.year, args.report_code, args.fs_div)
        if raw:
            raw.upload_json(dataset="financial", payload=payload, partition_date=today, stock_code=stock_code)
        rows = financial_account_rows(payload, stock_code=stock_code)
        summary = financial_summary_row(rows)
        with session_scope() as session:
            repository = OpenDartRepository(session)
            affected = repository.upsert_financial_accounts(rows)
            if summary:
                repository.upsert_financials([summary])
    else:
        payload = client.disclosures(
            corp_code,
            start_date=args.start_date,
            end_date=args.end_date,
            disclosure_type=args.type,
            page_count=args.limit,
        )
        if raw:
            raw.upload_json(dataset="disclosure", payload=payload, partition_date=today, stock_code=stock_code)
        rows = disclosure_rows(payload, stock_code=stock_code)
        with session_scope() as session:
            affected = OpenDartRepository(session).upsert_disclosures(rows)
    print(f"{args.command} complete: stock_code={stock_code} upserted={affected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
