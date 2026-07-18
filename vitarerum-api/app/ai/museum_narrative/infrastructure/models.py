"""SQLAlchemy ORM models for the KG-RAG museum-narrative context.

``record_id`` references an ``InSituVisitRecord`` in the ``cidoc_crm`` context
but is kept as a plain string (no cross-context FK). ``narrative_type`` /
``resolution_source`` are stored as plain strings, not native PG enums.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NarrativeFactSnapshotOrm(Base):
    __tablename__ = "narrative_fact_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(36), index=True)
    payload_json: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    builder_version: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cidoc_document_json: Mapped[str | None] = mapped_column(Text)
    cidoc_validation_report: Mapped[str | None] = mapped_column(Text)
    cidoc_conforms: Mapped[bool | None] = mapped_column(Boolean)


class GeneratedNarrativeOrm(Base):
    __tablename__ = "generated_narratives"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(36), index=True)
    narrative: Mapped[str] = mapped_column(Text)
    narrative_type: Mapped[str] = mapped_column(String(64))
    resolution_source: Mapped[str] = mapped_column(String(32))
    target_language: Mapped[str] = mapped_column(String(16))
    creativity_temperature: Mapped[float] = mapped_column(Float)
    llm_model: Mapped[str] = mapped_column(String(128))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    facts_snapshot_id: Mapped[str | None] = mapped_column(String(36), index=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    model_response_hash: Mapped[str | None] = mapped_column(String(64))
    validation_conforms: Mapped[bool | None] = mapped_column(Boolean)
    validation_findings: Mapped[list[dict[str, str]] | None] = mapped_column(JSON)


class GeneratedNarrativeRevisionOrm(Base):
    __tablename__ = "generated_narrative_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    narrative_id: Mapped[str] = mapped_column(String(36), index=True)
    previous_narrative: Mapped[str] = mapped_column(Text)
    revised_narrative: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    edited_by: Mapped[str | None] = mapped_column(String(36))
