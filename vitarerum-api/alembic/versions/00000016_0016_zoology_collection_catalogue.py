"""Replace initial collection catalogue with Zoology collections

Revision ID: 0016_zoology_catalogue
Revises: 0015_museum_question_triages
Create Date: 2026-07-09
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0016_zoology_catalogue"
down_revision: str | None = "0015_museum_question_triages"
branch_labels: str | None = None
depends_on: str | None = None

ZOOLOGY_AREA_NAME = "Zoology"
COLLECTION_NAMES = [
    "REPTILES & AMPHIBIANS",
    "FISH",
]

OLD_SEEDED_COLLECTION_NAMES = [
    "Biological Anthropology",
    "Archaeology",
    "Animal Sound Archive",
    "Historical Archives & Libraries",
    "Biological Banks",
    "Botany",
    "Ethnography",
    "Photography, Film & Audio",
    "History of Science and Medicine",
    "Institutional History & Art",
    "Mineralogy & Petrology",
    "Natural Objects",
    "Paleontology",
    "Zoology",
]
OLD_SEEDED_AREA_NAMES = [
    "Natural History",
    "Human Sciences",
    "Documentation & Media",
]


def _collection_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vitarerum:collection:{name}"))


def _area_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vitarerum:collection_area:{name}"))


def upgrade() -> None:
    connection = op.get_bind()
    seeded_at = datetime.now(UTC)
    zoology_area_id = _area_id(ZOOLOGY_AREA_NAME)

    zoology_area_id = connection.execute(
        sa.text(
            """
            INSERT INTO collection_index_collection_area
                (id, name, created_at, updated_at)
            VALUES (:id, :name, :created_at, :updated_at)
            ON CONFLICT (name) DO UPDATE
            SET updated_at = EXCLUDED.updated_at
            RETURNING id
            """
        ),
        {
            "id": zoology_area_id,
            "name": ZOOLOGY_AREA_NAME,
            "created_at": seeded_at,
            "updated_at": seeded_at,
        },
    ).scalar_one()

    old_collection_ids = list(
        connection.execute(
            sa.text(
                """
                SELECT id
                FROM collection_index_collection
                WHERE name IN :names
                """
            ).bindparams(sa.bindparam("names", expanding=True)),
            {"names": OLD_SEEDED_COLLECTION_NAMES},
        ).scalars()
    )
    if old_collection_ids:
        connection.execute(
            sa.text(
                """
                DELETE FROM collection_index_object
                WHERE collection_id IN :collection_ids
                """
            ).bindparams(sa.bindparam("collection_ids", expanding=True)),
            {"collection_ids": old_collection_ids},
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM collection_index_source_document
                WHERE collection_id IN :collection_ids
                """
            ).bindparams(sa.bindparam("collection_ids", expanding=True)),
            {"collection_ids": old_collection_ids},
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM collection_index_curator
                WHERE collection_id IN :collection_ids
                """
            ).bindparams(sa.bindparam("collection_ids", expanding=True)),
            {"collection_ids": old_collection_ids},
        )
        connection.execute(
            sa.text(
                """
                DELETE FROM collection_index_collection
                WHERE id IN :collection_ids
                """
            ).bindparams(sa.bindparam("collection_ids", expanding=True)),
            {"collection_ids": old_collection_ids},
        )

    for collection_name in COLLECTION_NAMES:
        connection.execute(
            sa.text(
                """
                INSERT INTO collection_index_collection
                    (id, area_id, name, created_at, updated_at)
                VALUES (:id, :area_id, :name, :created_at, :updated_at)
                ON CONFLICT (name) DO UPDATE
                SET area_id = EXCLUDED.area_id,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "id": _collection_id(collection_name),
                "area_id": zoology_area_id,
                "name": collection_name,
                "created_at": seeded_at,
                "updated_at": seeded_at,
            },
        )

    connection.execute(
        sa.text(
            """
            DELETE FROM collection_index_collection_area
            WHERE name IN :names
              AND id NOT IN (
                  SELECT DISTINCT area_id FROM collection_index_collection
              )
            """
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": OLD_SEEDED_AREA_NAMES},
    )


def downgrade() -> None:
    connection = op.get_bind()
    seeded_at = datetime.now(UTC)
    zoology_area_id = _area_id(ZOOLOGY_AREA_NAME)

    connection.execute(
        sa.text(
            """
            DELETE FROM collection_index_collection
            WHERE name IN :names
            """
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": COLLECTION_NAMES},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM collection_index_collection_area
            WHERE id = :id
              AND id NOT IN (
                  SELECT DISTINCT area_id FROM collection_index_collection
              )
            """
        ),
        {"id": zoology_area_id},
    )

    for area_name in OLD_SEEDED_AREA_NAMES:
        connection.execute(
            sa.text(
                """
                INSERT INTO collection_index_collection_area
                    (id, name, created_at, updated_at)
                VALUES (:id, :name, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": _area_id(area_name),
                "name": area_name,
                "created_at": seeded_at,
                "updated_at": seeded_at,
            },
        )

    old_collection_to_area = {
        "Biological Banks": "Natural History",
        "Botany": "Natural History",
        "Mineralogy & Petrology": "Natural History",
        "Natural Objects": "Natural History",
        "Paleontology": "Natural History",
        "Zoology": "Natural History",
        "Biological Anthropology": "Human Sciences",
        "Archaeology": "Human Sciences",
        "Ethnography": "Human Sciences",
        "History of Science and Medicine": "Human Sciences",
        "Institutional History & Art": "Human Sciences",
        "Animal Sound Archive": "Documentation & Media",
        "Historical Archives & Libraries": "Documentation & Media",
        "Photography, Film & Audio": "Documentation & Media",
    }
    for collection_name, area_name in old_collection_to_area.items():
        connection.execute(
            sa.text(
                """
                INSERT INTO collection_index_collection
                    (id, area_id, name, created_at, updated_at)
                VALUES (:id, :area_id, :name, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": _collection_id(collection_name),
                "area_id": _area_id(area_name),
                "name": collection_name,
                "created_at": seeded_at,
                "updated_at": seeded_at,
            },
        )
