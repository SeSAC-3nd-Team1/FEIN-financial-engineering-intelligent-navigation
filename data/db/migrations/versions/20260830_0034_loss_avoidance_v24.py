"""물림방지 전략의 실행 엔진을 Algorithm v2.4 fix2로 승격한다."""

from collections.abc import Sequence

from alembic import op


revision: str = "20260830_0034"
down_revision: str | None = "20260829_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """기존 low 식별자를 유지하면서 모델 버전 계약만 v2.4 fix2로 갱신한다."""

    # low는 기존 계좌와 주문이 참조하므로 식별자는 변경하지 않는다. 모델 버전과
    # engine_key만 갱신해 이후 생성되는 스냅샷이 반드시 v2.4인지 카탈로그에서도
    # 확인할 수 있게 한다.
    op.execute(
        """
        UPDATE strategies
        SET rule_config = jsonb_set(
              jsonb_set(rule_config, '{engine}', '"algorithm_v2_4_fix2"'),
              '{model_version}', '"2.4-fix2"'
            ),
            engine_key = 'algorithm_v2_4_fix2'
        WHERE id = 'low'
        """
    )


def downgrade() -> None:
    """물림방지 전략을 직전 v2.4 계약으로 되돌린다."""

    op.execute(
        """
        UPDATE strategies
        SET rule_config = jsonb_set(
              jsonb_set(rule_config, '{engine}', '"algorithm_v2_4"'),
              '{model_version}', '"2.4"'
            ),
            engine_key = 'algorithm_v2_4'
        WHERE id = 'low'
        """
    )
