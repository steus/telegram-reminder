"""member profile (jtbd onboarding)."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    insp = inspect(connection)
    if "member_profile" not in insp.get_table_names():
        op.create_table(
            "member_profile",
            sa.Column("member_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("profile_json", sa.Text(), nullable=False),
            sa.Column("onboarding_buffer", sa.Text(), nullable=False),
            sa.Column("progress_json", sa.Text(), nullable=False),
            sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["member_id"], ["member.id"]),
            sa.PrimaryKeyConstraint("member_id"),
        )


def downgrade() -> None:
    connection = op.get_bind()
    insp = inspect(connection)
    if "member_profile" in insp.get_table_names():
        op.drop_table("member_profile")
