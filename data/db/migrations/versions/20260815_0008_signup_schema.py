"""add persistent signup users, terms, and agreement audit

Revision ID: 20260815_0008
Revises: 20260814_0007
Create Date: 2026-08-15
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260815_0008"
down_revision: str | None = "20260814_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.String(length=16), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("birthdate", sa.String(length=6), nullable=False),
        sa.Column("phone_number", sa.String(length=11), nullable=False),
        sa.Column(
            "phone_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("phone_verified_at", sa.DateTime(timezone=True)),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column(
            "email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("ci_encrypted", sa.LargeBinary()),
        sa.Column("ci_lookup_hash", sa.LargeBinary(length=32)),
        sa.Column("di_encrypted", sa.LargeBinary()),
        sa.Column("telecom_carrier", sa.String(length=20)),
        sa.Column("gender", sa.String(length=1)),
        sa.Column(
            "member_type",
            sa.String(length=20),
            server_default=sa.text("'ASSOCIATE'"),
            nullable=False,
        ),
        sa.Column(
            "account_status",
            sa.String(length=20),
            server_default=sa.text("'ACTIVE'"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "user_id ~ '^[a-z0-9]{6,16}$'", name="ck_users_user_id_format"
        ),
        sa.CheckConstraint(
            "email = lower(email)", name="ck_users_email_lowercase"
        ),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 30", name="ck_users_name_length"
        ),
        sa.CheckConstraint(
            "birthdate ~ '^[0-9]{6}$'", name="ck_users_birthdate_format"
        ),
        sa.CheckConstraint(
            "phone_number ~ '^0[0-9]{9,10}$'",
            name="ck_users_phone_number_format",
        ),
        sa.CheckConstraint(
            "(phone_verified AND phone_verified_at IS NOT NULL) OR "
            "(NOT phone_verified AND phone_verified_at IS NULL)",
            name="ck_users_phone_verification_consistency",
        ),
        sa.CheckConstraint(
            "(email_verified AND email_verified_at IS NOT NULL) OR "
            "(NOT email_verified AND email_verified_at IS NULL)",
            name="ck_users_email_verification_consistency",
        ),
        sa.CheckConstraint(
            "member_type IN ('ASSOCIATE', 'FULL')",
            name="ck_users_member_type_values",
        ),
        sa.CheckConstraint(
            "account_status IN ('ACTIVE', 'DORMANT', 'SUSPENDED', 'WITHDRAWN')",
            name="ck_users_account_status_values",
        ),
        sa.CheckConstraint(
            "(account_status = 'WITHDRAWN' AND deleted_at IS NOT NULL) OR "
            "(account_status <> 'WITHDRAWN')",
            name="ck_users_withdrawn_has_deleted_at",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("user_id", name="uq_users_user_id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("ci_lookup_hash", name="uq_users_ci_lookup_hash"),
    )
    op.create_index("ix_users_phone_number", "users", ["phone_number"])

    op.create_table(
        "terms",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("term_code", sa.String(length=30), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content_reference", sa.String(length=500)),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(term_code)) > 0", name="ck_terms_term_code_not_blank"
        ),
        sa.CheckConstraint(
            "length(trim(version)) > 0", name="ck_terms_term_version_not_blank"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_terms"),
        sa.UniqueConstraint("term_code", "version", name="uq_terms_code_version"),
    )

    op.create_table(
        "user_agreements",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("term_code", sa.String(length=30), nullable=False),
        sa.Column("term_version", sa.String(length=20), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("is_agreed", sa.Boolean(), nullable=False),
        sa.Column("agreed_at", sa.DateTime(timezone=True)),
        sa.Column("agreed_ip", postgresql.INET()),
        sa.Column("user_agent", sa.String(length=512)),
        sa.CheckConstraint(
            "(is_agreed AND agreed_at IS NOT NULL) OR "
            "(NOT is_agreed AND agreed_at IS NULL)",
            name="ck_user_agreements_agreement_timestamp_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["term_code", "term_version"],
            ["terms.term_code", "terms.version"],
            name="fk_user_agreements_term_terms",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_agreements_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_agreements"),
        sa.UniqueConstraint(
            "user_id",
            "term_code",
            "term_version",
            name="uq_user_agreements_user_term_version",
        ),
    )
    op.create_index(
        "ix_user_agreements_user_agreed_at",
        "user_agreements",
        ["user_id", "agreed_at"],
    )

    op.execute(
        """
        CREATE FUNCTION set_users_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW
        EXECUTE FUNCTION set_users_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.execute("DROP FUNCTION IF EXISTS set_users_updated_at()")
    op.drop_index(
        "ix_user_agreements_user_agreed_at", table_name="user_agreements"
    )
    op.drop_table("user_agreements")
    op.drop_table("terms")
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_table("users")
