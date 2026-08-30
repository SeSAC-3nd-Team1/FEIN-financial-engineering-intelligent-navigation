"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    # 비직관적이거나 파괴적인 schema/data 변경은 왜 필요한지와 보호 대상을 한국어로 설명한다.
    # 과거 migration은 현재 ORM/model import에 의존하지 않고 self-contained하게 작성한다.
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    # rollback 시 데이터 손실 가능성이나 복구 전제조건이 있다면 한국어 주석으로 명시한다.
    ${downgrades if downgrades else "pass"}
