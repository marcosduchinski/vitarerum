"""Create the Collection Object Index tables and seed the 14 collections

Backs the Collection Object Index context: staff-managed .xlsx sources per
scientific collection, indexed row-by-row as searchable collection objects.
The ``tsv`` column is a PostgreSQL generated column (config 'simple' — no
stemming, safer for catalogue data full of scientific names and codes);
``pg_trgm`` backs substring/code matching.

Revision ID: 0011_collection_object_index
Revises: 0010_doc_correction_events
Create Date: 2026-07-04
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_collection_object_index"
down_revision: str | None = "0010_doc_correction_events"
branch_labels: str | None = None
depends_on: str | None = None

COLLECTION_NAMES = [
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


def _collection_id(name: str) -> str:
    """Deterministic id so every environment seeds the same catalogue."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"vitarerum:collection:{name}"))


def upgrade() -> None:
    op.create_table(
        "collection_index_collection",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "collection_index_curator",
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("permission_id", sa.String(length=36), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_by", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("collection_id", "permission_id"),
        sa.ForeignKeyConstraint(["collection_id"], ["collection_index_collection.id"]),
    )

    op.create_table(
        "collection_index_source_document",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_reference", sa.String(length=512), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.String(length=36), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["collection_id"], ["collection_index_collection.id"]),
    )
    op.create_index(
        "ix_collection_index_source_document_collection_id",
        "collection_index_source_document",
        ["collection_id"],
    )
    op.create_index(
        "ix_collection_index_source_document_deleted_at",
        "collection_index_source_document",
        ["deleted_at"],
    )

    op.create_table(
        "collection_index_object",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("source_document_id", sa.String(length=36), nullable=False),
        sa.Column("sheet", sa.String(length=255), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("cells", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["collection_id"], ["collection_index_collection.id"]),
        sa.ForeignKeyConstraint(
            ["source_document_id"], ["collection_index_source_document.id"]
        ),
    )
    op.create_index(
        "ix_collection_index_object_collection_id",
        "collection_index_object",
        ["collection_id"],
    )
    op.create_index(
        "ix_collection_index_object_source_document_id",
        "collection_index_object",
        ["source_document_id"],
    )

    # Full-text (generated, 'simple' config) + trigram support for the search
    # read side (Objects -> Search plan).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "ALTER TABLE collection_index_object ADD COLUMN tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED"
    )
    op.execute(
        "CREATE INDEX ix_collection_index_object_tsv "
        "ON collection_index_object USING GIN (tsv)"
    )
    op.execute(
        "CREATE INDEX ix_collection_index_object_content_trgm "
        "ON collection_index_object USING GIN (content gin_trgm_ops)"
    )

    # Seed the 14 scientific collections (curators are assigned later via the
    # management API; the permission ids do not exist at migration time).
    collections = sa.table(
        "collection_index_collection",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    seeded_at = datetime.now(UTC)
    op.bulk_insert(
        collections,
        [
            {
                "id": _collection_id(name),
                "name": name,
                "active": True,
                "created_at": seeded_at,
                "updated_at": seeded_at,
            }
            for name in COLLECTION_NAMES
        ],
    )


def downgrade() -> None:
    op.drop_table("collection_index_object")
    op.drop_index(
        "ix_collection_index_source_document_deleted_at",
        table_name="collection_index_source_document",
    )
    op.drop_index(
        "ix_collection_index_source_document_collection_id",
        table_name="collection_index_source_document",
    )
    op.drop_table("collection_index_source_document")
    op.drop_table("collection_index_curator")
    op.drop_table("collection_index_collection")
