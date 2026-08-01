"""Merge user status and notification branches

Revision ID: 0052_merge_0049_0051
Revises: 0049_user_status, 0051_clear_notifications
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0052_merge_0049_0051"
down_revision: tuple[str, str] | None = (
    "0049_user_status",
    "0051_clear_notifications",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
