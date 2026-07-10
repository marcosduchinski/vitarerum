"""SQLAlchemy ORM model for the museum-question triage context.

A single table, ``museum_question_triages``, storing one row per triage run.
``question_id`` references a ``MuseumQuestion`` in the ``museum_questions``
context but is kept as a plain string (no cross-context FK, same convention
as ``generated_narratives.record_id``). Each entry in
``mentioned_objects``/``object_matches`` carries both an English and a
Portuguese name (``{"english": ..., "portuguese": ...}``), since the catalogue
is searched in both languages. ``object_matches`` also stores a snapshot of
the catalogue search results so the "AI assistance" tab doesn't need to
re-search on reload.

Mutability: ``verdict``/``is_visit_related``/``llm_model``/``created_at`` are
fixed at creation. ``mentioned_objects``, ``object_matches`` and
``suggested_reply`` can be revised in place afterwards (see
``domain/models.py``'s module docstring), and the three ``staff_override_*``
columns record a staff correction of the scope verdict — last-write-wins, no
optimistic-concurrency check (accepted MVP limitation, see
docs/plans/museum-questions-ai-triage-refinements-plan.md).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MessageTriageOrm(Base):
    __tablename__ = "museum_question_triages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    question_id: Mapped[str] = mapped_column(String(36), index=True)
    verdict: Mapped[str] = mapped_column(String(16))
    is_visit_related: Mapped[bool] = mapped_column(Boolean)
    mentioned_objects: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    object_matches: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    suggested_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    staff_override_verdict: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    staff_override_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    staff_override_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
