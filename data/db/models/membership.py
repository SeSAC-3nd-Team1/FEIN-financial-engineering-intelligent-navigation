"""Persistent membership and registration-consent models."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models.common import TimestampMixin


class User(TimestampMixin, Base):
    """Registered account; pre-signup verification state is deliberately absent."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_users_user_id"),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("ci_lookup_hash", name="uq_users_ci_lookup_hash"),
        CheckConstraint(
            "user_id ~ '^[a-z0-9]{6,16}$'",
            name="user_id_format",
        ),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 30", name="name_length"),
        CheckConstraint("birthdate ~ '^[0-9]{6}$'", name="birthdate_format"),
        CheckConstraint(
            "phone_number ~ '^0[0-9]{9,10}$'",
            name="phone_number_format",
        ),
        CheckConstraint(
            "(phone_verified AND phone_verified_at IS NOT NULL) OR "
            "(NOT phone_verified AND phone_verified_at IS NULL)",
            name="phone_verification_consistency",
        ),
        CheckConstraint(
            "(email_verified AND email_verified_at IS NOT NULL) OR "
            "(NOT email_verified AND email_verified_at IS NULL)",
            name="email_verification_consistency",
        ),
        CheckConstraint(
            "member_type IN ('ASSOCIATE', 'FULL')",
            name="member_type_values",
        ),
        CheckConstraint(
            "account_status IN ('ACTIVE', 'DORMANT', 'SUSPENDED', 'WITHDRAWN')",
            name="account_status_values",
        ),
        CheckConstraint(
            "(account_status = 'WITHDRAWN' AND deleted_at IS NOT NULL) OR "
            "(account_status <> 'WITHDRAWN')",
            name="withdrawn_has_deleted_at",
        ),
        Index("ix_users_phone_number", "phone_number"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(16), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    birthdate: Mapped[str] = mapped_column(String(6), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(11), nullable=False)
    phone_verified: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ci_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    ci_lookup_hash: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    di_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    telecom_carrier: Mapped[str | None] = mapped_column(String(20))
    gender: Mapped[str | None] = mapped_column(String(1))
    member_type: Mapped[str] = mapped_column(
        String(20), server_default=text("'ASSOCIATE'"), nullable=False
    )
    account_status: Mapped[str] = mapped_column(
        String(20), server_default=text("'ACTIVE'"), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Term(Base):
    """Versioned catalog of terms that may be accepted during registration."""

    __tablename__ = "terms"
    __table_args__ = (
        UniqueConstraint("term_code", "version", name="uq_terms_code_version"),
        CheckConstraint("length(trim(term_code)) > 0", name="term_code_not_blank"),
        CheckConstraint("length(trim(version)) > 0", name="term_version_not_blank"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    term_code: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_reference: Mapped[str | None] = mapped_column(String(500))
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserAgreement(Base):
    """Immutable-style audit row for one user and one versioned term."""

    __tablename__ = "user_agreements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["term_code", "term_version"],
            ["terms.term_code", "terms.version"],
            name="fk_user_agreements_term_terms",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "user_id",
            "term_code",
            "term_version",
            name="uq_user_agreements_user_term_version",
        ),
        CheckConstraint(
            "(is_agreed AND agreed_at IS NOT NULL) OR "
            "(NOT is_agreed AND agreed_at IS NULL)",
            name="agreement_timestamp_consistency",
        ),
        Index("ix_user_agreements_user_agreed_at", "user_id", "agreed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    term_code: Mapped[str] = mapped_column(String(30), nullable=False)
    term_version: Mapped[str] = mapped_column(String(20), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_agreed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    agreed_ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(512))
