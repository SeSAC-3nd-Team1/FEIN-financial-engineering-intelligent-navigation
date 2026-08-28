"""물·방·개 전략 카탈로그와 실행 엔진 메타데이터를 추가한다.

Revision ID: 20260828_0025
Revises: 20260827_0024
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260828_0025"
down_revision: str | None = "20260827_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """기존 식별자를 보존하면서 서비스 전략 체계를 정식 카탈로그로 전환한다."""

    op.add_column(
        "strategies",
        sa.Column("product_group", sa.String(20), nullable=True),
    )
    op.add_column(
        "strategies",
        sa.Column("availability_status", sa.String(20), nullable=True),
    )
    op.add_column(
        "strategies",
        sa.Column("engine_key", sa.String(50), nullable=True),
    )
    op.add_column(
        "strategies",
        sa.Column("display_order", sa.SmallInteger(), nullable=True),
    )

    # low 식별자는 계좌·온보딩·주문 이력이 참조하므로 바꾸지 않고 의미만 물림방지로
    # 전환한다. 이렇게 해야 기존 계좌 FK와 멱등 처리 이력을 안전하게 보존할 수 있다.
    op.execute(
        """
        UPDATE strategies
        SET name = '물림방지 전략',
            description = 'BOCPD·HMM·BMA·Kelly 기반 자체 알고리즘으로 위험 국면의 노출을 줄입니다.',
            risk_level = 'MEDIUM',
            rebalance_cycle = 'DAILY',
            rule_config = '{
              "engine":"algorithm_v2_3",
              "model_version":"2.3",
              "snapshot_contract":"loss-avoidance-v1",
              "cash_buffer_max":0.05,
              "universe_rule":"latest_60d_median_trading_value"
            }'::jsonb,
            product_group = 'MUL',
            availability_status = 'AVAILABLE',
            engine_key = 'algorithm_v2_3',
            display_order = 10
        WHERE id = 'low'
        """
    )
    op.execute(
        """
        UPDATE strategies
        SET name = '가치주 전략',
            product_group = 'BANG',
            availability_status = 'TESTING',
            engine_key = 'value_factor_v1',
            display_order = 20
        WHERE id = 'value'
        """
    )
    op.execute(
        """
        UPDATE strategies
        SET product_group = 'BANG',
            availability_status = 'AVAILABLE',
            engine_key = 'price_momentum_v1',
            display_order = 10
        WHERE id = 'momentum'
        """
    )
    op.execute(
        """
        INSERT INTO strategies (
          id, name, description, risk_level, rebalance_cycle, rule_config,
          is_active, product_group, availability_status, engine_key, display_order
        ) VALUES
          (
            'stat_arb', '통계적 차익거래 전략',
            '종목 간 가격 관계와 통계적 패턴을 활용합니다.',
            'MEDIUM', 'DAILY', '{"engine":"stat_arb_v1"}', true,
            'BANG', 'TESTING', 'stat_arb_v1', 30
          ),
          (
            'event_driven', '이벤트 드리븐 전략',
            '공시와 뉴스 등 시장 이벤트를 활용합니다.',
            'HIGH', 'EVENT', '{"engine":"event_driven_v1"}', true,
            'BANG', 'TESTING', 'event_driven_v1', 40
          )
        """
    )

    op.alter_column("strategies", "product_group", nullable=False)
    op.alter_column("strategies", "availability_status", nullable=False)
    op.alter_column("strategies", "engine_key", nullable=False)
    op.alter_column("strategies", "display_order", nullable=False)
    op.create_check_constraint(
        "product_group_values",
        "strategies",
        "product_group IN ('MUL', 'BANG')",
    )
    op.create_check_constraint(
        "availability_status_values",
        "strategies",
        "availability_status IN ('AVAILABLE', 'TESTING')",
    )
    op.create_check_constraint(
        "display_order_positive",
        "strategies",
        "display_order > 0",
    )
    op.create_index(
        "ix_strategies_catalog_order",
        "strategies",
        ["product_group", "display_order"],
    )


def downgrade() -> None:
    """추가 전략을 제거하고 기존 3개 전략 카탈로그를 복원한다."""

    op.execute("DELETE FROM strategies WHERE id IN ('stat_arb', 'event_driven')")
    op.execute(
        """
        UPDATE strategies
        SET name = '저변동성 전략',
            description = '큰 손실을 줄이고 꾸준한 투자를 지향합니다.',
            risk_level = 'MEDIUM',
            rebalance_cycle = 'MONTHLY',
            rule_config = '{"factor":"low_volatility"}'::jsonb
        WHERE id = 'low'
        """
    )
    op.execute("UPDATE strategies SET name = '가치 전략' WHERE id = 'value'")
    op.drop_index("ix_strategies_catalog_order", table_name="strategies")
    op.drop_constraint(
        op.f("ck_strategies_display_order_positive"),
        "strategies",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_strategies_availability_status_values"),
        "strategies",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_strategies_product_group_values"),
        "strategies",
        type_="check",
    )
    op.drop_column("strategies", "display_order")
    op.drop_column("strategies", "engine_key")
    op.drop_column("strategies", "availability_status")
    op.drop_column("strategies", "product_group")
