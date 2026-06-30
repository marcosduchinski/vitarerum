"""Add Identity institutions and Group.institution_id

Introduces the Institution aggregate (Identity & Access) and wires every Group
to an owning institution. A single default institution is seeded and all
existing groups are backfilled to it before the FK is made NOT NULL, so the
change is safe on a populated database.

Revision ID: 0001_add_institutions
Revises: 0000_consolidated_baseline
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_add_institutions"
down_revision: str | None = "0000_consolidated_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fixed id for the seeded default institution, shared with scripts/seed.sql.
DEFAULT_INSTITUTION_ID = "a0000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(
        "CREATE TABLE identity_institutions ( "
        "id VARCHAR(36) NOT NULL, "
        "name VARCHAR(255) NOT NULL, "
        "email VARCHAR(255) NOT NULL, "
        "address VARCHAR(512) NOT NULL, "
        "phone VARCHAR(64) NOT NULL, "
        "PRIMARY KEY (id), UNIQUE (name) )"
    )
    op.execute(
        "INSERT INTO identity_institutions (id, name, email, address, phone) "
        f"VALUES ('{DEFAULT_INSTITUTION_ID}', 'MUHNAC', '', '', '')"
    )

    # Add nullable, backfill to the default institution, then constrain.
    op.execute("ALTER TABLE identity_groups ADD COLUMN institution_id VARCHAR(36)")
    op.execute(
        "UPDATE identity_groups SET institution_id = "
        f"'{DEFAULT_INSTITUTION_ID}' WHERE institution_id IS NULL"
    )
    op.execute(
        "ALTER TABLE identity_groups ALTER COLUMN institution_id SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE identity_groups ADD CONSTRAINT "
        "fk_identity_groups_institution_id "
        "FOREIGN KEY (institution_id) REFERENCES identity_institutions (id)"
    )
    op.execute(
        "CREATE INDEX ix_identity_groups_institution_id "
        "ON identity_groups (institution_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_identity_groups_institution_id")
    op.execute(
        "ALTER TABLE identity_groups DROP CONSTRAINT "
        "fk_identity_groups_institution_id"
    )
    op.execute("ALTER TABLE identity_groups DROP COLUMN institution_id")
    op.execute("DROP TABLE identity_institutions")
