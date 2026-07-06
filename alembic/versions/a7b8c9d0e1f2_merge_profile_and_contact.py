"""merge member_profile and member contact branches."""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = ("e5f6a7b8c9d0", "f6a7b8c9d0e1")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
