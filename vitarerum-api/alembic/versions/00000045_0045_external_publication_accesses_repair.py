"""Repair external publication access audit table

Revision ID: 0045_ext_pub_accesses
Revises: 0044_ext_pub_client_id
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0045_ext_pub_accesses"
down_revision: str | None = "0044_ext_pub_client_id"
branch_labels: str | None = None
depends_on: str | None = None


ACCESS_TABLE = "external_publication_accesses"


def upgrade() -> None:
    bind = op.get_bind()
    access_mode = postgresql.ENUM(
        "TOKEN",
        "INTEGRATION_CLIENT",
        name="external_publication_access_mode",
        create_type=False,
    )
    access_outcome = postgresql.ENUM(
        "GRANTED",
        "DENIED",
        name="external_publication_access_outcome",
        create_type=False,
    )

    postgresql.ENUM(
        "TOKEN",
        "INTEGRATION_CLIENT",
        name="external_publication_access_mode",
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "GRANTED",
        "DENIED",
        name="external_publication_access_outcome",
    ).create(bind, checkfirst=True)

    inspector = sa.inspect(bind)
    if not inspector.has_table(ACCESS_TABLE):
        op.create_table(
            ACCESS_TABLE,
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("publication_id", sa.String(length=36), nullable=True),
            sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("access_mode", access_mode, nullable=False),
            sa.Column("integration_client_id", sa.String(length=128), nullable=True),
            sa.Column("remote_addr_hash", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("outcome", access_outcome, nullable=False),
        )
        existing_indexes: set[str | None] = set()
    else:
        existing_columns = {
            column["name"] for column in inspector.get_columns(ACCESS_TABLE)
        }
        if "publication_id" not in existing_columns:
            op.add_column(
                ACCESS_TABLE,
                sa.Column("publication_id", sa.String(length=36), nullable=True),
            )
        if "accessed_at" not in existing_columns:
            op.add_column(
                ACCESS_TABLE,
                sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False),
            )
        if "access_mode" not in existing_columns:
            op.add_column(
                ACCESS_TABLE,
                sa.Column("access_mode", access_mode, nullable=False),
            )
        if "integration_client_id" not in existing_columns:
            op.add_column(
                ACCESS_TABLE,
                sa.Column(
                    "integration_client_id",
                    sa.String(length=128),
                    nullable=True,
                ),
            )
        if "remote_addr_hash" not in existing_columns:
            op.add_column(
                ACCESS_TABLE,
                sa.Column("remote_addr_hash", sa.String(length=64), nullable=True),
            )
        if "user_agent" not in existing_columns:
            op.add_column(
                ACCESS_TABLE,
                sa.Column("user_agent", sa.Text(), nullable=True),
            )
        if "outcome" not in existing_columns:
            op.add_column(
                ACCESS_TABLE,
                sa.Column("outcome", access_outcome, nullable=False),
            )
        existing_indexes = {
            index["name"] for index in inspector.get_indexes(ACCESS_TABLE)
        }

    if "ix_external_publication_accesses_publication_id" not in existing_indexes:
        op.create_index(
            "ix_external_publication_accesses_publication_id",
            ACCESS_TABLE,
            ["publication_id"],
        )
    if "ix_external_publication_accesses_accessed_at" not in existing_indexes:
        op.create_index(
            "ix_external_publication_accesses_accessed_at",
            ACCESS_TABLE,
            ["accessed_at"],
        )
    if "ix_external_publication_accesses_integration_client_id" not in existing_indexes:
        op.create_index(
            "ix_external_publication_accesses_integration_client_id",
            ACCESS_TABLE,
            ["integration_client_id"],
        )
    if "ix_external_publication_accesses_outcome" not in existing_indexes:
        op.create_index(
            "ix_external_publication_accesses_outcome",
            ACCESS_TABLE,
            ["outcome"],
        )


def downgrade() -> None:
    # Compatibility repair only. The canonical 0043 migration owns this table
    # for fresh databases, so downgrading 0045 must not remove it there.
    pass
