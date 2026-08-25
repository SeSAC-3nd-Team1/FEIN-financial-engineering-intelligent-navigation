"""사용자의 현재 활성 운용방식을 별도 계좌 선택으로 저장한다.

Revision ID: 20260825_0021
Revises: 20260825_0020
Create Date: 2026-08-25
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260825_0021"
down_revision: str | None = "20260825_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """계좌의 운용방식을 바꾸지 않고 사용자가 현재 보는 방식만 저장한다."""

    op.add_column(
        "users",
        sa.Column("active_operation_mode", sa.String(20), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("operation_mode_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "active_operation_mode_values",
        "users",
        "active_operation_mode IN ('AUTO', 'SEMI_AUTO')",
    )

    # 기존 사용자는 가장 최근에 완료한 투자 시작 방식으로 복원한다. 완료 이력이 없고 활성 계좌가
    # 정확히 하나뿐인 경우에만 그 계좌를 사용하며, 복수 계좌의 우선순위는 임의로 추측하지 않는다.
    op.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (onboarding.user_id)
                   onboarding.user_id,
                   onboarding.operation_mode,
                   onboarding.completed_at,
                   onboarding.updated_at,
                   onboarding.created_at
            FROM investment_onboardings AS onboarding
            WHERE onboarding.status = 'COMPLETED'
            ORDER BY onboarding.user_id,
                     onboarding.completed_at DESC NULLS LAST,
                     onboarding.updated_at DESC,
                     onboarding.created_at DESC
        )
        UPDATE users AS member
        SET active_operation_mode = latest.operation_mode,
            operation_mode_changed_at = COALESCE(
                latest.completed_at,
                latest.updated_at,
                latest.created_at
            )
        FROM latest
        WHERE latest.user_id = member.id
        """
    )
    op.execute(
        """
        WITH single_account AS (
            SELECT account.user_id,
                   min(account.operation_mode) AS operation_mode,
                   min(account.created_at) AS created_at
            FROM virtual_accounts AS account
            WHERE account.status = 'ACTIVE'
            GROUP BY account.user_id
            HAVING count(*) = 1
        )
        UPDATE users AS member
        SET active_operation_mode = single_account.operation_mode,
            operation_mode_changed_at = single_account.created_at
        FROM single_account
        WHERE single_account.user_id = member.id
          AND member.active_operation_mode IS NULL
        """
    )


def downgrade() -> None:
    """계좌와 거래 데이터는 유지하고 현재 선택 정보만 제거한다."""

    op.drop_constraint("active_operation_mode_values", "users", type_="check")
    op.drop_column("users", "operation_mode_changed_at")
    op.drop_column("users", "active_operation_mode")
