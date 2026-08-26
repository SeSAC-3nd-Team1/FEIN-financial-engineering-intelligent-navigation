"""OpenDART 사업보고서의 연간 배당 데이터를 멱등 수집한다."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import os

from dotenv import load_dotenv
from sqlalchemy import select

from collectors.opendart_client import OpenDartApiError, OpenDartClient, OpenDartError
from db.connection.session import PROJECT_ROOT, session_scope
from db.models.opendart import Company, StockDividend
from loaders.opendart import OpenDartRepository
from processing.opendart import dividend_rows
from storage.opendart import OpenDartRawWriter

DEFAULT_START_YEAR = 2018
ANNUAL_REPORT_CODE = "11011"
FATAL_API_STATUSES = {"010", "011", "012", "020", "901"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync annual OpenDART dividend data for listed companies"
    )
    years = parser.add_mutually_exclusive_group()
    years.add_argument("--year", type=int, help="하나의 사업연도")
    years.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=date.today().year)
    parser.add_argument(
        "--fallback-year",
        type=int,
        help="--year 응답에 배당 데이터가 없을 때만 조회할 이전 사업연도",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="이미 적재된 종목-사업연도도 다시 요청해 UPSERT",
    )
    parser.add_argument(
        "--stock-code",
        action="append",
        dest="stock_codes",
        help="특정 종목코드. 여러 종목은 옵션을 반복하며, 생략하면 전체 상장사",
    )
    return parser


def _year_range(args: argparse.Namespace) -> range:
    start = args.year if args.year is not None else args.start_year
    end = args.year if args.year is not None else args.end_year
    if start < 2015 or end < start:
        raise SystemExit("year range must be 2015 or later and start-year <= end-year")
    if args.fallback_year is not None:
        if args.year is None:
            raise SystemExit("--fallback-year requires --year")
        if args.fallback_year < 2015 or args.fallback_year >= args.year:
            raise SystemExit(
                "fallback-year must be 2015 or later and earlier than year"
            )
    return range(start, end + 1)


def _targets(stock_codes: list[str] | None) -> list[tuple[str, str]]:
    normalized = sorted({code.strip() for code in stock_codes or [] if code.strip()})
    if any(len(code) != 6 or not code.isdigit() for code in normalized):
        raise SystemExit("--stock-code must be a 6-digit code")
    with session_scope() as session:
        query = select(Company.corp_code, Company.stock_code).where(
            Company.stock_code.is_not(None)
        )
        if normalized:
            query = query.where(Company.stock_code.in_(normalized))
        rows = [
            (str(corp_code), str(stock_code))
            for corp_code, stock_code in session.execute(
                query.order_by(Company.stock_code)
            )
            if stock_code
        ]
    if normalized:
        found = {stock_code for _, stock_code in rows}
        missing = sorted(set(normalized) - found)
        if missing:
            print(f"OPENDART DIVIDEND UNMAPPED stock_codes={','.join(missing)}")
    return rows


def _existing_keys(years: range, stock_codes: list[str]) -> set[tuple[str, str]]:
    with session_scope() as session:
        return {
            (str(stock_code), str(business_year))
            for stock_code, business_year in session.execute(
                select(StockDividend.stock_code, StockDividend.business_year)
                .where(
                    StockDividend.report_code == ANNUAL_REPORT_CODE,
                    StockDividend.business_year.in_([str(year) for year in years]),
                    StockDividend.stock_code.in_(stock_codes),
                )
                .distinct()
            )
        }


def _sync_target(
    *,
    client: OpenDartClient,
    raw: OpenDartRawWriter,
    corp_code: str,
    stock_code: str,
    year: int,
    totals: dict[str, int],
) -> str:
    """한 종목·연도를 적재하고 fallback 판단을 위한 결과 상태를 반환한다."""

    try:
        response = client.dividends(corp_code, str(year), ANNUAL_REPORT_CODE)
        totals["requests"] += 1
        items = response.payload.get("list", [])
        if not isinstance(items, list) or not items:
            totals["unavailable"] += 1
            return "unavailable"
        raw.upload_bytes(
            dataset="dividend",
            stock_code=stock_code,
            content=response.content,
            partition_date=date(year, 12, 31),
            extension="json",
            content_type="application/json",
        )
        rows = dividend_rows(
            response.payload,
            stock_code=stock_code,
            corp_code=corp_code,
            business_year=str(year),
            report_code=ANNUAL_REPORT_CODE,
            collected_at=datetime.now().astimezone(),
        )
        if not rows:
            totals["unavailable"] += 1
            return "unavailable"
        with session_scope() as session:
            totals["upserted"] += OpenDartRepository(session).upsert_dividends(rows)
        totals["rows"] += len(rows)
        return "stored"
    except OpenDartApiError as exc:
        if exc.status in FATAL_API_STATUSES:
            raise
        if exc.status == "013":
            totals["unavailable"] += 1
            return "unavailable"
        totals["failed"] += 1
        print(
            "OPENDART DIVIDEND SKIP "
            f"stock_code={stock_code} year={year} status={exc.status}"
        )
    except (OpenDartError, ValueError) as exc:
        totals["failed"] += 1
        print(
            "OPENDART DIVIDEND SKIP "
            f"stock_code={stock_code} year={year} error={type(exc).__name__}"
        )
    return "failed"


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    args = _parser().parse_args(argv)
    years = _year_range(args)
    targets = _targets(args.stock_codes)
    if not targets:
        print("OPENDART DIVIDEND COMPLETE targets=0 unavailable=0 upserted=0")
        return 0

    client = OpenDartClient(
        os.getenv("OPENDART_API_KEY", ""),
        timeout_seconds=float(os.getenv("OPENDART_TIMEOUT_SECONDS", "10")),
        min_interval_seconds=float(os.getenv("OPENDART_MIN_INTERVAL_SECONDS", "0.25")),
    )
    raw = OpenDartRawWriter.from_env()
    lookup_years = range(
        args.fallback_year if args.fallback_year is not None else years.start,
        years.stop,
    )
    existing = (
        set()
        if args.refresh
        else _existing_keys(lookup_years, [stock_code for _, stock_code in targets])
    )
    totals = {
        "requests": 0,
        "skipped": 0,
        "unavailable": 0,
        "failed": 0,
        "rows": 0,
        "upserted": 0,
    }

    for year in years:
        for corp_code, stock_code in targets:
            if (stock_code, str(year)) in existing:
                totals["skipped"] += 1
                continue
            result = _sync_target(
                client=client,
                raw=raw,
                corp_code=corp_code,
                stock_code=stock_code,
                year=year,
                totals=totals,
            )
            if result != "unavailable" or args.fallback_year is None:
                continue
            fallback_key = (stock_code, str(args.fallback_year))
            if fallback_key in existing:
                totals["skipped"] += 1
                continue
            _sync_target(
                client=client,
                raw=raw,
                corp_code=corp_code,
                stock_code=stock_code,
                year=args.fallback_year,
                totals=totals,
            )
        print(
            "OPENDART DIVIDEND PROGRESS "
            f"year={year} requests={totals['requests']} rows={totals['rows']} "
            f"unavailable={totals['unavailable']} failed={totals['failed']}"
        )

    print(
        "OPENDART DIVIDEND COMPLETE "
        f"targets={len(targets)} years={years.start}..{years.stop - 1} "
        + " ".join(f"{key}={value}" for key, value in totals.items())
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
