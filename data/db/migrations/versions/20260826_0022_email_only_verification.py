"""휴대폰 인증 도입 전까지 회원의 휴대폰 인증 시각을 선택 값으로 전환한다.

Revision ID: 20260826_0022
Revises: 20260825_0021
Create Date: 2026-08-26
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260826_0022"
down_revision: str | None = "20260825_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """이메일 인증 회원도 가입할 수 있도록 휴대폰 인증 시각의 필수 제약을 해제한다."""

    op.alter_column(
        "users",
        "phone_verified_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )


def downgrade() -> None:
    """미인증 휴대폰 데이터가 없을 때만 기존 필수 제약으로 되돌린다."""

    # NULL을 임의의 인증 시각으로 채우면 실제로 하지 않은 인증을 했다고 기록하게 되므로,
    # 복원 가능한 데이터 상태인지 먼저 확인하고 그렇지 않으면 명시적으로 중단한다.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM users WHERE phone_verified_at IS NULL) THEN
                RAISE EXCEPTION
                    'cannot restore users.phone_verified_at NOT NULL while unverified users exist';
            END IF;
        END
        $$
        """
    )
    op.alter_column(
        "users",
        "phone_verified_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
