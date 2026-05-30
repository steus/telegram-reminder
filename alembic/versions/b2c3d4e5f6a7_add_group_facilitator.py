"""group_facilitator: несколько ведущих на группу."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "group_facilitator",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["group.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "group_id", "telegram_chat_id", name="uq_group_facilitator"
        ),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO group_facilitator (group_id, telegram_chat_id)
            SELECT id, facilitator_chat_id FROM "group"
            WHERE facilitator_chat_id IS NOT NULL AND facilitator_chat_id != ''
            """
        )
    )


def downgrade() -> None:
    op.drop_table("group_facilitator")
