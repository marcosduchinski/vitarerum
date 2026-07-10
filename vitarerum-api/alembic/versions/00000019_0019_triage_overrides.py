"""Add staff-override columns to museum_question_triages

Backs the triage refinements plan (docs/plans/museum-questions-ai-triage-
refinements-plan.md): staff can contest the AI's scope verdict. The override
is recorded alongside the AI's original verdict, never replacing it.

Revision ID: 0019_triage_overrides
Revises: 0018_password_reset_tokens
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0019_triage_overrides"
down_revision: str | None = "0018_password_reset_tokens"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "museum_question_triages",
        sa.Column("staff_override_verdict", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "museum_question_triages",
        sa.Column("staff_override_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "museum_question_triages",
        sa.Column("staff_override_by", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("museum_question_triages", "staff_override_by")
    op.drop_column("museum_question_triages", "staff_override_at")
    op.drop_column("museum_question_triages", "staff_override_verdict")
