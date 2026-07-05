"""SQLAlchemy ORM models for the Collection Object Index context.

All tables carry the ``collection_index_`` prefix to distinguish this context
from the *collection-use* concept elsewhere in the schema.

``collection_index_object`` also has a PostgreSQL-only generated ``tsv``
column (``to_tsvector('simple', content)``, GIN-indexed) created by the
Alembic migration and intentionally NOT mapped here: the write side never
reads it, and leaving it unmapped keeps the model portable to the SQLite
test database.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CollectionRecord(Base):
    __tablename__ = "collection_index_collection"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CuratorRecord(Base):
    __tablename__ = "collection_index_curator"

    collection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("collection_index_collection.id"),
        primary_key=True,
    )
    permission_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    assigned_by: Mapped[str] = mapped_column(String(36))


class SourceDocumentRecord(Base):
    __tablename__ = "collection_index_source_document"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    collection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("collection_index_collection.id"),
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255))
    file_reference: Mapped[str] = mapped_column(String(512))
    source_kind: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(36))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class CollectionObjectRecord(Base):
    __tablename__ = "collection_index_object"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    collection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("collection_index_collection.id"),
        index=True,
    )
    source_document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("collection_index_source_document.id"),
        index=True,
    )
    sheet: Mapped[str] = mapped_column(String(255))
    row_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    cells: Mapped[dict[str, str]] = mapped_column(JSON)
