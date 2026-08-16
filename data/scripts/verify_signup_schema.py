"""회원가입 schema의 제약조건을 실제 PostgreSQL에서 검증하고 모든 test write를 rollback한다."""

import argparse
import uuid

import psycopg
from psycopg import sql

from db.connection import get_database_url
from scripts.seed_signup_terms import TERM_TITLES


def expect_violation(connection: psycopg.Connection, query: str, params: tuple) -> None:
    """지정 SQL이 DB 무결성 제약을 실제로 위반하는지 savepoint 안에서 확인한다.

    하나의 실패 검증이 전체 transaction을 abort 상태로 만들지 않도록 각 case마다
    savepoint를 만들고 그 지점까지만 rollback한다.
    """

    savepoint = sql.Identifier(f"check_{uuid.uuid4().hex}")
    connection.execute(sql.SQL("SAVEPOINT {}").format(savepoint))
    try:
        connection.execute(query, params)
    except psycopg.IntegrityError:
        connection.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(savepoint))
    else:
        connection.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(savepoint))
        raise AssertionError("expected an integrity constraint violation")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--term-version", required=True)
    parser.add_argument(
        "--create-temporary-terms",
        action="store_true",
        help="Create the six requested term rows inside the rollback-only test transaction",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_url = get_database_url().replace("postgresql+psycopg://", "postgresql://")
    suffix = uuid.uuid4().hex[:10]

    with psycopg.connect(database_url) as connection:
        try:
            # 실제 terms catalog가 아직 준비되지 않은 개발 DB에서는 검증 transaction 안에서만
            # 임시 약관을 만들 수 있다. 마지막 rollback으로 이 row도 남지 않는다.
            if args.create_temporary_terms:
                for code, title in TERM_TITLES.items():
                    connection.execute(
                        """
                        INSERT INTO terms (
                            term_code, version, title, is_required, effective_at
                        )
                        VALUES (%s, %s, %s, true, now())
                        ON CONFLICT (term_code, version) DO NOTHING
                        """,
                        (code, args.term_version, title),
                    )

            catalog_count = connection.execute(
                "SELECT count(*) FROM terms WHERE version = %s AND term_code = ANY(%s)",
                (args.term_version, list(TERM_TITLES)),
            ).fetchone()[0]
            assert catalog_count == len(TERM_TITLES), "seed all six signup terms first"

            # ORM metadata만 보는 것이 아니라 실제 Azure/local PostgreSQL에 필요한 table이
            # 생성되었는지 information_schema를 통해 확인한다.
            table_names = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = ANY(%s)
                    """,
                    (["users", "terms", "user_agreements"],),
                )
            }
            assert table_names == {"users", "terms", "user_agreements"}

            index_names = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = ANY(%s)
                    """,
                    (["users", "terms", "user_agreements"],),
                )
            }
            assert {
                "uq_users_user_id",
                "uq_users_email",
                "uq_users_ci_lookup_hash",
                "ix_users_phone_number",
                "uq_terms_code_version",
                "uq_user_agreements_user_term_version",
                "ix_user_agreements_user_agreed_at",
            } <= index_names

            # 정상 계정과 약관 동의를 먼저 넣어 FK/UNIQUE 검증의 기준 row를 만든다.
            # 전체 transaction은 마지막에 rollback되므로 운영 데이터에는 남지 않는다.
            user_id = f"test{suffix}"[:16]
            email = f"{suffix}@example.test"
            user_pk = connection.execute(
                """
                INSERT INTO users (
                    user_id, password_hash, name, birthdate, phone_number,
                    phone_verified, phone_verified_at,
                    email, email_verified, email_verified_at
                )
                VALUES (%s, %s, %s, %s, %s, true, now(), %s, true, now())
                RETURNING id
                """,
                (user_id, "integration-test-hash", "테스트", "990117", "01012345678", email),
            ).fetchone()[0]

            inserted = connection.execute(
                """
                INSERT INTO user_agreements (
                    user_id, term_code, term_version, is_required,
                    is_agreed, agreed_at, agreed_ip, user_agent
                )
                SELECT %s, term_code, version, is_required,
                       true, now(), '127.0.0.1'::inet, 'schema-verifier'
                FROM terms
                WHERE version = %s AND term_code = ANY(%s)
                """,
                (user_pk, args.term_version, list(TERM_TITLES)),
            ).rowcount
            assert inserted == len(TERM_TITLES)

            # 아래 case들은 중복 동의, 존재하지 않는 약관/FK, 중복 계정, 형식 오류가
            # 애플리케이션 검증을 우회해도 DB 제약에서 차단되는지 확인한다.
            expect_violation(
                connection,
                """
                INSERT INTO user_agreements (
                    user_id, term_code, term_version, is_required, is_agreed, agreed_at
                ) VALUES (%s, %s, %s, true, true, now())
                """,
                (user_pk, "A1_THIRD_PARTY", args.term_version),
            )
            expect_violation(
                connection,
                """
                INSERT INTO user_agreements (
                    user_id, term_code, term_version, is_required, is_agreed, agreed_at
                ) VALUES (%s, %s, %s, true, true, now())
                """,
                (user_pk, "UNKNOWN_TERM", args.term_version),
            )

            duplicate_user_params = (
                user_id,
                "another-hash",
                "중복",
                "990117",
                "01099999999",
                f"other-{suffix}@example.test",
            )
            expect_violation(
                connection,
                """
                INSERT INTO users (
                    user_id, password_hash, name, birthdate, phone_number,
                    phone_verified, phone_verified_at,
                    email, email_verified, email_verified_at
                ) VALUES (%s, %s, %s, %s, %s, true, now(), %s, true, now())
                """,
                duplicate_user_params,
            )
            duplicate_email_params = (
                f"other{suffix}"[:16],
                "another-hash",
                "중복",
                "990117",
                "01099999999",
                email,
            )
            expect_violation(
                connection,
                """
                INSERT INTO users (
                    user_id, password_hash, name, birthdate, phone_number,
                    phone_verified, phone_verified_at,
                    email, email_verified, email_verified_at
                ) VALUES (%s, %s, %s, %s, %s, true, now(), %s, true, now())
                """,
                duplicate_email_params,
            )
            expect_violation(
                connection,
                """
                INSERT INTO user_agreements (
                    user_id, term_code, term_version, is_required, is_agreed, agreed_at
                ) VALUES (%s, %s, %s, true, true, now())
                """,
                (user_pk + 9_000_000_000, "A1_THIRD_PARTY", args.term_version),
            )
            expect_violation(
                connection,
                """
                INSERT INTO users (
                    user_id, password_hash, name, birthdate, phone_number,
                    email
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                ("bad!id", "hash", "테스트", "990117", "01012345678", f"bad-{email}"),
            )
        finally:
            # 성공/실패와 관계없이 integration test write를 실제 DB에 남기지 않는다.
            connection.rollback()

    print("signup schema verification passed (all test writes rolled back)")


if __name__ == "__main__":
    main()
