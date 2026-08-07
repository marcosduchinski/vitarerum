"""Prepare phase 1 encrypted database fields

Revision ID: 0054_database_field_encryption_phase1
Revises: 0053_object_collection_snapshots
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0054_database_field_encryption_phase1"
down_revision: str | None = "0053_object_collection_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(
        "ix_public_proposal_submissions_citizen_email",
        table_name="public_proposal_submissions",
    )
    op.alter_column(
        "public_proposal_submissions",
        "citizen_name",
        type_=sa.Text(),
        existing_type=sa.String(length=120),
        existing_nullable=False,
    )
    op.alter_column(
        "public_proposal_submissions",
        "citizen_email",
        type_=sa.Text(),
        existing_type=sa.String(length=180),
        existing_nullable=False,
    )
    op.alter_column(
        "public_proposal_submissions",
        "subject",
        type_=sa.Text(),
        existing_type=sa.String(length=160),
        existing_nullable=False,
    )
    op.alter_column(
        "public_proposal_submission_documents",
        "file_name",
        type_=sa.Text(),
        existing_type=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "proposal_amendment_tokens",
        "requester_email",
        type_=sa.Text(),
        existing_type=sa.String(length=180),
        existing_nullable=False,
    )

    op.alter_column(
        "museum_questions",
        "requester_name",
        type_=sa.Text(),
        existing_type=sa.String(length=120),
        existing_nullable=False,
    )
    op.alter_column(
        "museum_questions",
        "requester_email",
        type_=sa.Text(),
        existing_type=sa.String(length=180),
        existing_nullable=False,
    )
    op.alter_column(
        "museum_questions",
        "subject",
        type_=sa.Text(),
        existing_type=sa.String(length=200),
        existing_nullable=False,
    )
    op.add_column(
        "museum_questions",
        sa.Column("requester_email_hash", sa.String(length=64), nullable=False),
    )
    op.create_index(
        op.f("ix_museum_questions_requester_email_hash"),
        "museum_questions",
        ["requester_email_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_museum_questions_requester_email_hash"),
        table_name="museum_questions",
    )
    op.drop_column("museum_questions", "requester_email_hash")
    op.alter_column(
        "museum_questions",
        "subject",
        type_=sa.String(length=200),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "museum_questions",
        "requester_email",
        type_=sa.String(length=180),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "museum_questions",
        "requester_name",
        type_=sa.String(length=120),
        existing_type=sa.Text(),
        existing_nullable=False,
    )

    op.alter_column(
        "proposal_amendment_tokens",
        "requester_email",
        type_=sa.String(length=180),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "public_proposal_submission_documents",
        "file_name",
        type_=sa.String(length=255),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "public_proposal_submissions",
        "subject",
        type_=sa.String(length=160),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "public_proposal_submissions",
        "citizen_email",
        type_=sa.String(length=180),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.alter_column(
        "public_proposal_submissions",
        "citizen_name",
        type_=sa.String(length=120),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
    op.create_index(
        "ix_public_proposal_submissions_citizen_email",
        "public_proposal_submissions",
        ["citizen_email"],
        unique=False,
    )
