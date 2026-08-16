from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.scientific_return.domain.enums import (
    AgentAnalysisFeedback,
    AgentAnalysisStatus,
    AgentConfidence,
    AgentRecommendedAction,
    CandidateStatus,
    DecisionType,
    EvidenceStrength,
    EvidenceType,
    QueryStatus,
    QueryType,
    RunStatus,
    WatchStatus,
)


class ScientificReturnSnapshotRecord(Base):
    __tablename__ = "scientific_return_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    payload: Mapped[str] = mapped_column(Text)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    builder_version: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ScientificReturnWatchRecord(Base):
    __tablename__ = "scientific_return_watches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("collection_use_projects.id"), unique=True, index=True
    )
    status: Mapped[WatchStatus] = mapped_column(
        SAEnum(WatchStatus, name="scientific_return_watch_status")
    )
    review_interval_days: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    project_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_snapshots.id"), unique=True
    )


class ScientificReturnRunRecord(Base):
    __tablename__ = "scientific_return_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    watch_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_watches.id"), index=True
    )
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(RunStatus, name="scientific_return_run_status")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    new_candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    queries: Mapped[list[ScientificReturnQueryRecord]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ScientificReturnQueryRecord(Base):
    __tablename__ = "scientific_return_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_runs.id"), index=True
    )
    source: Mapped[str] = mapped_column(String(80))
    query_text: Mapped[str] = mapped_column(Text)
    query_type: Mapped[QueryType] = mapped_column(
        SAEnum(QueryType, name="scientific_return_query_type")
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[QueryStatus] = mapped_column(
        SAEnum(QueryStatus, name="scientific_return_query_status")
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[ScientificReturnRunRecord] = relationship(back_populates="queries")


class CandidatePublicationRecord(Base):
    __tablename__ = "scientific_return_candidates"
    __table_args__ = (
        UniqueConstraint(
            "watch_id", "deduplication_key", name="uq_scientific_return_candidate_key"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    watch_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_watches.id"), index=True
    )
    first_seen_run_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_runs.id"), index=True
    )
    source: Mapped[str] = mapped_column(String(80))
    source_record_id: Mapped[str] = mapped_column(String(255))
    deduplication_key: Mapped[str] = mapped_column(String(255))
    doi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(Text)
    authors: Mapped[list[str]] = mapped_column(JSON)
    publication_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_metadata_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[CandidateStatus] = mapped_column(
        SAEnum(CandidateStatus, name="scientific_return_candidate_status"), index=True
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_publication_entry_id: Mapped[str | None] = mapped_column(
        ForeignKey("publication_log_entries.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    evidences: Mapped[list[CandidateEvidenceRecord]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class CandidateEvidenceRecord(Base):
    __tablename__ = "scientific_return_evidences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_candidates.id"), index=True
    )
    type: Mapped[EvidenceType] = mapped_column(
        SAEnum(EvidenceType, name="scientific_return_evidence_type")
    )
    strength: Mapped[EvidenceStrength] = mapped_column(
        SAEnum(EvidenceStrength, name="scientific_return_evidence_strength")
    )
    value: Mapped[str] = mapped_column(Text)
    source_field: Mapped[str] = mapped_column(String(120))
    explanation: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    object_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    candidate: Mapped[CandidatePublicationRecord] = relationship(
        back_populates="evidences"
    )


class CandidateDecisionRecord(Base):
    __tablename__ = "scientific_return_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_candidates.id"), index=True
    )
    decision: Mapped[DecisionType] = mapped_column(
        SAEnum(DecisionType, name="scientific_return_decision_type")
    )
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(36), index=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    evidence_snapshot: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    correction: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class CandidateAgentAnalysisRecord(Base):
    __tablename__ = "scientific_return_agent_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_candidates.id"), index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_runs.id"), index=True
    )
    status: Mapped[AgentAnalysisStatus] = mapped_column(
        SAEnum(AgentAnalysisStatus, name="scientific_return_agent_analysis_status"),
        index=True,
    )
    model: Mapped[str] = mapped_column(String(128))
    prompt_version_id: Mapped[str] = mapped_column(String(36), index=True)
    prompt_version: Mapped[str] = mapped_column(String(96))
    input_payload: Mapped[str] = mapped_column(Text)
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    analysis_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[AgentRecommendedAction | None] = mapped_column(
        SAEnum(
            AgentRecommendedAction,
            name="scientific_return_agent_recommended_action",
        ),
        nullable=True,
    )
    confidence: Mapped[AgentConfidence | None] = mapped_column(
        SAEnum(AgentConfidence, name="scientific_return_agent_confidence"),
        nullable=True,
    )
    response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), index=True)
    staff_feedback: Mapped[AgentAnalysisFeedback | None] = mapped_column(
        SAEnum(AgentAnalysisFeedback, name="scientific_return_agent_feedback"),
        nullable=True,
    )
    feedback_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
