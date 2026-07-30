"""Repair external publications integration-client column

Revision ID: 0044_ext_pub_client_id
Revises: 0043_external_publications
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0044_ext_pub_client_id"
down_revision: str | None = "0043_external_publications"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        column["name"] for column in inspector.get_columns("external_publications")
    }
    if "integration_client_id" not in columns:
        op.add_column(
            "external_publications",
            sa.Column("integration_client_id", sa.String(length=128), nullable=True),
        )

    indexes = {
        index["name"] for index in inspector.get_indexes("external_publications")
    }
    if "ix_external_publications_integration_client_id" not in indexes:
        op.create_index(
            "ix_external_publications_integration_client_id",
            "external_publications",
            ["integration_client_id"],
        )


def downgrade() -> None:
    # Compatibility repair only. The canonical 0043 migration owns this column
    # for fresh databases, so downgrading 0044 must not remove it there.
    pass
