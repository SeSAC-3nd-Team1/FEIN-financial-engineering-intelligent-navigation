"""회원가입의 영구/임시 관계형 데이터를 제3정규형으로 정의한다."""

from datetime import datetime
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models.common import TimestampMixin


class User(TimestampMixin, Base):
    """가입이 완료되고 휴대폰/이메일 검증까지 끝난 계정만 저장한다.

    인증 여부는 `*_verified_at`의 NULL 여부에서 파생한다. 같은 사실을 boolean으로
    중복 저장하지 않아 갱신 시 상태가 어긋나는 문제를 막는다.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_users_user_id"),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("ci_lookup_hash", name="uq_users_ci_lookup_hash"),
        CheckConstraint("user_id ~ '^[a-z0-9]{6,16}$'", name="user_id_format"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 30", name="name_length"),
        CheckConstraint("birthdate ~ '^[0-9]{6}$'", name="birthdate_format"),
        CheckConstraint(
            "phone_number ~ '^0[0-9]{9,10}$'",
            name="phone_number_format",
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
    phone_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # CI/DI는 민감 식별정보이므로 복호화용 ciphertext와 중복 탐색용 keyed HMAC을 분리한다.
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
    """약관을 code + version 단위의 불변 catalog로 보존한다."""

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
    """가입 완료 회원과 특정 약관 version의 동의 사실만 저장한다.

    약관 code/version/필수 여부는 `terms`에 종속되므로 이 테이블에 복제하지 않는다.
    회원은 soft delete가 원칙이며 감사 행의 물리 삭제를 막기 위해 FK는 RESTRICT다.
    """

    __tablename__ = "user_agreements"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "term_id",
            name="uq_user_agreements_user_term_id",
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
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    term_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("terms.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_agreed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    agreed_ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(512))


class RegistrationSession(Base):
    """가입 완료 전 개인정보와 검증 완료 시각을 짧게 보관하는 임시 관계다.

    OTP/비밀번호/token은 저장하지 않는다. 기본 TTL은 30분이며 가입 완료 후에는
    별도 정리 작업으로 개인정보를 신속히 제거하는 것을 전제로 한다.
    """

    __tablename__ = "registration_sessions"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 30", name="name_length"),
        CheckConstraint("birthdate ~ '^[0-9]{6}$'", name="birthdate_format"),
        CheckConstraint(
            "phone_number ~ '^0[0-9]{9,10}$'",
            name="phone_number_format",
        ),
        CheckConstraint(
            "email IS NULL OR email = lower(email)",
            name="email_lowercase",
        ),
        CheckConstraint(
            "email_verified_at IS NULL OR email IS NOT NULL",
            name="email_verification_has_target",
        ),
        CheckConstraint("expires_at > created_at", name="expires_after_created"),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="completion_after_created",
        ),
        Index("ix_registration_sessions_phone_number", "phone_number"),
    )

    id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True), default=uuid4, primary_key=True
    )
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    birthdate: Mapped[str] = mapped_column(String(6), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(11), nullable=False)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email: Mapped[str | None] = mapped_column(String(255))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("(now() + interval '30 minutes')"),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RegistrationAgreement(Base):
    """가입 세션과 특정 약관 version 사이의 선택 상태를 저장한다."""

    __tablename__ = "registration_agreements"
    __table_args__ = (
        CheckConstraint(
            "(is_agreed AND agreed_at IS NOT NULL) OR "
            "(NOT is_agreed AND agreed_at IS NULL)",
            name="agreement_timestamp_consistency",
        ),
    )

    registration_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("registration_sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    term_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("terms.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    is_agreed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    agreed_ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(512))
