"""Ensure Direction identity group exists

Revision ID: 0048_ensure_direction_group
Revises: 0047_notification_kinds
Create Date: 2026-07-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0048_ensure_direction_group"
down_revision: str | None = "0047_notification_kinds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_INSTITUTION_ID = "a0000000-0000-0000-0000-000000000001"
DIRECTION_GROUP_ID = "grp-dir"


def upgrade() -> None:
    op.execute(
        "ALTER TYPE identity_group_name ADD VALUE IF NOT EXISTS 'DIRECTION'"
    )
    op.execute(
        "INSERT INTO identity_groups (id, name, institution_id) "
        "SELECT "
        f"'{DIRECTION_GROUP_ID}', "
        "'DIRECTION', "
        "COALESCE( "
        "(SELECT id FROM identity_institutions "
        f"WHERE id = '{DEFAULT_INSTITUTION_ID}' LIMIT 1), "
        "(SELECT id FROM identity_institutions ORDER BY id LIMIT 1) "
        ") "
        "WHERE NOT EXISTS ("
        "SELECT 1 FROM identity_groups WHERE name = 'DIRECTION'"
        ") "
        "AND EXISTS (SELECT 1 FROM identity_institutions) "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM identity_groups "
        f"WHERE id = '{DIRECTION_GROUP_ID}' "
        "AND name = 'DIRECTION' "
        "AND NOT EXISTS ("
        "SELECT 1 FROM identity_permissions "
        f"WHERE group_id = '{DIRECTION_GROUP_ID}'"
        ")"
    )
