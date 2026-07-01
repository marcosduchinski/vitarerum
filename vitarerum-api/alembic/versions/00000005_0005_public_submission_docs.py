"""Add documents to public proposal submissions

Revision ID: 0005_public_submission_docs
Revises: 0004_public_dates_required
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_public_submission_docs"
down_revision: str | None = "0004_public_dates_required"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "public_proposal_submission_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_reference", sa.String(length=512), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["public_proposal_submissions.id"]),
    )
    op.create_index(
        "ix_public_proposal_submission_documents_submission_id",
        "public_proposal_submission_documents",
        ["submission_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_public_proposal_submission_documents_submission_id",
        table_name="public_proposal_submission_documents",
    )
    op.drop_table("public_proposal_submission_documents")
