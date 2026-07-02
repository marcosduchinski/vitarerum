"""Store requester contact for public proposals

Revision ID: 0006_public_requester_contact
Revises: 0005_public_submission_docs
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0006_public_requester_contact"
down_revision: str | None = "0005_public_submission_docs"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "proposals",
        sa.Column("requester_name", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "proposals",
        sa.Column("requester_email", sa.String(length=180), nullable=True),
    )
    op.execute(
        "ALTER TABLE proposals "
        "ALTER COLUMN collection_use_project_id DROP NOT NULL"
    )
    op.execute("ALTER TABLE proposals ALTER COLUMN requested_by DROP NOT NULL")
    op.execute("ALTER TABLE proposal_events ALTER COLUMN triggered_by DROP NOT NULL")
    op.execute("ALTER TABLE documents ALTER COLUMN submitted_by DROP NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE documents ALTER COLUMN submitted_by SET NOT NULL")
    op.execute("ALTER TABLE proposal_events ALTER COLUMN triggered_by SET NOT NULL")
    op.execute("ALTER TABLE proposals ALTER COLUMN requested_by SET NOT NULL")
    op.execute(
        "ALTER TABLE proposals "
        "ALTER COLUMN collection_use_project_id SET NOT NULL"
    )
    op.drop_column("proposals", "requester_email")
    op.drop_column("proposals", "requester_name")
