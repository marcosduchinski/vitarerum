"""Introduce CollectionArea and Collection.area_id

Adds a catalogue-classification level above `Collection` (docs/plans/
plano-collection-areas.md): a `CollectionArea` groups several scientific
collections (e.g. "Zoology" groups reptiles, amphibians, and fish). Permissions
and ingestion stay unchanged at the `Collection` level.

Sequence for a populated database: create + seed the area table first, add
`area_id` as nullable, backfill the existing collections into their
initial area, then tighten to NOT NULL + FK + index.

Revision ID: 0014_collection_areas
Revises: 0013_museum_questions
Create Date: 2026-07-06
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0014_collection_areas"
down_revision: str | None = "0013_museum_questions"
branch_labels: str | None = None
depends_on: str | None = None

AREA_NAMES = [
    "Zoology",
]

# Initial grouping of the collections seeded by 0011_collection_object_index
# into the area above.
COLLECTION_TO_AREA = {
    "REPTILES & AMPHIBIANS": "Zoology",
    "FISH": "Zoology",
}


def _area_id(name: str) -> str:
    """Deterministic id so every environment seeds the same areas."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vitarerum:collection_area:{name}"))


def upgrade() -> None:
    op.create_table(
        "collection_index_collection_area",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    areas = sa.table(
        "collection_index_collection_area",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    seeded_at = datetime.now(UTC)
    op.bulk_insert(
        areas,
        [
            {
                "id": _area_id(name),
                "name": name,
                "created_at": seeded_at,
                "updated_at": seeded_at,
            }
            for name in AREA_NAMES
        ],
    )

    # 1. Add area_id as nullable so existing rows aren't rejected outright.
    op.add_column(
        "collection_index_collection",
        sa.Column("area_id", sa.String(length=36), nullable=True),
    )

    # 2. Backfill the pre-existing collections into their initial area.
    # Matched by name (unique, stable) rather than the deterministic seed id:
    # a collection may have been removed and recreated by the admin API since
    # 0011 seeded it, which mints a fresh random id but keeps the same name.
    collection_table = sa.table(
        "collection_index_collection",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("area_id", sa.String),
    )
    connection = op.get_bind()
    for collection_name, area_name in COLLECTION_TO_AREA.items():
        connection.execute(
            collection_table.update()
            .where(collection_table.c.name == collection_name)
            .values(area_id=_area_id(area_name))
        )

    # Safety net: any collection outside the initial 14 (renamed, or created
    # between 0011 and this migration) falls back to the first area rather
    # than failing the NOT NULL tightening below.
    connection.execute(
        collection_table.update()
        .where(collection_table.c.area_id.is_(None))
        .values(area_id=_area_id(AREA_NAMES[0]))
    )

    # 3. Tighten to NOT NULL now that every row has an area.
    op.alter_column("collection_index_collection", "area_id", nullable=False)

    # 4. FK + index.
    op.create_foreign_key(
        "fk_collection_index_collection_area_id",
        "collection_index_collection",
        "collection_index_collection_area",
        ["area_id"],
        ["id"],
    )
    op.create_index(
        "ix_collection_index_collection_area_id",
        "collection_index_collection",
        ["area_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collection_index_collection_area_id",
        table_name="collection_index_collection",
    )
    op.drop_constraint(
        "fk_collection_index_collection_area_id",
        "collection_index_collection",
        type_="foreignkey",
    )
    op.drop_column("collection_index_collection", "area_id")
    op.drop_table("collection_index_collection_area")
