"""SQLAlchemy ORM model for the KG-RAG museum-narrative context.

A single table, ``generated_narratives``, storing one immutable row per
generation. ``record_id`` references an ``InSituVisitRecord`` in the
``cidoc_crm`` context but is kept as a plain string (no cross-context FK).
``narrative_type`` / ``resolution_source`` are stored as plain strings, not
native PG enums.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


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
