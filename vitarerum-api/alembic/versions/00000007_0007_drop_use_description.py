"""Drop intended_use_description columns

The IntendedUse value object was collapsed to a bare UseType; its free-text
description is no longer part of the domain, so its backing columns are removed
from both proposals and collection_use_projects.

Revision ID: 0007_drop_use_description
Revises: 0006_public_requester_contact
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0007_drop_use_description"
down_revision: str | None = "0006_public_requester_contact"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_column("proposals", "intended_use_description")
    op.drop_column("collection_use_projects", "intended_use_description")


def downgrade() -> None:
    op.add_column(
        "collection_use_projects",
        sa.Column(
            "intended_use_description",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "proposals",
        sa.Column(
            "intended_use_description",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
