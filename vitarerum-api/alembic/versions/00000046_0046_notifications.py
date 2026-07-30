"""Notifications

Revision ID: 0046_notifications
Revises: 0045_ext_pub_accesses
Create Date: 2026-07-30
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0046_notifications"
down_revision: str | None = "0045_ext_pub_accesses"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    notification_kind = postgresql.ENUM(
        "PROPOSAL_ASSIGNED",
        "PROPOSAL_FORWARDED",
        name="notification_kind",
        create_type=False,
    )
    related_resource_type = postgresql.ENUM(
        "PROPOSAL",
        "PROJECT",
        name="notification_related_resource_type",
        create_type=False,
    )
    notification_kind.create(bind, checkfirst=True)
    related_resource_type.create(bind, checkfirst=True)

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("recipient_permission_id", sa.String(length=36), nullable=False),
        sa.Column("kind", notification_kind, nullable=False),
        sa.Column("related_resource_type", related_resource_type, nullable=True),
        sa.Column("related_resource_id", sa.String(length=36), nullable=True),
        sa.Column("related_resource_label", sa.String(length=128), nullable=True),
        sa.Column("triggered_by", sa.String(length=36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notifications_recipient_permission_id",
        "notifications",
        ["recipient_permission_id"],
    )
    op.create_index(
        "ix_notifications_related_resource_id",
        "notifications",
        ["related_resource_id"],
    )
    op.create_index("ix_notifications_triggered_by", "notifications", ["triggered_by"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_triggered_by", table_name="notifications")
    op.drop_index("ix_notifications_related_resource_id", table_name="notifications")
    op.drop_index(
        "ix_notifications_recipient_permission_id", table_name="notifications"
    )
    op.drop_table("notifications")
    bind = op.get_bind()
    postgresql.ENUM(name="notification_related_resource_type").drop(
        bind, checkfirst=True
    )
    postgresql.ENUM(name="notification_kind").drop(bind, checkfirst=True)
