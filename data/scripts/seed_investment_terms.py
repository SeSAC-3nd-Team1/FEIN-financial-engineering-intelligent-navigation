"""가상투자 시작에 필요한 승인 약관 catalog를 멱등하게 seed한다."""

from datetime import datetime

from sqlalchemy import Connection, Engine
from sqlalchemy.dialects.postgresql import insert

from db.connection import build_engine, session_scope
from db.models import Term


INVESTMENT_TERM_TITLES = {
    "INVEST_PRODUCT_LOW": "저변동성 전략 상품설명서",
    "INVEST_PRODUCT_VALUE": "가치 전략 상품설명서",
    "INVEST_PRODUCT_MOMENTUM": "모멘텀 전략 상품설명서",
    "INVEST_SERVICE": "가상투자 서비스 필수 약관",
    "INVEST_PRIVACY": "투자정보 수집 및 이용 동의",
    "INVEST_LOSS_NOTICE": "원금손실 가능성 확인",
}


def build_investment_term_rows(
    version: str,
    effective_at: datetime,
    content_base_url: str | None = None,
) -> list[dict]:
    """상품설명서와 공통 필수 약관을 동일 승인 version으로 구성한다."""

    rows = []
    for code, title in INVESTMENT_TERM_TITLES.items():
        content_reference = None
        if content_base_url:
            content_reference = f"{content_base_url.rstrip('/')}/{code}/{version}"
        rows.append({
            "term_code": code,
            "version": version,
            "title": title,
            "content_reference": content_reference,
            "is_required": True,
            "effective_at": effective_at,
        })
    return rows


def build_investment_seed_statement(rows: list[dict]):
    """기존 code/version 본문을 덮어쓰지 않는 PostgreSQL insert를 만든다."""

    return insert(Term).values(rows).on_conflict_do_nothing(
        index_elements=[Term.term_code, Term.version]
    ).returning(Term.id)


def seed_investment_terms(
    version: str,
    effective_at: datetime,
    content_base_url: str | None = None,
    bind: Engine | Connection | None = None,
) -> int:
    """같은 약관 version을 건너뛰며 새로 추가된 행 수를 반환한다."""

    rows = build_investment_term_rows(version, effective_at, content_base_url)
    active_bind = bind if bind is not None else build_engine()
    with session_scope(active_bind) as session:
        result = session.execute(build_investment_seed_statement(rows))
        return len(result.scalars().all())
