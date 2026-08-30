from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.scientific_return.application.full_agentic_ports import (
    InvestigationConcurrencyConflict,
)
from app.scientific_return.domain.enums import (
    FullAgenticInvestigationStatus,
    InvestigationObjective,
    KnowledgeStatus,
)
from app.scientific_return.domain.full_agentic_models import (
    AgenticBudget,
    AgenticCandidateLink,
    AgenticToolExecution,
    AgenticToolExecutionId,
    AgenticTrajectoryEvent,
    AgenticTrajectoryEventId,
    AgenticUsage,
    FullAgenticInvestigation,
    FullAgenticInvestigationId,
    KnowledgeItemId,
    ScientificReturnKnowledgeItem,
)
from app.scientific_return.domain.models import (
    CandidateDecisionId,
    CandidatePublicationId,
    ScientificReturnRunId,
    ScientificReturnWatchId,
)
from app.scientific_return.infrastructure.models import (
    AgenticInvestigationCandidateRecord,
    AgenticKnowledgeUsageRecord,
    AgenticTrajectoryEventRecord,
    FullAgenticInvestigationRecord,
    FullAgenticToolExecutionRecord,
    ScientificReturnKnowledgeRecord,
)
from app.shared.field_encryption import FieldEncryptor
from app.shared.kernel import PermissionId

_KNOWLEDGE_CONTENT = "scientific_return.knowledge.content"
_REGISTERED_NUMBER = "scientific_return.knowledge.registered_number"
_REGISTERED_HASH = "scientific_return.knowledge.registered_number_hash"
_OBSERVED_FORM = "scientific_return.knowledge.observed_form"
_OBSERVED_HASH = "scientific_return.knowledge.observed_form_hash"
_TRAJECTORY_PAYLOAD = "scientific_return.full_agentic.trajectory"
_TOOL_INVOCATION = "scientific_return.full_agentic.tool.invocation"
_TOOL_RESULT = "scientific_return.full_agentic.tool.result"


def _knowledge_to_domain(
    record: ScientificReturnKnowledgeRecord, encryptor: FieldEncryptor
) -> ScientificReturnKnowledgeItem:
    return ScientificReturnKnowledgeItem(
        id=KnowledgeItemId(record.id),
        institution_id=record.institution_id,
        kind=record.kind,
        status=record.status,
        content=encryptor.decrypt_text(record.content_encrypted, _KNOWLEDGE_CONTENT)
        or "",
        registered_number=encryptor.decrypt_text(
            record.registered_number_encrypted, _REGISTERED_NUMBER
        ),
        observed_form=encryptor.decrypt_text(
            record.observed_form_encrypted, _OBSERVED_FORM
        ),
        source_candidate_id=CandidatePublicationId(record.source_candidate_id)
        if record.source_candidate_id
        else None,
        source_decision_id=CandidateDecisionId(record.source_decision_id)
        if record.source_decision_id
        else None,
        supersedes_id=KnowledgeItemId(record.supersedes_id)
        if record.supersedes_id
        else None,
        proposed_by_model=record.proposed_by_model,
        prompt_version=record.prompt_version,
        created_by=PermissionId(record.created_by),
        created_at=record.created_at,
        validated_by=PermissionId(record.validated_by) if record.validated_by else None,
        validated_at=record.validated_at,
        retired_by=PermissionId(record.retired_by) if record.retired_by else None,
        retired_at=record.retired_at,
    )


def _budget(payload: dict[str, Any]) -> AgenticBudget:
    return AgenticBudget(
        max_iterations=int(payload["max_iterations"]),
        max_queries=int(payload["max_queries"]),
        max_results=int(payload["max_results"]),
        max_candidates=int(payload["max_candidates"]),
        max_llm_calls=int(payload["max_llm_calls"]),
    )


def _usage(payload: dict[str, Any]) -> AgenticUsage:
    return AgenticUsage(**{key: int(value) for key, value in payload.items()})


def _investigation_to_domain(
    record: FullAgenticInvestigationRecord,
) -> FullAgenticInvestigation:
    return FullAgenticInvestigation(
        id=FullAgenticInvestigationId(record.id),
        watch_id=ScientificReturnWatchId(record.watch_id),
        objective=record.objective,
        candidate_id=CandidatePublicationId(record.candidate_id)
        if record.candidate_id
        else None,
        object_id=record.object_id,
        search_run_id=ScientificReturnRunId(record.search_run_id)
        if record.search_run_id
        else None,
        status=record.status,
        idempotency_key=record.idempotency_key,
        budget=_budget(record.budget),
        usage=_usage(record.usage),
        created_by=PermissionId(record.created_by),
        created_at=record.created_at,
        heartbeat_at=record.heartbeat_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        failure_reason=record.failure_reason,
        degraded_reason=record.degraded_reason,
        cancel_requested_by=PermissionId(record.cancel_requested_by)
        if record.cancel_requested_by
        else None,
        lease_owner=record.lease_owner,
        lease_expires_at=record.lease_expires_at,
        recovery_count=record.recovery_count,
        last_recovered_at=record.last_recovered_at,
        last_recovery_reason=record.last_recovery_reason,
        version=record.version,
    )


class SqlAlchemyFullAgenticRepository:
    def __init__(self, session: AsyncSession, encryptor: FieldEncryptor) -> None:
        self._session = session
        self._encryptor = encryptor

    async def add_knowledge(self, item: ScientificReturnKnowledgeItem) -> None:
        self._session.add(
            ScientificReturnKnowledgeRecord(
                id=item.id,
                institution_id=item.institution_id,
                kind=item.kind,
                status=item.status,
                content_encrypted=self._encryptor.encrypt_required_text(
                    item.content, _KNOWLEDGE_CONTENT
                ),
                registered_number_encrypted=self._encryptor.encrypt_text(
                    item.registered_number, _REGISTERED_NUMBER
                ),
                registered_number_hash=self._encryptor.lookup_hash(
                    item.registered_number, _REGISTERED_HASH
                ),
                observed_form_encrypted=self._encryptor.encrypt_text(
                    item.observed_form, _OBSERVED_FORM
                ),
                observed_form_hash=self._encryptor.lookup_hash(
                    item.observed_form, _OBSERVED_HASH
                ),
                source_candidate_id=item.source_candidate_id,
                source_decision_id=item.source_decision_id,
                supersedes_id=item.supersedes_id,
                proposed_by_model=item.proposed_by_model,
                prompt_version=item.prompt_version,
                created_by=item.created_by,
                created_at=item.created_at,
                validated_by=item.validated_by,
                validated_at=item.validated_at,
                retired_by=item.retired_by,
                retired_at=item.retired_at,
            )
        )
        await self._session.flush()

    async def save_knowledge(self, item: ScientificReturnKnowledgeItem) -> None:
        record = await self._session.get(ScientificReturnKnowledgeRecord, item.id)
        if record is None:
            raise LookupError(f"Knowledge item {item.id} not found")
        record.status = item.status
        record.validated_by = item.validated_by
        record.validated_at = item.validated_at
        record.retired_by = item.retired_by
        record.retired_at = item.retired_at
        await self._session.flush()

    async def get_knowledge(
        self, item_id: KnowledgeItemId
    ) -> ScientificReturnKnowledgeItem | None:
        record = await self._session.get(ScientificReturnKnowledgeRecord, item_id)
        return _knowledge_to_domain(record, self._encryptor) if record else None

    async def list_knowledge(
        self, *, active_only: bool, limit: int
    ) -> list[ScientificReturnKnowledgeItem]:
        statement = select(ScientificReturnKnowledgeRecord)
        if active_only:
            statement = statement.where(
                ScientificReturnKnowledgeRecord.status == KnowledgeStatus.ACTIVE
            )
        result = await self._session.execute(
            statement.order_by(ScientificReturnKnowledgeRecord.created_at.desc()).limit(
                limit
            )
        )
        return [_knowledge_to_domain(row, self._encryptor) for row in result.scalars()]

    async def find_knowledge_exact(
        self, registered_number: str, limit: int
    ) -> list[ScientificReturnKnowledgeItem]:
        value_hash = self._encryptor.lookup_required_hash(
            registered_number, _REGISTERED_HASH
        )
        result = await self._session.execute(
            select(ScientificReturnKnowledgeRecord)
            .where(
                ScientificReturnKnowledgeRecord.status == KnowledgeStatus.ACTIVE,
                ScientificReturnKnowledgeRecord.registered_number_hash == value_hash,
            )
            .limit(limit)
        )
        return [_knowledge_to_domain(row, self._encryptor) for row in result.scalars()]

    async def add_investigation(self, investigation: FullAgenticInvestigation) -> None:
        self._session.add(
            FullAgenticInvestigationRecord(
                id=investigation.id,
                watch_id=investigation.watch_id,
                objective=investigation.objective,
                candidate_id=investigation.candidate_id,
                search_run_id=investigation.search_run_id,
                object_id=investigation.object_id,
                status=investigation.status,
                idempotency_key=investigation.idempotency_key,
                budget={
                    "max_iterations": investigation.budget.max_iterations,
                    "max_queries": investigation.budget.max_queries,
                    "max_results": investigation.budget.max_results,
                    "max_candidates": investigation.budget.max_candidates,
                    "max_llm_calls": investigation.budget.max_llm_calls,
                },
                usage={
                    "iterations": 0,
                    "queries": 0,
                    "results": 0,
                    "candidates": 0,
                    "llm_calls": 0,
                },
                created_by=investigation.created_by,
                created_at=investigation.created_at,
                version=investigation.version,
            )
        )
        await self._session.flush()

    async def save_investigation(self, investigation: FullAgenticInvestigation) -> None:
        next_version = (
            await self._session.execute(
                update(FullAgenticInvestigationRecord)
                .where(
                    FullAgenticInvestigationRecord.id == investigation.id,
                    FullAgenticInvestigationRecord.version == investigation.version,
                )
                .values(
                    status=investigation.status,
                    search_run_id=investigation.search_run_id,
                    usage={
                        "iterations": investigation.usage.iterations,
                        "queries": investigation.usage.queries,
                        "results": investigation.usage.results,
                        "candidates": investigation.usage.candidates,
                        "llm_calls": investigation.usage.llm_calls,
                    },
                    heartbeat_at=investigation.heartbeat_at,
                    started_at=investigation.started_at,
                    completed_at=investigation.completed_at,
                    failure_reason=investigation.failure_reason,
                    degraded_reason=investigation.degraded_reason,
                    cancel_requested_by=investigation.cancel_requested_by,
                    lease_owner=investigation.lease_owner,
                    lease_expires_at=investigation.lease_expires_at,
                    recovery_count=investigation.recovery_count,
                    last_recovered_at=investigation.last_recovered_at,
                    last_recovery_reason=investigation.last_recovery_reason,
                    version=FullAgenticInvestigationRecord.version + 1,
                )
                .returning(FullAgenticInvestigationRecord.version)
            )
        ).scalar_one_or_none()
        if next_version is None:
            raise InvestigationConcurrencyConflict(
                f"Investigation {investigation.id} changed concurrently"
            )
        investigation.version = int(next_version)
        await self._session.flush()

    async def claim_investigation(
        self,
        investigation_id: FullAgenticInvestigationId,
        worker_id: str,
        claimed_at: datetime,
        lease_expires_at: datetime,
    ) -> FullAgenticInvestigation | None:
        record = (
            await self._session.execute(
                update(FullAgenticInvestigationRecord)
                .where(
                    FullAgenticInvestigationRecord.id == investigation_id,
                    or_(
                        FullAgenticInvestigationRecord.status
                        == FullAgenticInvestigationStatus.QUEUED,
                        (
                            FullAgenticInvestigationRecord.status.in_(
                                (
                                    FullAgenticInvestigationStatus.RUNNING,
                                    FullAgenticInvestigationStatus.CANCEL_REQUESTED,
                                )
                            )
                            & or_(
                                FullAgenticInvestigationRecord.lease_expires_at.is_(
                                    None
                                ),
                                FullAgenticInvestigationRecord.lease_expires_at
                                <= claimed_at,
                            )
                        ),
                    ),
                )
                .values(
                    status=case(
                        (
                            FullAgenticInvestigationRecord.status
                            == FullAgenticInvestigationStatus.QUEUED,
                            FullAgenticInvestigationStatus.RUNNING,
                        ),
                        else_=FullAgenticInvestigationRecord.status,
                    ),
                    started_at=case(
                        (
                            FullAgenticInvestigationRecord.status
                            == FullAgenticInvestigationStatus.QUEUED,
                            claimed_at,
                        ),
                        else_=FullAgenticInvestigationRecord.started_at,
                    ),
                    heartbeat_at=claimed_at,
                    lease_owner=worker_id,
                    lease_expires_at=lease_expires_at,
                    # Only a take-over counts. A queued row is either a first
                    # claim or a slice the worker handed back on purpose, and
                    # charging those would spend the allowance on healthy work.
                    recovery_count=case(
                        (
                            FullAgenticInvestigationRecord.status
                            == FullAgenticInvestigationStatus.QUEUED,
                            FullAgenticInvestigationRecord.recovery_count,
                        ),
                        else_=FullAgenticInvestigationRecord.recovery_count + 1,
                    ),
                    last_recovered_at=case(
                        (
                            FullAgenticInvestigationRecord.status
                            == FullAgenticInvestigationStatus.QUEUED,
                            FullAgenticInvestigationRecord.last_recovered_at,
                        ),
                        else_=claimed_at,
                    ),
                    last_recovery_reason=case(
                        (
                            FullAgenticInvestigationRecord.status
                            == FullAgenticInvestigationStatus.QUEUED,
                            FullAgenticInvestigationRecord.last_recovery_reason,
                        ),
                        else_="Lease expired before the worker finished",
                    ),
                    version=FullAgenticInvestigationRecord.version + 1,
                )
                .returning(FullAgenticInvestigationRecord)
            )
        ).scalar_one_or_none()
        await self._session.flush()
        return _investigation_to_domain(record) if record is not None else None

    async def renew_investigation_lease(
        self,
        investigation_id: FullAgenticInvestigationId,
        worker_id: str,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> int | None:
        next_version = (
            await self._session.execute(
                update(FullAgenticInvestigationRecord)
                .where(
                    FullAgenticInvestigationRecord.id == investigation_id,
                    FullAgenticInvestigationRecord.status
                    == FullAgenticInvestigationStatus.RUNNING,
                    FullAgenticInvestigationRecord.lease_owner == worker_id,
                    FullAgenticInvestigationRecord.lease_expires_at > heartbeat_at,
                )
                .values(
                    heartbeat_at=heartbeat_at,
                    lease_expires_at=lease_expires_at,
                    version=FullAgenticInvestigationRecord.version + 1,
                )
                .returning(FullAgenticInvestigationRecord.version)
            )
        ).scalar_one_or_none()
        await self._session.flush()
        return int(next_version) if next_version is not None else None

    async def reserve_llm_call(
        self,
        investigation: FullAgenticInvestigation,
        worker_id: str,
        heartbeat_at: datetime,
        lease_expires_at: datetime,
    ) -> int | None:
        """Charge the reserved call and renew the lease in one statement.

        The guard is the lease, not only the version: a worker whose lease was
        taken while it was thinking must not be able to spend the budget of an
        investigation somebody else is now running. Returning ``None`` says
        exactly that, and the caller stops.

        ``usage`` is a JSON document, so the new counters are computed by the
        aggregate — which owns the ceiling — and written here under the guard.
        """
        next_version = (
            await self._session.execute(
                update(FullAgenticInvestigationRecord)
                .where(
                    FullAgenticInvestigationRecord.id == investigation.id,
                    FullAgenticInvestigationRecord.version == investigation.version,
                    FullAgenticInvestigationRecord.status
                    == FullAgenticInvestigationStatus.RUNNING,
                    FullAgenticInvestigationRecord.lease_owner == worker_id,
                    FullAgenticInvestigationRecord.lease_expires_at > heartbeat_at,
                )
                .values(
                    usage={
                        "iterations": investigation.usage.iterations,
                        "queries": investigation.usage.queries,
                        "results": investigation.usage.results,
                        "candidates": investigation.usage.candidates,
                        "llm_calls": investigation.usage.llm_calls,
                    },
                    heartbeat_at=heartbeat_at,
                    lease_expires_at=lease_expires_at,
                    version=FullAgenticInvestigationRecord.version + 1,
                )
                .returning(FullAgenticInvestigationRecord.version)
            )
        ).scalar_one_or_none()
        await self._session.flush()
        return int(next_version) if next_version is not None else None

    async def get_investigation(
        self, investigation_id: FullAgenticInvestigationId
    ) -> FullAgenticInvestigation | None:
        record = await self._session.get(
            FullAgenticInvestigationRecord, investigation_id, populate_existing=True
        )
        return _investigation_to_domain(record) if record else None

    async def list_abandoned(
        self, created_before: datetime, limit: int
    ) -> list[FullAgenticInvestigation]:
        """Live rows older than the ceiling, oldest first.

        Age is measured from creation, not from the last heartbeat: a row that
        keeps being recovered stays warm forever while never finishing, and it
        is exactly that row the ceiling exists to end.
        """
        records = (
            (
                await self._session.execute(
                    select(FullAgenticInvestigationRecord)
                    .where(
                        FullAgenticInvestigationRecord.status.in_(
                            (
                                FullAgenticInvestigationStatus.QUEUED,
                                FullAgenticInvestigationStatus.RUNNING,
                                FullAgenticInvestigationStatus.CANCEL_REQUESTED,
                            )
                        ),
                        FullAgenticInvestigationRecord.created_at < created_before,
                    )
                    .order_by(FullAgenticInvestigationRecord.created_at)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [_investigation_to_domain(record) for record in records]

    async def get_by_idempotency_key(self, key: str) -> FullAgenticInvestigation | None:
        record = (
            await self._session.execute(
                select(FullAgenticInvestigationRecord).where(
                    FullAgenticInvestigationRecord.idempotency_key == key
                )
            )
        ).scalar_one_or_none()
        return _investigation_to_domain(record) if record else None

    async def find_live_target(
        self,
        watch_id: str,
        objective: str,
        candidate_id: str | None,
        object_id: str | None = None,
    ) -> FullAgenticInvestigation | None:
        """The live investigation of this exact target, if there is one.

        The target includes the consulted object: two objects of the same
        project are two targets, and each may be investigated at the same time.
        This mirrors the partial unique index that enforces it in the database.
        """
        record = (
            await self._session.execute(
                select(FullAgenticInvestigationRecord).where(
                    FullAgenticInvestigationRecord.watch_id == watch_id,
                    FullAgenticInvestigationRecord.objective
                    == InvestigationObjective(objective),
                    FullAgenticInvestigationRecord.candidate_id == candidate_id,
                    FullAgenticInvestigationRecord.object_id == object_id,
                    FullAgenticInvestigationRecord.status.in_(
                        (
                            FullAgenticInvestigationStatus.QUEUED,
                            FullAgenticInvestigationStatus.RUNNING,
                            FullAgenticInvestigationStatus.CANCEL_REQUESTED,
                        )
                    ),
                )
            )
        ).scalar_one_or_none()
        return _investigation_to_domain(record) if record else None

    async def list_investigations(
        self, watch_id: str, limit: int
    ) -> list[FullAgenticInvestigation]:
        result = await self._session.execute(
            select(FullAgenticInvestigationRecord)
            .where(FullAgenticInvestigationRecord.watch_id == watch_id)
            .order_by(FullAgenticInvestigationRecord.created_at.desc())
            .limit(limit)
        )
        return [_investigation_to_domain(row) for row in result.scalars()]

    async def append_event(self, event: AgenticTrajectoryEvent) -> None:
        self._session.add(
            AgenticTrajectoryEventRecord(
                id=event.id,
                investigation_id=event.investigation_id,
                sequence=event.sequence,
                kind=event.kind,
                payload_encrypted=self._encryptor.encrypt_json(
                    event.payload, _TRAJECTORY_PAYLOAD
                )
                or "",
                occurred_at=event.occurred_at,
            )
        )
        await self._session.flush()

    async def list_events(
        self, investigation_id: FullAgenticInvestigationId
    ) -> list[AgenticTrajectoryEvent]:
        result = await self._session.execute(
            select(AgenticTrajectoryEventRecord)
            .where(AgenticTrajectoryEventRecord.investigation_id == investigation_id)
            .order_by(AgenticTrajectoryEventRecord.sequence)
        )
        return [
            AgenticTrajectoryEvent(
                id=AgenticTrajectoryEventId(row.id),
                investigation_id=investigation_id,
                sequence=row.sequence,
                kind=row.kind,
                payload=cast(
                    dict[str, object],
                    self._encryptor.decrypt_json(
                        row.payload_encrypted, _TRAJECTORY_PAYLOAD
                    ),
                ),
                occurred_at=row.occurred_at,
            )
            for row in result.scalars()
        ]

    async def next_event_sequence(
        self, investigation_id: FullAgenticInvestigationId
    ) -> int:
        value = await self._session.scalar(
            select(
                func.coalesce(func.max(AgenticTrajectoryEventRecord.sequence), 0) + 1
            ).where(AgenticTrajectoryEventRecord.investigation_id == investigation_id)
        )
        return int(value or 1)

    async def add_knowledge_usage(
        self,
        investigation_id: str,
        knowledge_item_id: str,
        prompt_step: str,
        used_at: Any,
    ) -> None:
        self._session.add(
            AgenticKnowledgeUsageRecord(
                id=str(uuid4()),
                investigation_id=investigation_id,
                knowledge_item_id=knowledge_item_id,
                prompt_step=prompt_step,
                used_at=used_at,
            )
        )
        await self._session.flush()

    async def link_candidate(self, link: AgenticCandidateLink) -> bool:
        inserted = (
            await self._session.execute(
                insert(AgenticInvestigationCandidateRecord)
                .values(
                    investigation_id=link.investigation_id,
                    candidate_id=link.candidate_id,
                    relation_kind=link.relation_kind,
                    rank=link.rank,
                    linked_at=link.linked_at,
                )
                .on_conflict_do_nothing(
                    index_elements=("investigation_id", "candidate_id")
                )
                .returning(AgenticInvestigationCandidateRecord.candidate_id)
            )
        ).scalar_one_or_none()
        await self._session.flush()
        return inserted is not None

    async def add_tool_execution(self, execution: AgenticToolExecution) -> None:
        self._session.add(
            FullAgenticToolExecutionRecord(
                id=execution.id,
                investigation_id=execution.investigation_id,
                trajectory_sequence=execution.trajectory_sequence,
                idempotency_key=execution.idempotency_key,
                status=execution.status,
                invocation_encrypted=self._encryptor.encrypt_json(
                    execution.invocation, _TOOL_INVOCATION
                )
                or "",
                attempts=execution.attempts,
                lease_expires_at=execution.lease_expires_at,
                started_at=execution.started_at,
            )
        )
        await self._session.flush()

    async def save_tool_execution(self, execution: AgenticToolExecution) -> None:
        record = await self._session.get(FullAgenticToolExecutionRecord, execution.id)
        if record is None:
            raise LookupError(f"Tool execution {execution.id} not found")
        record.status = execution.status
        record.result_encrypted = self._encryptor.encrypt_json(
            execution.result, _TOOL_RESULT
        )
        record.result_hash = execution.result_hash
        record.attempts = execution.attempts
        record.lease_expires_at = execution.lease_expires_at
        record.completed_at = execution.completed_at
        record.error_message = execution.error_message
        await self._session.flush()

    async def get_tool_execution(self, key: str) -> AgenticToolExecution | None:
        record = (
            await self._session.execute(
                select(FullAgenticToolExecutionRecord).where(
                    FullAgenticToolExecutionRecord.idempotency_key == key
                )
            )
        ).scalar_one_or_none()
        if record is None:
            return None
        return AgenticToolExecution(
            id=AgenticToolExecutionId(record.id),
            investigation_id=FullAgenticInvestigationId(record.investigation_id),
            trajectory_sequence=record.trajectory_sequence,
            idempotency_key=record.idempotency_key,
            status=record.status,
            invocation=cast(
                dict[str, object],
                self._encryptor.decrypt_json(
                    record.invocation_encrypted, _TOOL_INVOCATION
                ),
            ),
            result=cast(
                dict[str, object] | None,
                self._encryptor.decrypt_json(record.result_encrypted, _TOOL_RESULT),
            ),
            result_hash=record.result_hash,
            attempts=record.attempts,
            lease_expires_at=record.lease_expires_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            error_message=record.error_message,
        )
