"""retire legacy financial PostgreSQL schemas

Revision ID: 20260816_0010
Revises: 20260815_0009
Create Date: 2026-08-16

The legacy financial/API structures were intentionally retired after proving
that Azure Blob Storage contains the complete canonical Raw dataset. Membership
objects live in public and are not touched by this migration.
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260816_0010"
down_revision: str | None = "20260815_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS raw CASCADE")
    op.execute("DROP SCHEMA IF EXISTS processed CASCADE")


def downgrade() -> None:
    raise RuntimeError(
        "20260816_0010 is intentionally irreversible; rebuild financial schemas "
        "with a new forward migration instead"
    )
