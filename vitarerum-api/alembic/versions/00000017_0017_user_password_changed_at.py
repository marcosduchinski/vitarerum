"""Add identity_users.password_changed_at

Backs session invalidation: access tokens issued before this instant are
rejected by get_caller_permission once a user changes or resets their
password (docs/plans/plano-gestao-passwords.md).

Revision ID: 0017_password_changed_at
Revises: 0016_zoology_catalogue
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0017_password_changed_at"
down_revision: str | None = "0016_zoology_catalogue"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "identity_users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("identity_users", "password_changed_at")
