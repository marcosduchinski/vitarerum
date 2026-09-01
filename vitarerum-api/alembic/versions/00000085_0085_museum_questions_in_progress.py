"""Mark assigned museum questions as in progress.

Revision ID: 0085_mq_in_progress
Revises: 0084_sr_knowledge_base
Create Date: 2026-09-01
"""

from __future__ import annotations

from alembic import op

revision: str = "0085_mq_in_progress"
down_revision: str | None = "0084_sr_knowledge_base"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE museum_questions
        SET status = 'IN_PROGRESS'
        WHERE status = 'SUBMITTED'
          AND assigned_to IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE museum_questions
        SET status = 'SUBMITTED'
        WHERE status = 'IN_PROGRESS'
        """
    )
