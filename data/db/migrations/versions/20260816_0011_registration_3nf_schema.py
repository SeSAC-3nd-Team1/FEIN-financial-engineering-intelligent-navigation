"""회원가입 관계를 3NF 목표 스키마로 전환한다.

Revision ID: 20260816_0011
Revises: 20260816_0010
Create Date: 2026-08-16

기존 회원/동의 데이터를 조용히 버리지 않는다. 인증 시각이 없는 기존 회원이나
terms catalog와 연결할 수 없는 동의 행이 있으면 migration을 명시적으로 중단한다.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260816_0011"
down_revision: str | None = "20260816_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 목표 users는 가입 완료 계정만 저장하므로 두 인증 시각이 반드시 있어야 한다.
    # 과거 데이터가 이 전제를 만족하지 않으면 임의 시각을 만들어 넣지 않고 중단한다.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM users
                WHERE phone_verified_at IS NULL
                   OR email_verified_at IS NULL
            ) THEN
                RAISE EXCEPTION
                    '20260816_0011 preflight failed: users contains rows without verification timestamps';
            END IF;
        END;
        $$
        """
    )

    # 약관 code/version을 새 surrogate FK인 term_id로 먼저 backfill한다.
    op.add_column(
        "user_agreements",
        sa.Column("term_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        UPDATE user_agreements AS ua
        SET term_id = t.id
        FROM terms AS t
        WHERE t.term_code = ua.term_code
          AND t.version = ua.term_version
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM user_agreements
                WHERE term_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    '20260816_0011 preflight failed: user agreement cannot be mapped to terms.id';
            END IF;
        END;
        $$
        """
    )

    op.drop_constraint(
        "uq_user_agreements_user_term_version",
        "user_agreements",
        type_="unique",
    )
    op.drop_constraint(
        "fk_user_agreements_term_terms",
        "user_agreements",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_user_agreements_user_id_users",
        "user_agreements",
        type_="foreignkey",
    )

    op.drop_column("user_agreements", "is_required")
    op.drop_column("user_agreements", "term_version")
    op.drop_column("user_agreements", "term_code")
    op.alter_column(
        "user_agreements",
        "term_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_user_agreements_user_id_users",
        "user_agreements",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_user_agreements_term_id_terms",
        "user_agreements",
        "terms",
        ["term_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_user_agreements_user_term_id",
        "user_agreements",
        ["user_id", "term_id"],
    )

    # 인증 여부 boolean은 timestamp에서 완전히 파생되므로 중복 상태를 제거한다.
    op.drop_constraint(
        "ck_users_phone_verification_consistency", "users", type_="check"
    )
    op.drop_constraint(
        "ck_users_email_verification_consistency", "users", type_="check"
    )
    op.alter_column(
        "users",
        "phone_verified_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.alter_column(
        "users",
        "email_verified_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
    op.drop_column("users", "phone_verified")
    op.drop_column("users", "email_verified")

    # 가입 전 개인정보는 users와 분리된 TTL 대상 관계에 저장한다.
    op.create_table(
        "registration_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("birthdate", sa.String(length=6), nullable=False),
        sa.Column("phone_number", sa.String(length=11), nullable=False),
        sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() + interval '30 minutes')"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 30",
            name="ck_registration_sessions_name_length",
        ),
        sa.CheckConstraint(
            "birthdate ~ '^[0-9]{6}$'",
            name="ck_registration_sessions_birthdate_format",
        ),
        sa.CheckConstraint(
            "phone_number ~ '^0[0-9]{9,10}$'",
            name="ck_registration_sessions_phone_number_format",
        ),
        sa.CheckConstraint(
            "email IS NULL OR email = lower(email)",
            name="ck_registration_sessions_email_lowercase",
        ),
        sa.CheckConstraint(
            "email_verified_at IS NULL OR email IS NOT NULL",
            name="ck_registration_sessions_email_verification_has_target",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_registration_sessions_expires_after_created",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="ck_registration_sessions_completion_after_created",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_registration_sessions"),
    )
    op.create_index(
        "ix_registration_sessions_phone_number",
        "registration_sessions",
        ["phone_number"],
    )

    # 가입 전 약관 선택도 약관 catalog의 PK만 참조해 3NF를 유지한다.
    op.create_table(
        "registration_agreements",
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("term_id", sa.BigInteger(), nullable=False),
        sa.Column("is_agreed", sa.Boolean(), nullable=False),
        sa.Column("agreed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agreed_ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.CheckConstraint(
            "(is_agreed AND agreed_at IS NOT NULL) OR "
            "(NOT is_agreed AND agreed_at IS NULL)",
            name="ck_registration_agreements_agreement_timestamp_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["registration_id"],
            ["registration_sessions.id"],
            name="fk_registration_agreements_registration_id_registration_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["term_id"],
            ["terms.id"],
            name="fk_registration_agreements_term_id_terms",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "registration_id",
            "term_id",
            name="pk_registration_agreements",
        ),
    )


def downgrade() -> None:
    op.drop_table("registration_agreements")
    op.drop_index(
        "ix_registration_sessions_phone_number",
        table_name="registration_sessions",
    )
    op.drop_table("registration_sessions")

    # boolean은 현재 target timestamp가 NOT NULL이므로 모두 true로 안전하게 복원할 수 있다.
    op.add_column(
        "users",
        sa.Column(
            "phone_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=True,
        ),
    )
    op.execute("UPDATE users SET phone_verified = true, email_verified = true")
    op.alter_column(
        "users",
        "phone_verified",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )
    op.alter_column(
        "users",
        "email_verified",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )
    op.alter_column(
        "users",
        "phone_verified_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "users",
        "email_verified_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_users_phone_verification_consistency",
        "users",
        "(phone_verified AND phone_verified_at IS NOT NULL) OR "
        "(NOT phone_verified AND phone_verified_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_users_email_verification_consistency",
        "users",
        "(email_verified AND email_verified_at IS NOT NULL) OR "
        "(NOT email_verified AND email_verified_at IS NULL)",
    )

    op.add_column(
        "user_agreements",
        sa.Column("term_code", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "user_agreements",
        sa.Column("term_version", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "user_agreements",
        sa.Column("is_required", sa.Boolean(), nullable=True),
    )
    op.execute(
        """
        UPDATE user_agreements AS ua
        SET term_code = t.term_code,
            term_version = t.version,
            is_required = t.is_required
        FROM terms AS t
        WHERE t.id = ua.term_id
        """
    )

    op.drop_constraint(
        "uq_user_agreements_user_term_id",
        "user_agreements",
        type_="unique",
    )
    op.drop_constraint(
        "fk_user_agreements_term_id_terms",
        "user_agreements",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_user_agreements_user_id_users",
        "user_agreements",
        type_="foreignkey",
    )

    op.alter_column(
        "user_agreements",
        "term_code",
        existing_type=sa.String(length=30),
        nullable=False,
    )
    op.alter_column(
        "user_agreements",
        "term_version",
        existing_type=sa.String(length=20),
        nullable=False,
    )
    op.alter_column(
        "user_agreements",
        "is_required",
        existing_type=sa.Boolean(),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_user_agreements_term_terms",
        "user_agreements",
        "terms",
        ["term_code", "term_version"],
        ["term_code", "version"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_user_agreements_user_id_users",
        "user_agreements",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_user_agreements_user_term_version",
        "user_agreements",
        ["user_id", "term_code", "term_version"],
    )
    op.drop_column("user_agreements", "term_id")
