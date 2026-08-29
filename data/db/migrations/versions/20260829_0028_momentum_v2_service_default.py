"""Make the service momentum catalog match its v2 quarterly execution policy."""

from alembic import op


revision = "20260829_0030"
down_revision = "20260828_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE strategies
        SET rebalance_cycle = 'QUARTERLY',
            engine_key = 'risk_adjusted_momentum_v2'
        WHERE id = 'momentum'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE strategies
        SET rebalance_cycle = 'MONTHLY',
            engine_key = 'price_momentum_v1'
        WHERE id = 'momentum'
    """)
