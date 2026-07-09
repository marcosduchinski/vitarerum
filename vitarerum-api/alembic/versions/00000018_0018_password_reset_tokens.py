"""Create identity_password_reset_tokens

Backs the self-service "forgot password" flow: a single-use, expiring token
whose raw value only ever lives in the e-mailed link (docs/plans/plano-gestao-passwords.md).

Revision ID: 0018_password_reset_tokens
Revises: 0017_password_changed_at
Create Date: 2026-07-09
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0018_password_reset_tokens"
down_revision: str | None = "0017_password_changed_at"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "identity_password_reset_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["identity_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_identity_password_reset_tokens_token_hash",
        "identity_password_reset_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_identity_password_reset_tokens_user_id",
        "identity_password_reset_tokens",
        ["user_id"],
    )
    op.create_index(
        "ix_identity_password_reset_tokens_expires_at",
        "identity_password_reset_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_identity_password_reset_tokens_expires_at",
        table_name="identity_password_reset_tokens",
    )
    op.drop_index(
        "ix_identity_password_reset_tokens_user_id",
        table_name="identity_password_reset_tokens",
    )
    op.drop_index(
        "ix_identity_password_reset_tokens_token_hash",
        table_name="identity_password_reset_tokens",
    )
    op.drop_table("identity_password_reset_tokens")
