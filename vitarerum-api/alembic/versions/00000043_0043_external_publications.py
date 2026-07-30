"""Add external publications

Revision ID: 0043_external_publications
Revises: 0042_project_follow_ups
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0043_external_publications"
down_revision: str | None = "0042_project_follow_ups"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    resource_type = sa.Enum(
        "PROPOSAL",
        "PROJECT",
        "IN_SITU_VISIT_REPORT",
        name="external_publication_resource_type",
    )
    status = sa.Enum(
        "PUBLISHED",
        "REVOKED",
        name="external_publication_status",
    )
    access_mode = sa.Enum(
        "TOKEN",
        "INTEGRATION_CLIENT",
        name="external_publication_access_mode",
    )
    profile = sa.Enum(
        "SUMMARY",
        "DETAIL",
        "JSON_LD",
        name="external_publication_profile",
    )
    access_outcome = sa.Enum(
        "GRANTED",
        "DENIED",
        name="external_publication_access_outcome",
    )

    resource_type.create(op.get_bind(), checkfirst=True)
    status.create(op.get_bind(), checkfirst=True)
    access_mode.create(op.get_bind(), checkfirst=True)
    profile.create(op.get_bind(), checkfirst=True)
    access_outcome.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "external_publications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("resource_type", resource_type, nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("access_mode", access_mode, nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("integration_client_id", sa.String(length=128), nullable=True),
        sa.Column("profile", profile, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_external_publications_resource_type", "external_publications", ["resource_type"])
    op.create_index("ix_external_publications_resource_id", "external_publications", ["resource_id"])
    op.create_index("ix_external_publications_status", "external_publications", ["status"])
    op.create_index("ix_external_publications_token_hash", "external_publications", ["token_hash"], unique=True)
    op.create_index("ix_external_publications_profile", "external_publications", ["profile"])
    op.create_index("ix_external_publications_expires_at", "external_publications", ["expires_at"])
    op.create_index("ix_external_publications_created_by", "external_publications", ["created_by"])
    op.create_index("ix_external_publications_created_at", "external_publications", ["created_at"])
    op.create_index("ix_external_publications_published_at", "external_publications", ["published_at"])
    op.create_index("ix_external_publications_revoked_by", "external_publications", ["revoked_by"])
    op.create_index("ix_external_publications_revoked_at", "external_publications", ["revoked_at"])

    op.create_table(
        "external_publication_accesses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("publication_id", sa.String(length=36), nullable=True),
        sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("access_mode", access_mode, nullable=False),
        sa.Column("integration_client_id", sa.String(length=128), nullable=True),
        sa.Column("remote_addr_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("outcome", access_outcome, nullable=False),
    )
    op.create_index("ix_external_publication_accesses_publication_id", "external_publication_accesses", ["publication_id"])
    op.create_index("ix_external_publication_accesses_accessed_at", "external_publication_accesses", ["accessed_at"])
    op.create_index("ix_external_publication_accesses_integration_client_id", "external_publication_accesses", ["integration_client_id"])
    op.create_index("ix_external_publication_accesses_outcome", "external_publication_accesses", ["outcome"])


def downgrade() -> None:
    op.drop_index("ix_external_publication_accesses_outcome", table_name="external_publication_accesses")
    op.drop_index("ix_external_publication_accesses_integration_client_id", table_name="external_publication_accesses")
    op.drop_index("ix_external_publication_accesses_accessed_at", table_name="external_publication_accesses")
    op.drop_index("ix_external_publication_accesses_publication_id", table_name="external_publication_accesses")
    op.drop_table("external_publication_accesses")

    op.drop_index("ix_external_publications_revoked_at", table_name="external_publications")
    op.drop_index("ix_external_publications_revoked_by", table_name="external_publications")
    op.drop_index("ix_external_publications_published_at", table_name="external_publications")
    op.drop_index("ix_external_publications_created_at", table_name="external_publications")
    op.drop_index("ix_external_publications_created_by", table_name="external_publications")
    op.drop_index("ix_external_publications_expires_at", table_name="external_publications")
    op.drop_index("ix_external_publications_profile", table_name="external_publications")
    op.drop_index("ix_external_publications_token_hash", table_name="external_publications")
    op.drop_index("ix_external_publications_status", table_name="external_publications")
    op.drop_index("ix_external_publications_resource_id", table_name="external_publications")
    op.drop_index("ix_external_publications_resource_type", table_name="external_publications")
    op.drop_table("external_publications")

    sa.Enum(name="external_publication_access_outcome").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="external_publication_profile").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="external_publication_access_mode").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="external_publication_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="external_publication_resource_type").drop(op.get_bind(), checkfirst=True)
