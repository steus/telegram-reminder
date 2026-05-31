"""membership_request + group.invite_code."""

from __future__ import annotations

import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _new_invite_code(existing: set[str]) -> str:
    while True:
        code = secrets.token_hex(4)
        if code not in existing:
            existing.add(code)
            return code


def upgrade() -> None:
    connection = op.get_bind()
    insp = inspect(connection)
    group_cols = {col["name"] for col in insp.get_columns("group")}

    if "invite_code" not in group_cols:
        op.add_column(
            "group",
            sa.Column("invite_code", sa.String(length=16), nullable=True),
        )

    existing_codes = {
        row[0]
        for row in connection.execute(
            sa.text('SELECT invite_code FROM "group" WHERE invite_code IS NOT NULL')
        )
    }
    rows = connection.execute(
        sa.text('SELECT id FROM "group" WHERE invite_code IS NULL OR invite_code = ""')
    ).fetchall()
    for (group_id,) in rows:
        code = _new_invite_code(existing_codes)
        connection.execute(
            sa.text('UPDATE "group" SET invite_code = :code WHERE id = :id'),
            {"code": code, "id": group_id},
        )

    # SQLite: alter nullable via batch if still nullable
    group_cols = {col["name"] for col in inspect(connection).get_columns("group")}
    if "invite_code" in group_cols:
        invite_col = next(
            col for col in inspect(connection).get_columns("group") if col["name"] == "invite_code"
        )
        if invite_col.get("nullable", True):
            with op.batch_alter_table("group") as batch_op:
                batch_op.alter_column("invite_code", nullable=False)

    unique_names = {
        uc["name"]
        for uc in inspect(connection).get_unique_constraints("group")
    }
    indexes = {idx["name"] for idx in inspect(connection).get_indexes("group")}
    if "uq_group_invite_code" not in unique_names and "uq_group_invite_code" not in indexes:
        op.create_index("uq_group_invite_code", "group", ["invite_code"], unique=True)

    if "membership_request" not in insp.get_table_names():
        op.create_table(
            "membership_request",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("group_id", sa.Integer(), nullable=False),
            sa.Column("telegram_chat_id", sa.String(length=64), nullable=False),
            sa.Column("telegram_username", sa.String(length=64), nullable=True),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("resolved_by_chat_id", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("(CURRENT_TIMESTAMP)"),
                nullable=False,
            ),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["group_id"], ["group.id"]),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    connection = op.get_bind()
    insp = inspect(connection)
    if "membership_request" in insp.get_table_names():
        op.drop_table("membership_request")
    unique_names = {
        uc["name"]
        for uc in inspect(connection).get_unique_constraints("group")
    }
    indexes = {idx["name"] for idx in inspect(connection).get_indexes("group")}
    if "uq_group_invite_code" in indexes:
        op.drop_index("uq_group_invite_code", table_name="group")
    elif "uq_group_invite_code" in unique_names:
        op.drop_constraint("uq_group_invite_code", "group", type_="unique")
    group_cols = {col["name"] for col in insp.get_columns("group")}
    if "invite_code" in group_cols:
        op.drop_column("group", "invite_code")
