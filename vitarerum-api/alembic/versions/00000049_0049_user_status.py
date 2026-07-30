"""Add identity user status

Revision ID: 0049_user_status
Revises: 0048_ensure_direction_group
Create Date: 2026-07-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0049_user_status"
down_revision: str | None = "0048_ensure_direction_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE identity_user_status AS ENUM ('ACTIVE', 'DISABLED')")
    op.execute(
        "ALTER TABLE identity_users "
        "ADD COLUMN status identity_user_status NOT NULL DEFAULT 'ACTIVE'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE identity_users DROP COLUMN status")
    op.execute("DROP TYPE identity_user_status")
