"""Drop the redundant unique constraint on the agentic candidate link.

Revision ID: 0069_drop_agentic_link_unique
Revises: 0068_full_agentic_prompts
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0069_drop_agentic_link_unique"
down_revision: str | None = "0068_full_agentic_prompts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_sr_agentic_candidate_link",
        "sr_agentic_investigation_candidates",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_sr_agentic_candidate_link",
        "sr_agentic_investigation_candidates",
        ("investigation_id", "candidate_id"),
    )
