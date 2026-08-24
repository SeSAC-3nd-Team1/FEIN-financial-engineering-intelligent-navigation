"""2018-01-01부터 OpenDART 공시와 주요 재무계정을 장기 백필한다."""

from __future__ import annotations

import argparse
import calendar
from collections import defaultdict
from collections.abc import Iterator, Sequence
from datetime import date, timedelta
import os

from dotenv import load_dotenv
from sqlalchemy import select

from collectors.opendart_client import OpenDartClient, parse_corp_code_zip
from db.connection.session import PROJECT_ROOT, session_scope
from db.models.opendart import Company
from loaders.opendart import OpenDartRepository
from processing.opendart import (
    corp_code_rows,
    disclosure_rows,
    financial_account_rows,
    financial_summary_row,
    parse_date,
)
from storage.opendart import OpenDartRawWriter


DEFAULT_START_DATE = date(2018, 1, 1)
REPORT_CODES = ("11013", "11012", "11014", "11011")
REPORT_PERIOD_END = {
    "11013": (3, 31),
    "11012": (6, 30),
    "11014": (9, 30),
    "11011": (12, 31),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill listed-company OpenDART data from 2018-01-01"
    )
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=date.today())
    parser.add_argument(
        "--company-limit",
        type=int,
        help="로컬 진단용 상장사 수 제한. 운영 백필에서는 사용하지 않는다.",
    )
    parser.add_argument("--skip-financials", action="store_true")
    parser.add_argument("--skip-disclosures", action="store_true")
    return parser


def _chunks[T](values: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    """OpenDART 다중회사 요청 한도에 맞게 순서를 유지하며 분할한다."""

    for start in range(0, len(values), size):
        yield values[start : start + size]


def _quarter_windows(start_date: date, end_date: date) -> Iterator[tuple[date, date]]:
    """corp_code 없는 공시검색의 최대 3개월 제약을 넘지 않는 기간을 만든다."""

    cursor = start_date
    while cursor <= end_date:
        quarter_end_month = ((cursor.month - 1) // 3 + 1) * 3
        quarter_end = date(
            cursor.year,
            quarter_end_month,
            calendar.monthrange(cursor.year, quarter_end_month)[1],
        )
        window_end = min(end_date, quarter_end)
        yield cursor, window_end
        cursor = window_end + timedelta(days=1)


def _report_period_end(year: int, report_code: str) -> date:
    month, day = REPORT_PERIOD_END[report_code]
    return date(year, month, day)


def _sync_corp_codes(client: OpenDartClient, raw: OpenDartRawWriter) -> int:
    """최신 corpCode 원문을 보존하고 기업 마스터를 먼저 UPSERT한다."""

    content = client.download_corp_codes()
    records = parse_corp_code_zip(content)
    raw.upload_bytes(
        dataset="corp_code",
        content=content,
        partition_date=date.today(),
        extension="zip",
        content_type="application/zip",
    )
    with session_scope() as session:
        affected = OpenDartRepository(session).upsert_companies(corp_code_rows(records))
    print(f"OPENDART CORP CODES COMPLETE records={len(records)} upserted={affected}")
    return affected


def _listed_targets(limit: int | None) -> list[tuple[str, str]]:
    """corpCode에서 주식코드가 있는 상장사만 안정적인 순서로 조회한다."""

    with session_scope() as session:
        query = (
            select(Company.corp_code, Company.stock_code)
            .where(Company.stock_code.is_not(None))
            .order_by(Company.stock_code)
        )
        if limit is not None:
            query = query.limit(max(1, limit))
        return [
            (str(corp_code), str(stock_code))
            for corp_code, stock_code in session.execute(query)
            if stock_code
        ]


def _normalize_multi_financial_items(
    items: list[dict],
    targets: Sequence[tuple[str, str]],
) -> dict[tuple[str, str], list[dict]]:
    """다중회사 응답의 stock_code를 요청 corp_code와 연결해 회사·재무구분별로 묶는다."""

    corp_by_stock = {stock_code: corp_code for corp_code, stock_code in targets}
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in items:
        stock_code = str(item.get("stock_code") or "").strip()
        corp_code = str(item.get("corp_code") or corp_by_stock.get(stock_code) or "").strip()
        fs_div = str(item.get("fs_div") or "").strip()
        if not stock_code or not corp_code or not fs_div:
            continue
        enriched = dict(item)
        enriched["corp_code"] = corp_code
        grouped[(stock_code, fs_div)].append(enriched)
    return grouped


def _backfill_financials(
    client: OpenDartClient,
    raw: OpenDartRawWriter,
    *,
    targets: list[tuple[str, str]],
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    """최대 100개 회사씩 묶어 2018년 이후 주요 재무계정을 멱등 적재한다."""

    totals = {"requests": 0, "items": 0, "accounts": 0, "summaries": 0}
    for year in range(start_date.year, end_date.year + 1):
        for report_code in REPORT_CODES:
            period_end = _report_period_end(year, report_code)
            if period_end < start_date or period_end > end_date:
                continue
            for target_chunk in _chunks(targets, 100):
                response = client.financials_multi(
                    [corp_code for corp_code, _ in target_chunk],
                    str(year),
                    report_code,
                )
                totals["requests"] += 1
                items = response.payload.get("list", [])
                if not isinstance(items, list):
                    raise RuntimeError("OpenDART financials_multi list must be an array")
                if not items:
                    continue

                # query 단위 원문을 손대지 않고 보존한다. 같은 응답 재실행은 hash 경로를 재사용한다.
                raw.upload_bytes(
                    dataset="financial_multi",
                    content=response.content,
                    partition_date=period_end,
                    extension="json",
                    content_type="application/json",
                )
                grouped = _normalize_multi_financial_items(items, target_chunk)
                account_rows: list[dict] = []
                summary_rows: list[dict] = []
                for (stock_code, _fs_div), group in grouped.items():
                    rows = financial_account_rows({"list": group}, stock_code=stock_code)
                    account_rows.extend(rows)
                    summary = financial_summary_row(rows)
                    if summary:
                        summary_rows.append(summary)

                with session_scope() as session:
                    repository = OpenDartRepository(session)
                    totals["accounts"] += repository.upsert_financial_accounts(account_rows)
                    totals["summaries"] += repository.upsert_financials(summary_rows)
                totals["items"] += len(items)
            print(
                "OPENDART FINANCIAL PROGRESS "
                f"year={year} report_code={report_code} requests={totals['requests']} "
                f"items={totals['items']}"
            )
    return totals


def _disclosure_partition_date(items: list[dict], fallback: date) -> date:
    """페이지의 첫 실제 접수일을 Raw partition으로 사용하고 없으면 조회구간 시작일을 쓴다."""

    if not items:
        return fallback
    parsed = parse_date(items[0].get("rcept_dt"))
    return parsed or fallback


def _backfill_disclosures(
    client: OpenDartClient,
    raw: OpenDartRawWriter,
    *,
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    """KOSPI·KOSDAQ 공시를 3개월 이하 구간으로 나누어 전체 pagination한다."""

    totals = {"requests": 0, "items": 0, "upserted": 0}
    for window_start, window_end in _quarter_windows(start_date, end_date):
        for corp_cls in ("Y", "K"):
            responses = client.disclosures_market(
                start_date=window_start.strftime("%Y%m%d"),
                end_date=window_end.strftime("%Y%m%d"),
                corp_cls=corp_cls,
            )
            totals["requests"] += len(responses)
            for response in responses:
                items = response.payload.get("list", [])
                if not isinstance(items, list):
                    raise RuntimeError("OpenDART disclosure list must be an array")
                if not items:
                    continue
                raw.upload_bytes(
                    dataset="disclosure_market",
                    content=response.content,
                    partition_date=_disclosure_partition_date(items, window_start),
                    extension="json",
                    content_type="application/json",
                )
                rows = disclosure_rows({"list": items}, stock_code="")
                with session_scope() as session:
                    totals["upserted"] += OpenDartRepository(session).upsert_disclosures(rows)
                totals["items"] += len(items)
        print(
            "OPENDART DISCLOSURE PROGRESS "
            f"window={window_start.isoformat()}..{window_end.isoformat()} "
            f"requests={totals['requests']} items={totals['items']}"
        )
    return totals


def main(argv: list[str] | None = None) -> int:
    """기업 마스터를 먼저 만든 뒤 재무·공시 장기 백필을 순차 실행한다."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    args = _parser().parse_args(argv)
    if args.start_date > args.end_date:
        raise SystemExit("--start-date must not be after --end-date")
    if args.start_date < DEFAULT_START_DATE:
        print(
            "OPENDART NOTICE: requested start date is earlier than project baseline "
            f"{DEFAULT_START_DATE.isoformat()}"
        )

    client = OpenDartClient(
        os.getenv("OPENDART_API_KEY", ""),
        timeout_seconds=float(os.getenv("OPENDART_TIMEOUT_SECONDS", "10")),
    )
    raw = OpenDartRawWriter.from_env()
    _sync_corp_codes(client, raw)
    targets = _listed_targets(args.company_limit)
    if not targets:
        raise RuntimeError("OpenDART listed company targets are empty")
    print(f"OPENDART TARGETS listed_companies={len(targets)}")

    if not args.skip_financials:
        financials = _backfill_financials(
            client,
            raw,
            targets=targets,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"OPENDART FINANCIAL COMPLETE {financials}")

    if not args.skip_disclosures:
        disclosures = _backfill_disclosures(
            client,
            raw,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        print(f"OPENDART DISCLOSURE COMPLETE {disclosures}")

    print(
        "OPENDART 8Y BACKFILL SUCCESS "
        f"start={args.start_date.isoformat()} end={args.end_date.isoformat()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
