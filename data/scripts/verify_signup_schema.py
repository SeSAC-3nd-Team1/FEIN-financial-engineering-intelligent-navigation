"""회원가입 3NF schema를 실제 PostgreSQL에서 검증하고 모든 test write를 rollback한다."""

import argparse
import uuid

import psycopg
from psycopg import sql

from db.connection import get_database_url
from scripts.seed_signup_terms import TERM_TITLES


EXPECTED_TABLES = {
    "users",
    "terms",
    "user_agreements",
    "registration_sessions",
    "registration_agreements",
}


def expect_violation(connection: psycopg.Connection, query: str, params: tuple) -> None:
    """지정 SQL이 무결성 제약을 위반하는지 독립 savepoint에서 확인한다."""

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
            # 개발 DB에 catalog가 아직 없다면 검증 transaction 안에서만 임시 약관을 만든다.
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

            term_rows = connection.execute(
                """
                SELECT id, term_code
                FROM terms
                WHERE version = %s AND term_code = ANY(%s)
                ORDER BY term_code
                """,
                (args.term_version, list(TERM_TITLES)),
            ).fetchall()
            assert len(term_rows) == len(TERM_TITLES), "seed all six signup terms first"
            term_ids = [row[0] for row in term_rows]

            # ORM metadata가 아니라 migration이 적용된 실제 DB catalog를 확인한다.
            table_names = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = ANY(%s)
                    """,
                    (list(EXPECTED_TABLES),),
                )
            }
            assert table_names == EXPECTED_TABLES

            index_names = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                      AND tablename = ANY(%s)
                    """,
                    (list(EXPECTED_TABLES),),
                )
            }
            assert {
                "uq_users_user_id",
                "uq_users_email",
                "uq_users_ci_lookup_hash",
                "ix_users_phone_number",
                "uq_terms_code_version",
                "uq_user_agreements_user_term_id",
                "ix_user_agreements_user_agreed_at",
                "ix_registration_sessions_phone_number",
                "pk_registration_agreements",
            } <= index_names

            user_columns = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'users'
                    """
                )
            }
            assert "phone_verified" not in user_columns
            assert "email_verified" not in user_columns

            agreement_columns = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = 'user_agreements'
                    """
                )
            }
            assert "term_id" in agreement_columns
            assert {"term_code", "term_version", "is_required"}.isdisjoint(
                agreement_columns
            )

            # 가입 완료 회원은 두 인증 시각이 이미 존재해야 한다.
            user_id = f"test{suffix}"[:16]
            email = f"{suffix}@example.test"
            user_pk = connection.execute(
                """
                INSERT INTO users (
                    user_id, password_hash, name, birthdate, phone_number,
                    phone_verified_at, email, email_verified_at
                )
                VALUES (%s, %s, %s, %s, %s, now(), %s, now())
                RETURNING id
                """,
                (user_id, "integration-test-hash", "테스트", "990117", "01012345678", email),
            ).fetchone()[0]

            inserted = connection.execute(
                """
                INSERT INTO user_agreements (
                    user_id, term_id, is_agreed, agreed_at, agreed_ip, user_agent
                )
                SELECT %s, id, true, now(), '127.0.0.1'::inet, 'schema-verifier'
                FROM terms
                WHERE version = %s AND term_code = ANY(%s)
                """,
                (user_pk, args.term_version, list(TERM_TITLES)),
            ).rowcount
            assert inserted == len(TERM_TITLES)

            # 같은 회원/약관 version 중복과 존재하지 않는 FK는 DB가 차단해야 한다.
            expect_violation(
                connection,
                """
                INSERT INTO user_agreements (
                    user_id, term_id, is_agreed, agreed_at
                ) VALUES (%s, %s, true, now())
                """,
                (user_pk, term_ids[0]),
            )
            expect_violation(
                connection,
                """
                INSERT INTO user_agreements (
                    user_id, term_id, is_agreed, agreed_at
                ) VALUES (%s, %s, true, now())
                """,
                (user_pk, 9_000_000_000),
            )

            # 감사 데이터가 존재하면 회원/약관을 물리 삭제할 수 없어야 한다.
            expect_violation(connection, "DELETE FROM users WHERE id = %s", (user_pk,))
            expect_violation(connection, "DELETE FROM terms WHERE id = %s", (term_ids[0],))

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
                    phone_verified_at, email, email_verified_at
                ) VALUES (%s, %s, %s, %s, %s, now(), %s, now())
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
                    phone_verified_at, email, email_verified_at
                ) VALUES (%s, %s, %s, %s, %s, now(), %s, now())
                """,
                duplicate_email_params,
            )
            expect_violation(
                connection,
                """
                INSERT INTO users (
                    user_id, password_hash, name, birthdate, phone_number,
                    phone_verified_at, email, email_verified_at
                ) VALUES (%s, %s, %s, %s, %s, now(), %s, now())
                """,
                ("bad!id", "hash", "테스트", "990117", "01012345678", f"bad-{email}"),
            )

            # 가입 진행 관계는 session 삭제 시에만 동의 row가 함께 정리되어야 한다.
            registration_id = uuid.uuid4()
            connection.execute(
                """
                INSERT INTO registration_sessions (
                    id, name, birthdate, phone_number, expires_at
                ) VALUES (%s, %s, %s, %s, now() + interval '30 minutes')
                """,
                (registration_id, "테스트", "990117", "01022223333"),
            )
            connection.execute(
                """
                INSERT INTO registration_agreements (
                    registration_id, term_id, is_agreed, agreed_at,
                    agreed_ip, user_agent
                ) VALUES (%s, %s, true, now(), '127.0.0.1'::inet, %s)
                """,
                (registration_id, term_ids[0], "schema-verifier"),
            )
            connection.execute(
                "DELETE FROM registration_sessions WHERE id = %s",
                (registration_id,),
            )
            remaining = connection.execute(
                "SELECT count(*) FROM registration_agreements WHERE registration_id = %s",
                (registration_id,),
            ).fetchone()[0]
            assert remaining == 0
        finally:
            # 성공/실패와 관계없이 검증용 write는 DB에 남기지 않는다.
            connection.rollback()

    print("signup 3NF schema verification passed (all test writes rolled back)")


if __name__ == "__main__":
    main()
