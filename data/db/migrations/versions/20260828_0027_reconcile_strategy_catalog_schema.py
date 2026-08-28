"""누락될 수 있는 전략 카탈로그 스키마를 현재 계약으로 복구한다.

Revision ID: 20260828_0027
Revises: 20260828_0026
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260828_0027"
down_revision: str | None = "20260828_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """버전만 0025로 기록된 DB도 전략 카탈로그 계약을 만족하게 복구한다."""

    # 일부 공용 DB는 0025 revision만 기록되고 실제 DDL이 누락되었다. 정상 DB와
    # 드리프트 DB 모두에서 같은 forward migration을 실행할 수 있도록 멱등 DDL을 쓴다.
    op.execute(
        """
        ALTER TABLE strategies
          ADD COLUMN IF NOT EXISTS product_group VARCHAR(20),
          ADD COLUMN IF NOT EXISTS availability_status VARCHAR(20),
          ADD COLUMN IF NOT EXISTS engine_key VARCHAR(50),
          ADD COLUMN IF NOT EXISTS display_order SMALLINT
        """
    )

    # 기존 FK가 참조하는 전략 식별자는 유지하고 0025의 카탈로그 의미만 복원한다.
    op.execute(
        """
        UPDATE strategies
        SET name = '물림방지 전략',
            description = 'BOCPD·HMM·BMA·Kelly 기반 자체 알고리즘으로 위험 국면의 노출을 줄입니다.',
            risk_level = 'MEDIUM',
            rebalance_cycle = 'DAILY',
            rule_config = jsonb_build_object(
              'engine', 'algorithm_v2_3',
              'model_version', '2.3',
              'snapshot_contract', 'loss-avoidance-v1',
              'cash_buffer_max', 0.05,
              'universe_rule', 'latest_60d_median_trading_value'
            ),
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
            'MEDIUM', 'DAILY', jsonb_build_object('engine', 'stat_arb_v1'), true,
            'BANG', 'TESTING', 'stat_arb_v1', 30
          ),
          (
            'event_driven', '이벤트 드리븐 전략',
            '공시와 뉴스 등 시장 이벤트를 활용합니다.',
            'HIGH', 'EVENT', jsonb_build_object('engine', 'event_driven_v1'), true,
            'BANG', 'TESTING', 'event_driven_v1', 40
          )
        ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name,
            description = EXCLUDED.description,
            risk_level = EXCLUDED.risk_level,
            rebalance_cycle = EXCLUDED.rebalance_cycle,
            rule_config = EXCLUDED.rule_config,
            is_active = EXCLUDED.is_active,
            product_group = EXCLUDED.product_group,
            availability_status = EXCLUDED.availability_status,
            engine_key = EXCLUDED.engine_key,
            display_order = EXCLUDED.display_order
        """
    )

    # 예상하지 못한 기존 전략은 삭제하지 않고 테스트 중인 방 전략으로 보존한다.
    # 모든 행을 채운 뒤 NOT NULL을 적용해야 과거 데이터 때문에 복구가 중단되지 않는다.
    op.execute(
        """
        UPDATE strategies
        SET product_group = COALESCE(product_group, 'BANG'),
            availability_status = COALESCE(availability_status, 'TESTING'),
            engine_key = COALESCE(engine_key, LEFT('legacy_' || id, 50)),
            display_order = COALESCE(display_order, 1000)
        WHERE product_group IS NULL
           OR availability_status IS NULL
           OR engine_key IS NULL
           OR display_order IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE strategies
          ALTER COLUMN product_group SET NOT NULL,
          ALTER COLUMN availability_status SET NOT NULL,
          ALTER COLUMN engine_key SET NOT NULL,
          ALTER COLUMN display_order SET NOT NULL
        """
    )

    # PostgreSQL은 ADD CONSTRAINT IF NOT EXISTS를 지원하지 않으므로 catalog에서
    # 이름을 확인한다. 0025가 정상 적용된 DB의 기존 제약은 그대로 보존한다.
    op.execute(
        """
        DO $migration$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = to_regclass('strategies')
              AND conname = 'ck_strategies_product_group_values'
          ) THEN
            ALTER TABLE strategies
              ADD CONSTRAINT ck_strategies_product_group_values
              CHECK (product_group IN ('MUL', 'BANG'));
          END IF;
        END
        $migration$
        """
    )
    op.execute(
        """
        DO $migration$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = to_regclass('strategies')
              AND conname = 'ck_strategies_availability_status_values'
          ) THEN
            ALTER TABLE strategies
              ADD CONSTRAINT ck_strategies_availability_status_values
              CHECK (availability_status IN ('AVAILABLE', 'TESTING'));
          END IF;
        END
        $migration$
        """
    )
    op.execute(
        """
        DO $migration$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = to_regclass('strategies')
              AND conname = 'ck_strategies_display_order_positive'
          ) THEN
            ALTER TABLE strategies
              ADD CONSTRAINT ck_strategies_display_order_positive
              CHECK (display_order > 0);
          END IF;
        END
        $migration$
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_strategies_catalog_order
        ON strategies (product_group, display_order)
        """
    )


def downgrade() -> None:
    """0025가 원래 보장하는 스키마이므로 복구 결과를 제거하지 않는다."""

    # 0027은 새 기능이 아니라 0025의 실제 상태를 복구한다. 여기서 컬럼을 제거하면
    # 0026 애플리케이션 계약까지 깨지므로 revision만 되돌리고 스키마는 유지한다.
    pass
