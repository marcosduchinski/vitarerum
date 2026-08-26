from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
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
    AgenticCandidateRelationKind,
    AgenticToolExecutionStatus,
    AgenticTrajectoryEventKind,
    AgentProgress,
    AgentRecommendedAction,
    CandidateStatus,
    DecisionType,
    EvidenceStrength,
    EvidenceType,
    FullAgenticInvestigationStatus,
    InvestigationMode,
    InvestigationObjective,
    InvestigationStatus,
    IterationStatus,
    KnowledgeKind,
    KnowledgeStatus,
    PolicyRejectionReason,
    QueryStatus,
    QueryType,
    RunKind,
    RunStatus,
    StopReason,
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
    run_kind: Mapped[RunKind] = mapped_column(
        SAEnum(RunKind, name="scientific_return_run_kind", native_enum=False),
        default=RunKind.DETERMINISTIC,
        index=True,
    )

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
    first_seen_run: Mapped[ScientificReturnRunRecord] = relationship()
    agentic_links: Mapped[list[AgenticInvestigationCandidateRecord]] = relationship()


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
    # Provenance of evidence added by an agentic investigation. Nullable so
    # every row written by the deterministic pipeline stays valid.
    investigation_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    iteration_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tool_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    query_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

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
    decision_context_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScientificReturnKnowledgeRecord(Base):
    __tablename__ = "sr_knowledge_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    institution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[KnowledgeKind] = mapped_column(
        SAEnum(KnowledgeKind, native_enum=False, length=64)
    )
    status: Mapped[KnowledgeStatus] = mapped_column(
        SAEnum(KnowledgeStatus, native_enum=False, length=16), index=True
    )
    content_encrypted: Mapped[str] = mapped_column(Text)
    registered_number_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_number_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    observed_form_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_form_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    source_decision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    proposed_by_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(96), nullable=True)
    created_by: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    validated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retired_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FullAgenticInvestigationRecord(Base):
    __tablename__ = "sr_full_agentic_investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    watch_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_watches.id"), index=True
    )
    objective: Mapped[InvestigationObjective] = mapped_column(
        SAEnum(InvestigationObjective, native_enum=False, length=32)
    )
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("scientific_return_candidates.id"), nullable=True, index=True
    )
    search_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("scientific_return_runs.id"), nullable=True, unique=True
    )
    status: Mapped[FullAgenticInvestigationStatus] = mapped_column(
        SAEnum(FullAgenticInvestigationStatus, native_enum=False, length=32), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    degraded_reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    cancel_requested_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=0)


class AgenticTrajectoryEventRecord(Base):
    __tablename__ = "sr_agentic_trajectory_events"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id", "sequence", name="uq_sr_agentic_event_sequence"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("sr_full_agentic_investigations.id"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    kind: Mapped[AgenticTrajectoryEventKind] = mapped_column(
        SAEnum(AgenticTrajectoryEventKind, native_enum=False, length=32)
    )
    payload_encrypted: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgenticKnowledgeUsageRecord(Base):
    __tablename__ = "sr_agentic_knowledge_usage"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id",
            "knowledge_item_id",
            "prompt_step",
            name="uq_sr_agentic_knowledge_usage",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("sr_full_agentic_investigations.id"), index=True
    )
    knowledge_item_id: Mapped[str] = mapped_column(
        ForeignKey("sr_knowledge_items.id"), index=True
    )
    prompt_step: Mapped[str] = mapped_column(String(64))
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgenticInvestigationCandidateRecord(Base):
    __tablename__ = "sr_agentic_investigation_candidates"

    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("sr_full_agentic_investigations.id"), primary_key=True
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_candidates.id"), primary_key=True
    )
    relation_kind: Mapped[AgenticCandidateRelationKind] = mapped_column(
        SAEnum(AgenticCandidateRelationKind, native_enum=False, length=16)
    )
    rank: Mapped[int] = mapped_column(Integer)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FullAgenticToolExecutionRecord(Base):
    __tablename__ = "sr_agentic_tool_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("sr_full_agentic_investigations.id"), index=True
    )
    trajectory_sequence: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[AgenticToolExecutionStatus] = mapped_column(
        SAEnum(AgenticToolExecutionStatus, native_enum=False, length=16), index=True
    )
    invocation_encrypted: Mapped[str] = mapped_column(Text)
    result_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


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


class ScientificReturnInvestigationRecord(Base):
    """One agentic investigation over a watch and, optionally, a candidate.

    ``candidate_id`` is nullable so a discovery investigation can exist for a
    watch whose deterministic run produced nothing actionable.
    """

    __tablename__ = "scientific_return_agent_investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    watch_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_watches.id"), index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("scientific_return_candidates.id"), nullable=True, index=True
    )
    initial_run_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_runs.id"), index=True
    )
    previous_investigation_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    objective: Mapped[InvestigationObjective] = mapped_column(
        SAEnum(
            InvestigationObjective,
            name="scientific_return_investigation_objective",
        )
    )
    status: Mapped[InvestigationStatus] = mapped_column(
        SAEnum(InvestigationStatus, name="scientific_return_investigation_status"),
        index=True,
    )
    mode: Mapped[InvestigationMode] = mapped_column(
        SAEnum(InvestigationMode, name="scientific_return_investigation_mode")
    )
    stop_reason: Mapped[StopReason | None] = mapped_column(
        SAEnum(StopReason, name="scientific_return_stop_reason"), nullable=True
    )
    current_iteration: Mapped[int] = mapped_column(Integer, default=0)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(36), index=True)
    contract_version: Mapped[str] = mapped_column(String(96))
    version: Mapped[int] = mapped_column(Integer, default=0)

    iterations: Mapped[list[ScientificReturnIterationRecord]] = relationship(
        back_populates="investigation",
        cascade="all, delete-orphan",
        order_by="ScientificReturnIterationRecord.number",
    )


class ScientificReturnIterationRecord(Base):
    __tablename__ = "scientific_return_agent_iterations"
    __table_args__ = (
        UniqueConstraint(
            "investigation_id",
            "number",
            name="uq_scientific_return_agent_iteration_number",
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_agent_investigations.id"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[IterationStatus] = mapped_column(
        SAEnum(IterationStatus, name="scientific_return_iteration_status")
    )
    # Observation, plan and reflection carry project data and model output and
    # are encrypted at rest, like the snapshot payload and the query text.
    observation_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_authorized: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    policy_rejection_reason: Mapped[PolicyRejectionReason | None] = mapped_column(
        SAEnum(
            PolicyRejectionReason,
            name="scientific_return_policy_rejection_reason",
        ),
        nullable=True,
    )
    policy_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[AgentProgress | None] = mapped_column(
        SAEnum(AgentProgress, name="scientific_return_agent_progress"), nullable=True
    )
    tool_execution_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    evidence_before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_delta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Which model and prompt produced this iteration, and what they cost.
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(96), nullable=True)
    plan_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reflection_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan_response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reflection_response_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    investigation: Mapped[ScientificReturnInvestigationRecord] = relationship(
        back_populates="iterations"
    )


class ScientificReturnToolExecutionRecord(Base):
    """One external tool run, keyed by the idempotency key issued before it.

    The key is unique, so replaying a command cannot execute the same tool
    twice: the second attempt finds this row and reuses its result.
    """

    __tablename__ = "scientific_return_agent_tool_executions"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_scientific_return_agent_tool_idempotency",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_return_agent_investigations.id"), index=True
    )
    iteration_id: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    action: Mapped[AgentRecommendedAction] = mapped_column(
        SAEnum(
            AgentRecommendedAction,
            name="scientific_return_agent_recommended_action",
        )
    )
    # The issued queries are project data and are encrypted, as run queries are.
    queries_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    total_results: Mapped[int] = mapped_column(Integer, default=0)
    created_candidate_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    added_evidence_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    result_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
