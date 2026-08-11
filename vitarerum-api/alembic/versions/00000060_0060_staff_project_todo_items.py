"""Add staff profile scoped project TODO items

Revision ID: 0060_staff_project_todo_items
Revises: 0059_in_situ_visit_institution
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0060_staff_project_todo_items"
down_revision: str | None = "0059_in_situ_visit_institution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "staff_project_todo_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("owner_permission_id", sa.String(length=36), nullable=False),
        sa.Column("text", sa.String(length=160), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("length(trim(text)) > 0", name="ck_staff_project_todo_text"),
        sa.CheckConstraint("position >= 0", name="ck_staff_project_todo_position"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["collection_use_projects.id"],
            name="fk_staff_project_todo_project_id",
        ),
        sa.ForeignKeyConstraint(
            ["owner_permission_id"],
            ["identity_permissions.id"],
            name="fk_staff_project_todo_owner_permission_id",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_staff_project_todo_project_owner_position_created",
        "staff_project_todo_items",
        ["project_id", "owner_permission_id", "position", "created_at"],
    )
    op.create_index(
        "ix_staff_project_todo_owner_completed_updated",
        "staff_project_todo_items",
        ["owner_permission_id", "completed", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_staff_project_todo_owner_completed_updated",
        table_name="staff_project_todo_items",
    )
    op.drop_index(
        "ix_staff_project_todo_project_owner_position_created",
        table_name="staff_project_todo_items",
    )
    op.drop_table("staff_project_todo_items")
