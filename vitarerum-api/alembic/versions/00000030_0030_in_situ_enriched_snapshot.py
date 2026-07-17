"""Persist enriched in-situ visit snapshot fields

Revision ID: 0030_in_situ_enriched_snapshot
Revises: 0029_attachment_desc_required
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0030_in_situ_enriched_snapshot"
down_revision: str | None = "0029_attachment_desc_required"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "in_situ_visit_records",
        sa.Column("record_schema_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("source_project_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("project_title", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records", sa.Column("project_purpose", sa.Text(), nullable=True)
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("planned_begin_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("planned_end_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("execution_evidence_type", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("execution_occurred_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("execution_recorded_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("execution_evidence_gaps", sa.JSON(), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("approved_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records", sa.Column("approval_note", sa.Text(), nullable=True)
    )

    op.add_column(
        "requested_object_records",
        sa.Column("display_title", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "requested_object_records",
        sa.Column("object_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "requested_object_records",
        sa.Column("brief_description_snapshot", sa.Text(), nullable=True),
    )

    op.add_column(
        "in_situ_occurrence_records",
        sa.Column("number_of_objects", sa.Integer(), nullable=True),
    )
    op.add_column(
        "in_situ_occurrence_records",
        sa.Column("occurrence_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "in_situ_occurrence_records",
        sa.Column("location", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_occurrence_records",
        sa.Column("reported_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_occurrence_records",
        sa.Column("testimonial", sa.Text(), nullable=True),
    )
    op.add_column(
        "in_situ_occurrence_records",
        sa.Column(
            "occurrence_log_date_conclusion",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "in_situ_occurrence_records",
        sa.Column("occurrence_log_curator", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_occurrence_attachment_records",
        sa.Column("media_type", sa.String(length=64), nullable=True),
    )

    op.add_column(
        "in_situ_log_records",
        sa.Column("number_of_objects", sa.Integer(), nullable=True),
    )
    op.add_column(
        "in_situ_log_records",
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "in_situ_log_records",
        sa.Column("added_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_log_records",
        sa.Column(
            "access_log_date_conclusion", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "in_situ_log_records",
        sa.Column("access_log_curator", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_log_attachment_records",
        sa.Column("media_type", sa.String(length=64), nullable=True),
    )

    op.add_column(
        "in_situ_publication_records",
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "in_situ_publication_records",
        sa.Column("added_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_publication_attachment_records",
        sa.Column("media_type", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("in_situ_publication_attachment_records", "media_type")
    op.drop_column("in_situ_publication_records", "added_by")
    op.drop_column("in_situ_publication_records", "added_at")

    op.drop_column("in_situ_log_attachment_records", "media_type")
    op.drop_column("in_situ_log_records", "access_log_curator")
    op.drop_column("in_situ_log_records", "access_log_date_conclusion")
    op.drop_column("in_situ_log_records", "added_by")
    op.drop_column("in_situ_log_records", "added_at")
    op.drop_column("in_situ_log_records", "number_of_objects")

    op.drop_column("in_situ_occurrence_attachment_records", "media_type")
    op.drop_column("in_situ_occurrence_records", "occurrence_log_curator")
    op.drop_column("in_situ_occurrence_records", "occurrence_log_date_conclusion")
    op.drop_column("in_situ_occurrence_records", "testimonial")
    op.drop_column("in_situ_occurrence_records", "reported_by")
    op.drop_column("in_situ_occurrence_records", "location")
    op.drop_column("in_situ_occurrence_records", "occurrence_date")
    op.drop_column("in_situ_occurrence_records", "number_of_objects")

    op.drop_column("requested_object_records", "brief_description_snapshot")
    op.drop_column("requested_object_records", "object_name")
    op.drop_column("requested_object_records", "display_title")

    op.drop_column("in_situ_visit_records", "approval_note")
    op.drop_column("in_situ_visit_records", "approved_by")
    op.drop_column("in_situ_visit_records", "approved_at")
    op.drop_column("in_situ_visit_records", "execution_evidence_gaps")
    op.drop_column("in_situ_visit_records", "execution_recorded_by")
    op.drop_column("in_situ_visit_records", "execution_occurred_at")
    op.drop_column("in_situ_visit_records", "execution_evidence_type")
    op.drop_column("in_situ_visit_records", "planned_end_date")
    op.drop_column("in_situ_visit_records", "planned_begin_date")
    op.drop_column("in_situ_visit_records", "project_purpose")
    op.drop_column("in_situ_visit_records", "project_title")
    op.drop_column("in_situ_visit_records", "source_project_id")
    op.drop_column("in_situ_visit_records", "record_schema_version")
