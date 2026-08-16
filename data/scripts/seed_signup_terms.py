"""승인된 version을 명시적으로 받아 회원가입 약관 catalog를 멱등하게 seed한다."""

import argparse
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert

from db.connection import build_engine, session_scope
from db.models import Term


# term_code는 사용자 동의 이력과 FK로 연결되는 식별자이므로 title 변경과 분리해 유지한다.
TERM_TITLES = {
    "A1_THIRD_PARTY": "제3자 정보 제공 동의",
    "A2_UNIQUE_ID": "고유식별정보 처리 동의",
    "A3_CARRIER": "통신사 이용약관 동의",
    "A4_KCB": "KCB 본인확인 서비스 동의",
    "B_PRIVACY": "개인정보 수집 및 이용 동의",
    "C_ASSOCIATE_TERMS": "준회원 이용약관 동의",
}


def parse_timestamp(value: str) -> datetime:
    """약관 효력 시각에 timezone offset이 반드시 포함되도록 검증한다."""

    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a UTC offset")
    return timestamp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        required=True,
        help="Approved term version, or an explicit development version such as dev-20260815",
    )
    parser.add_argument(
        "--effective-at",
        required=True,
        type=parse_timestamp,
        help="ISO-8601 timestamp, for example 2026-08-15T00:00:00+09:00",
    )
    parser.add_argument(
        "--content-base-url",
        help="Optional immutable base URL; /<term-code>/<version> is appended",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = []
    for code, title in TERM_TITLES.items():
        content_reference = None
        if args.content_base_url:
            # 약관 본문 URL도 code/version을 포함시켜 과거 동의 당시 내용을 재현할 수 있게 한다.
            content_reference = (
                f"{args.content_base_url.rstrip('/')}/{code}/{args.version}"
            )
        rows.append(
            {
                "term_code": code,
                "version": args.version,
                "title": title,
                "content_reference": content_reference,
                "is_required": True,
                "effective_at": args.effective_at,
            }
        )

    engine = build_engine()
    statement = insert(Term).values(rows)
    # 같은 term_code/version을 다시 실행해도 기존 약관 row를 덮어쓰지 않는다.
    statement = statement.on_conflict_do_nothing(
        index_elements=[Term.term_code, Term.version]
    ).returning(Term.id)
    with session_scope(engine) as session:
        result = session.execute(statement)
        inserted_count = len(result.scalars().all())
    print(f"signup terms ready: {inserted_count} inserted, version={args.version}")


if __name__ == "__main__":
    main()
