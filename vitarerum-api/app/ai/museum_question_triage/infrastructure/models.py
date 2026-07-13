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

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
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


class MessageClassificationOrm(Base):
    __tablename__ = "museum_question_triage_classifications"
    __table_args__ = (
        Index(
            "ix_mq_triage_classifications_current",
            "triage_id",
            "classifier_kind",
            "superseded_at",
        ),
        Index(
            "ix_mq_triage_classifications_pending",
            "status",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    triage_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    classifier_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    classifier_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    classifier_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    category_scores: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    assigned_categories: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False
    )
    classified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class UseCategoryTrainingExampleOrm(Base):
    __tablename__ = "museum_question_use_category_training_examples"
    __table_args__ = (
        Index(
            "ix_mq_use_category_training_current_triage",
            "triage_id",
            "superseded_at",
        ),
        Index(
            "ix_mq_use_category_training_active_question",
            "question_id",
            "active",
            "superseded_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    triage_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_by_example_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    human_outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    human_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    llm_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    embedding_categories: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    message_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class EmbeddingPrototypeVersionOrm(Base):
    __tablename__ = "museum_question_embedding_prototype_versions"
    __table_args__ = (
        Index(
            "ix_mq_embedding_prototype_versions_promoted",
            "promoted_at",
            "retired_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregation_method: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold_profile: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    example_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    prototypes: Mapped[dict[str, list[list[float]]]] = mapped_column(
        JSON, nullable=False
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
