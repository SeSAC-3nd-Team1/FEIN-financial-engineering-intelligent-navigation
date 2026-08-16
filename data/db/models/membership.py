"""회원가입 이후 영구 보존되는 계정과 약관 동의 관계형 모델을 정의한다."""

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
    """가입 완료 계정만 저장하며 가입 전 인증 상태는 영구 DB에 두지 않는다.

    형식 검증과 상태 일관성은 애플리케이션 코드에만 의존하지 않고 DB CheckConstraint로도
    보장한다. CI/DI 원문은 평문으로 저장하지 않고 암호화 값과 lookup hash를 분리한다.
    """

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
    # CI/DI는 민감 식별정보이므로 검색용 hash와 복호화가 필요한 encrypted value를 분리한다.
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
    """회원가입에서 동의할 수 있는 약관을 code + version 단위로 보존한다.

    약관 내용이 바뀌어도 과거 사용자가 어느 version에 동의했는지 재현할 수 있도록
    기존 row를 덮어쓰지 않고 새 version을 추가하는 구조다.
    """

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
    """사용자와 특정 약관 version의 동의 사실을 감사 가능한 형태로 보존한다.

    동의 시각/IP/User-Agent를 함께 남기고, 같은 사용자·약관·version 조합은 한 번만
    기록되도록 UNIQUE 제약을 둔다.
    """

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
