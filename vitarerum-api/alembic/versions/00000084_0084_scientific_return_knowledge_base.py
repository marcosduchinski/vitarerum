"""Scope scientific-return knowledge and investigations by institution

Revision ID: 0084_sr_knowledge_base
Revises: 0083_direction_notifications
Create Date: 2026-08-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0084_sr_knowledge_base"
down_revision: str | None = "0083_direction_notifications"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "scientific_return_watches",
        sa.Column("institution_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_scientific_return_watches_institution_id",
        "scientific_return_watches",
        ["institution_id"],
    )
    op.add_column(
        "sr_full_agentic_investigations",
        sa.Column("institution_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_sr_full_agentic_investigations_institution_id",
        "sr_full_agentic_investigations",
        ["institution_id"],
    )
    op.create_index(
        "ix_sr_knowledge_items_institution_id",
        "sr_knowledge_items",
        ["institution_id"],
    )
    op.create_index(
        "ix_sr_knowledge_institution_status_created",
        "sr_knowledge_items",
        ["institution_id", "status", "kind", "created_at", "id"],
    )

    op.execute(
        """
        UPDATE sr_knowledge_items AS knowledge
        SET institution_id = groups.institution_id
        FROM identity_permissions AS permissions
        JOIN identity_groups AS groups ON groups.id = permissions.group_id
        WHERE knowledge.created_by = permissions.id
          AND knowledge.institution_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE scientific_return_watches AS watches
        SET institution_id = groups.institution_id
        FROM identity_permissions AS permissions
        JOIN identity_groups AS groups ON groups.id = permissions.group_id
        WHERE watches.created_by = permissions.id
          AND watches.institution_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE sr_full_agentic_investigations AS investigations
        SET institution_id = watches.institution_id
        FROM scientific_return_watches AS watches
        WHERE investigations.watch_id = watches.id
          AND investigations.institution_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sr_knowledge_institution_status_created",
        table_name="sr_knowledge_items",
    )
    op.drop_index(
        "ix_sr_knowledge_items_institution_id", table_name="sr_knowledge_items"
    )
    op.drop_index(
        "ix_sr_full_agentic_investigations_institution_id",
        table_name="sr_full_agentic_investigations",
    )
    op.drop_column("sr_full_agentic_investigations", "institution_id")
    op.drop_index(
        "ix_scientific_return_watches_institution_id",
        table_name="scientific_return_watches",
    )
    op.drop_column("scientific_return_watches", "institution_id")
