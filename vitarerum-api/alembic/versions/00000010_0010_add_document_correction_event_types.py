"""Add proposal event types for document corrections

Revision ID: 0010_doc_correction_events
Revises: 0009_document_corrections
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_doc_correction_events"
down_revision: str | None = "0009_document_corrections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD_PROPOSAL_EVENT_TYPES = (
    "SUBMITTED",
    "ASSIGNED",
    "FORWARDED",
    "DOCUMENTS_REQUESTED",
    "DOCUMENTS_SUBMITTED",
    "REVIEW_STARTED",
    "REFERRED_TO_DIRECTION",
    "DIRECTION_CLARIFIED",
    "APPROVED",
    "REJECTED",
    "CANCELLED",
)


def upgrade() -> None:
    op.execute(
        "ALTER TYPE proposal_event_type "
        "ADD VALUE IF NOT EXISTS 'DOCUMENT_CORRECTIONS_REQUESTED'"
    )
    op.execute(
        "ALTER TYPE proposal_event_type "
        "ADD VALUE IF NOT EXISTS 'DOCUMENT_CORRECTIONS_SUBMITTED'"
    )


def downgrade() -> None:
    old_values_sql = ", ".join(f"'{value}'" for value in OLD_PROPOSAL_EVENT_TYPES)
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM proposal_events
                WHERE type::text IN (
                    'DOCUMENT_CORRECTIONS_REQUESTED',
                    'DOCUMENT_CORRECTIONS_SUBMITTED'
                )
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade proposal_event_type: %',
                    'document correction events exist';
            END IF;
        END
        $$;
        """
    )
    op.execute("ALTER TYPE proposal_event_type RENAME TO proposal_event_type_old")
    op.execute(
        "CREATE TYPE proposal_event_type AS ENUM "
        f"({old_values_sql})"
    )
    op.execute(
        "ALTER TABLE proposal_events "
        "ALTER COLUMN type TYPE proposal_event_type "
        "USING type::text::proposal_event_type"
    )
    op.execute("DROP TYPE proposal_event_type_old")
