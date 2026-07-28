"""Add project follow-up origin link

Revision ID: 0042_project_follow_ups
Revises: 0041_reference_number_policies
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0042_project_follow_ups"
down_revision: str | None = "0041_reference_number_policies"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "collection_use_projects",
        sa.Column("origin_project_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_collection_use_projects_origin_project_id",
        "collection_use_projects",
        ["origin_project_id"],
    )
    op.create_foreign_key(
        "fk_collection_use_projects_origin_project_id",
        "collection_use_projects",
        "collection_use_projects",
        ["origin_project_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_collection_use_projects_origin_project_id",
        "collection_use_projects",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_collection_use_projects_origin_project_id",
        table_name="collection_use_projects",
    )
    op.drop_column("collection_use_projects", "origin_project_id")
