"""OpenDART 정제 행의 transaction 단위 UPSERT를 제공한다."""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from db.models.opendart import (
    Company,
    CompanyDisclosure,
    CompanyFinancial,
    CompanyFinancialAccount,
    StockDividend,
)
from loaders.upsert import upsert_rows

CASH_FLOW_COLUMNS = (
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
)


class OpenDartRepository:
    """OpenDART 테이블별 충돌키를 한 곳에서 관리한다."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_companies(self, rows: list[dict]) -> int:
        return upsert_rows(self.session, Company, rows, conflict_columns=["corp_code"])

    def upsert_financial_accounts(self, rows: list[dict]) -> int:
        return upsert_rows(
            self.session,
            CompanyFinancialAccount,
            rows,
            conflict_columns=[
                "corp_code",
                "business_year",
                "report_code",
                "fs_div",
                "sj_div",
                "account_id",
            ],
        )

    def upsert_financials(
        self,
        rows: list[dict],
        *,
        preserve_existing_cash_flows: bool = False,
    ) -> int:
        """보고서 요약을 UPSERT하고 sparse 응답에서는 기존 현금흐름 값을 보존한다.

        ``fnlttMultiAcnt``는 주요 BS/IS 계정 중심이라 현금흐름 3종이 키는 존재하지만 모두
        ``None``으로 들어온다. 이런 명시적 sparse 배치만 감지해 현금흐름 컬럼을 UPDATE
        대상에서 제외하고, 일반 단일회사 전체재무제표 경로의 기존 동작은 유지한다.
        """

        sparse_cash_flow_batch = bool(rows) and all(
            all(column in row for column in CASH_FLOW_COLUMNS)
            and all(row[column] is None for column in CASH_FLOW_COLUMNS)
            for row in rows
        )
        preserve_cash_flows = preserve_existing_cash_flows or sparse_cash_flow_batch
        conflict_columns = ["corp_code", "business_year", "report_code", "fs_div"]

        if not preserve_cash_flows:
            return upsert_rows(
                self.session,
                CompanyFinancial,
                rows,
                conflict_columns=conflict_columns,
            )

        return upsert_rows(
            self.session,
            CompanyFinancial,
            rows,
            conflict_columns=conflict_columns,
            update_columns=[
                "stock_code",
                "quarter",
                "revenue",
                "operating_income",
                "net_income",
                "total_assets",
                "total_liabilities",
                "total_equity",
            ],
        )

    def upsert_dividends(self, rows: list[dict]) -> int:
        return upsert_rows(
            self.session,
            StockDividend,
            rows,
            conflict_columns=[
                "stock_code",
                "business_year",
                "report_code",
                "stock_kind",
            ],
        )

    def replace_dividends(
        self,
        rows: list[dict],
        *,
        stock_code: str,
        business_year: str,
        report_code: str,
    ) -> int:
        """한 종목·사업연도·보고서 범위를 새 응답으로 원자적으로 교체한다."""

        scope = (stock_code, business_year, report_code)
        if any(
            (
                row.get("stock_code"),
                row.get("business_year"),
                row.get("report_code"),
            )
            != scope
            for row in rows
        ):
            raise ValueError("dividend replacement rows must match the requested scope")

        # UPSERT만으로는 정규화 키가 바뀐 legacy 행을 제거할 수 없으므로 refresh 범위만
        # 먼저 지운다. session_scope가 delete와 insert를 같은 transaction으로 확정한다.
        self.session.execute(
            delete(StockDividend).where(
                StockDividend.stock_code == stock_code,
                StockDividend.business_year == business_year,
                StockDividend.report_code == report_code,
            )
        )
        return self.upsert_dividends(rows)

    def upsert_disclosures(self, rows: list[dict]) -> int:
        return upsert_rows(
            self.session, CompanyDisclosure, rows, conflict_columns=["receipt_no"]
        )
