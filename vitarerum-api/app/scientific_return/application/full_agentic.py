from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import uuid4

from app.identity.public import Actor, GroupName
from app.scientific_return.application.agent_tools import (
    normalized_tool_idempotency_key,
)
from app.scientific_return.application.analysis import deduplication_key
from app.scientific_return.application.full_agentic_ports import (
    AgenticInvestigationDispatcher,
    AgenticPlan,
    FullAgenticClock,
    FullAgenticReasoner,
    FullAgenticRepository,
    FullAgenticUnitOfWork,
    InvestigationConcurrencyConflict,
)
from app.scientific_return.application.knowledge import retrieve_relevant_knowledge
from app.scientific_return.application.ports import (
    BibliographicRecord,
    BibliographicSource,
    ScientificReturnRepository,
)
from app.scientific_return.domain.enums import (
    AgentAnalysisStatus,
    AgenticCandidateRelationKind,
    AgenticToolExecutionStatus,
    AgenticTrajectoryEventKind,
    AgentRecommendedAction,
    CandidateStatus,
    FullAgenticInvestigationStatus,
    InvestigationObjective,
    QueryStatus,
    QueryType,
    RunKind,
    RunStatus,
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
)
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidateAnalysisResult,
    CandidatePublication,
    CandidatePublicationId,
    ScientificReturnQuery,
    ScientificReturnQueryId,
    ScientificReturnRunId,
    ScientificReturnSearchRun,
    ScientificReturnWatchId,
)
from app.shared.authorization import require_group, require_staff

_MUTATION_GROUPS = (
    GroupName.CURATORIAL,
    GroupName.COLLECTIONS_MANAGEMENT,
    GroupName.DIRECTION,
)


def _string_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key, [])
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


class FullAgenticDisabled(RuntimeError):
    pass


class FullAgenticAlreadyRunning(RuntimeError):
    pass


class FullAgenticCircuitOpen(RuntimeError):
    pass


class _InvestigationLeaseLost(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FullAgenticConfiguration:
    enabled: bool
    allowed_sources: tuple[str, ...]
    budget: AgenticBudget
    memory_limit: int = 30
    tool_lease_seconds: int = 120
    investigation_lease_seconds: int = 900
    circuit_min_decisions: int = 0
    circuit_min_precision: float = 0.0

    def __post_init__(self) -> None:
        if self.circuit_min_decisions < 0:
            raise ValueError("Circuit-breaker sample cannot be negative")
        if not 0.0 <= self.circuit_min_precision <= 1.0:
            raise ValueError("Circuit-breaker precision must be between zero and one")
        if self.investigation_lease_seconds < 60:
            raise ValueError("Investigation lease must be at least 60 seconds")


@dataclass(frozen=True, slots=True)
class StartFullAgenticInput:
    watch_id: ScientificReturnWatchId
    objective: InvestigationObjective
    candidate_id: CandidatePublicationId | None
    idempotency_key: str
    caller: Actor


class StartFullAgenticScientificReturn:
    def __init__(
        self,
        scientific_repository: ScientificReturnRepository,
        repository: FullAgenticRepository,
        dispatcher: AgenticInvestigationDispatcher,
        unit_of_work: FullAgenticUnitOfWork,
        clock: FullAgenticClock,
        configuration: FullAgenticConfiguration,
    ) -> None:
        self._scientific_repository = scientific_repository
        self._repository = repository
        self._dispatcher = dispatcher
        self._uow = unit_of_work
        self._clock = clock
        self._configuration = configuration

    async def execute(self, data: StartFullAgenticInput) -> FullAgenticInvestigation:
        require_group(data.caller, *_MUTATION_GROUPS)
        existing = await self._repository.get_by_idempotency_key(data.idempotency_key)
        if existing is not None:
            if (
                existing.watch_id != data.watch_id
                or existing.objective is not data.objective
                or existing.candidate_id != data.candidate_id
            ):
                raise ValueError(
                    "Idempotency-Key is already bound to another full-agentic target"
                )
            return existing
        if (
            data.objective is not InvestigationObjective.DISCOVER_CANDIDATE
            or data.candidate_id is not None
        ):
            raise ValueError(
                "The full-agentic flow currently supports only DISCOVER_CANDIDATE"
            )
        if not self._configuration.enabled:
            raise FullAgenticDisabled("The full-agentic flow is disabled")
        minimum = self._configuration.circuit_min_decisions
        if minimum:
            metrics = await self._scientific_repository.get_metrics()
            decided = (
                metrics.full_agentic_confirmed_candidates
                + metrics.full_agentic_dismissed_candidates
            )
            precision = (
                metrics.full_agentic_confirmed_candidates / decided if decided else 1.0
            )
            if (
                decided >= minimum
                and precision < self._configuration.circuit_min_precision
            ):
                raise FullAgenticCircuitOpen(
                    "New autonomous investigations are paused because curator "
                    f"precision is {precision:.1%} over {decided} decided candidates"
                )
        watch = await self._scientific_repository.get_watch(data.watch_id)
        if watch is None:
            raise LookupError(f"Scientific-return watch {data.watch_id} not found")
        if data.candidate_id is not None:
            candidate = await self._scientific_repository.get_candidate(
                data.candidate_id
            )
            if candidate is None or candidate.watch_id != data.watch_id:
                raise ValueError("candidateId does not belong to the watch")
        live = await self._repository.find_live_target(
            str(data.watch_id),
            data.objective.value,
            str(data.candidate_id) if data.candidate_id else None,
        )
        if live is not None:
            raise FullAgenticAlreadyRunning(
                f"Investigation {live.id} is already live for this target"
            )
        investigation = FullAgenticInvestigation(
            id=FullAgenticInvestigationId(str(uuid4())),
            watch_id=data.watch_id,
            objective=data.objective,
            candidate_id=data.candidate_id,
            status=FullAgenticInvestigationStatus.QUEUED,
            idempotency_key=data.idempotency_key,
            budget=self._configuration.budget,
            usage=AgenticUsage(),
            created_by=data.caller.id,
            created_at=self._clock.now(),
        )
        await self._repository.add_investigation(investigation)
        await self._uow.commit()
        try:
            await self._dispatcher.enqueue(investigation.id)
        except Exception:
            # The durable QUEUED row remains claimable by a polling worker.
            raise
        return investigation


@dataclass(frozen=True, slots=True)
class ExecuteFullAgenticInput:
    investigation_id: FullAgenticInvestigationId
    worker_id: str


class ExecuteFullAgenticScientificReturn:
    def __init__(
        self,
        scientific_repository: ScientificReturnRepository,
        repository: FullAgenticRepository,
        reasoner: FullAgenticReasoner,
        sources: tuple[BibliographicSource, ...],
        unit_of_work: FullAgenticUnitOfWork,
        clock: FullAgenticClock,
        configuration: FullAgenticConfiguration,
    ) -> None:
        self._scientific_repository = scientific_repository
        self._repository = repository
        self._reasoner = reasoner
        self._sources = {source.name.upper(): source for source in sources}
        self._uow = unit_of_work
        self._clock = clock
        self._configuration = configuration

    async def execute(self, data: ExecuteFullAgenticInput) -> FullAgenticInvestigation:
        investigation = await self._repository.get_investigation(data.investigation_id)
        if investigation is None:
            raise LookupError(f"Investigation {data.investigation_id} not found")
        if investigation.status.is_terminal:
            return investigation
        now = self._clock.now()
        investigation = await self._repository.claim_investigation(
            data.investigation_id,
            data.worker_id,
            now,
            now + timedelta(seconds=self._configuration.investigation_lease_seconds),
        )
        await self._uow.commit()
        if investigation is None:
            current = await self._repository.get_investigation(data.investigation_id)
            if current is None:
                raise LookupError(f"Investigation {data.investigation_id} not found")
            return current
        if investigation.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED:
            investigation.cancel(now)
            await self._repository.save_investigation(investigation)
            await self._uow.commit()
            return investigation
        try:
            await self._run(investigation)
        except _InvestigationLeaseLost:
            await self._uow.rollback()
            current = await self._repository.get_investigation(investigation.id)
            if current is None:
                raise LookupError(
                    f"Investigation {investigation.id} not found"
                ) from None
            if current.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED:
                current.cancel(self._clock.now())
                try:
                    await self._repository.save_investigation(current)
                    await self._uow.commit()
                except InvestigationConcurrencyConflict:
                    await self._uow.rollback()
                    latest = await self._repository.get_investigation(investigation.id)
                    if latest is not None:
                        return latest
            return current
        except Exception as exc:
            await self._uow.rollback()
            current = await self._repository.get_investigation(investigation.id)
            if current is not None and not current.status.is_terminal:
                if current.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED:
                    current.cancel(self._clock.now())
                else:
                    current.fail(f"{type(exc).__name__}: {exc}", self._clock.now())
                try:
                    await self._repository.save_investigation(current)
                    await self._append_event(
                        current,
                        AgenticTrajectoryEventKind.ERROR,
                        {"message": str(exc)[:2000]},
                    )
                    await self._uow.commit()
                    return current
                except InvestigationConcurrencyConflict:
                    await self._uow.rollback()
                    latest = await self._repository.get_investigation(investigation.id)
                    if latest is not None:
                        return latest
            raise
        return investigation

    async def _run(self, investigation: FullAgenticInvestigation) -> None:
        snapshot = await self._scientific_repository.get_snapshot_for_watch(
            investigation.watch_id
        )
        if snapshot is None:
            raise RuntimeError("Watch snapshot is missing")
        inventories = tuple(
            item.inventory_number for item in snapshot.payload.consulted_objects
        )
        memory = await retrieve_relevant_knowledge(
            self._repository,
            inventories,
            limit=self._configuration.memory_limit,
        )
        existing_events = await self._repository.list_events(investigation.id)
        if not any(
            event.kind is AgenticTrajectoryEventKind.MEMORY_RETRIEVED
            for event in existing_events
        ):
            for item in memory:
                await self._repository.add_knowledge_usage(
                    str(investigation.id), str(item.id), "PLANNER", self._clock.now()
                )
            await self._append_event(
                investigation,
                AgenticTrajectoryEventKind.MEMORY_RETRIEVED,
                {"knowledgeItemIds": [str(item.id) for item in memory]},
            )
        if investigation.search_run_id is not None:
            existing_run = await self._scientific_repository.get_run(
                investigation.search_run_id
            )
            if existing_run is None:
                raise RuntimeError("Full-agentic envelope run is missing")
            run = existing_run
        else:
            run = ScientificReturnSearchRun(
                id=ScientificReturnRunId(str(uuid4())),
                watch_id=investigation.watch_id,
                status=RunStatus.RUNNING,
                started_at=self._clock.now(),
                run_kind=RunKind.FULL_AGENTIC,
            )
            await self._scientific_repository.add_run(run)
            investigation.search_run_id = run.id
            await self._repository.save_investigation(investigation)
            await self._uow.commit()

        history: list[dict[str, object]] = [
            event.payload
            for event in existing_events
            if event.kind is AgenticTrajectoryEventKind.PLAN_CREATED
        ]
        observation: dict[str, object] = {
            "projectReference": snapshot.payload.project_reference,
            "researcher": snapshot.payload.researcher,
            "objects": [
                {
                    "id": item.id,
                    "inventoryNumber": item.inventory_number,
                    "objectName": item.object_name,
                }
                for item in snapshot.payload.consulted_objects
            ],
        }
        seen_records: set[str] = {
            f"{event.payload.get('source')}|{event.payload.get('sourceRecordId')}"
            for event in existing_events
            if event.kind is AgenticTrajectoryEventKind.ARTICLE_ASSESSED
            or (
                event.kind is AgenticTrajectoryEventKind.ERROR
                and event.payload.get("phase") == "ARTICLE_ASSESSMENT"
            )
        }
        executed_sources: set[str] = set()
        new_candidate_count = sum(
            1
            for event in existing_events
            if event.kind is AgenticTrajectoryEventKind.CANDIDATE_LINKED
            and event.payload.get("relationKind")
            == AgenticCandidateRelationKind.CREATED.value
        )

        for iteration in range(1, investigation.budget.max_iterations + 1):
            fresh = await self._repository.get_investigation(investigation.id)
            if (
                fresh
                and fresh.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED
            ):
                investigation.status = fresh.status
                investigation.cancel(self._clock.now())
                break
            remaining_queries = (
                investigation.budget.max_queries - investigation.usage.queries
            )
            remaining_llm = (
                investigation.budget.max_llm_calls - investigation.usage.llm_calls
            )
            if remaining_queries <= 0 or remaining_llm <= 0:
                break
            persisted_plan = next(
                (
                    event
                    for event in existing_events
                    if event.kind is AgenticTrajectoryEventKind.PLAN_CREATED
                    and event.payload.get("iteration") == iteration
                ),
                None,
            )
            if persisted_plan is not None:
                persisted_payload = persisted_plan.payload
                plan = AgenticPlan(
                    queries=_string_tuple(persisted_payload, "queries"),
                    sources=_string_tuple(persisted_payload, "sources"),
                    reasoning=str(persisted_payload.get("reasoning", "")),
                    should_stop=bool(persisted_payload.get("shouldStop", False)),
                )
            else:
                await self._renew_lease(investigation)
                plan = await self._reasoner.plan(
                    observation=observation,
                    memory=tuple(item.as_prompt_example() for item in memory),
                    history=tuple(history),
                    allowed_sources=tuple(self._sources),
                    remaining_queries=remaining_queries,
                )
                investigation.usage = replace(
                    investigation.usage,
                    iterations=iteration,
                    llm_calls=investigation.usage.llm_calls + 1,
                )
                await self._append_event(
                    investigation,
                    AgenticTrajectoryEventKind.PLAN_CREATED,
                    {
                        "iteration": iteration,
                        "queries": list(plan.queries),
                        "sources": list(plan.sources),
                        "reasoning": plan.reasoning,
                        "shouldStop": plan.should_stop,
                    },
                )
            if plan.should_stop:
                break
            records = await self._execute_searches(
                investigation,
                run,
                iteration,
                plan.queries,
                plan.sources,
                executed_sources,
            )
            relevant_count = 0
            for record, query in records:
                key = f"{record.source}|{record.source_record_id}"
                if key in seen_records:
                    continue
                seen_records.add(key)
                if investigation.usage.llm_calls >= investigation.budget.max_llm_calls:
                    break
                await self._renew_lease(investigation)
                investigation.usage = replace(
                    investigation.usage,
                    llm_calls=investigation.usage.llm_calls + 1,
                )
                try:
                    assessment = await self._reasoner.assess(
                        record=record,
                        trusted_context={
                            **observation,
                            "query": query,
                            "curatorialMemory": [
                                item.as_prompt_example() for item in memory
                            ],
                        },
                    )
                except Exception as exc:
                    await self._append_event(
                        investigation,
                        AgenticTrajectoryEventKind.ERROR,
                        {
                            "phase": "ARTICLE_ASSESSMENT",
                            "source": record.source,
                            "sourceRecordId": record.source_record_id,
                            "message": f"{type(exc).__name__}: {exc}"[:2000],
                        },
                    )
                    await self._repository.save_investigation(investigation)
                    await self._uow.commit()
                    continue
                await self._append_event(
                    investigation,
                    AgenticTrajectoryEventKind.ARTICLE_ASSESSED,
                    {
                        "source": record.source,
                        "sourceRecordId": record.source_record_id,
                        "relevant": assessment.relevant,
                        "confidence": assessment.confidence.value,
                        "explanation": assessment.explanation,
                        "passages": list(assessment.passages),
                        "inventoryForms": list(assessment.inventory_forms),
                        "contradictions": list(assessment.contradictions),
                        "query": query,
                    },
                )
                if assessment.relevant:
                    relevant_count += 1
                    created = await self._present_candidate(
                        investigation,
                        run,
                        record,
                        assessment,
                        query,
                        tuple(str(item.id) for item in memory),
                    )
                    new_candidate_count += int(created)
                if (
                    investigation.usage.candidates
                    >= investigation.budget.max_candidates
                ):
                    break
            history.append(
                {
                    "iteration": iteration,
                    "queries": list(plan.queries),
                    "sources": list(plan.sources),
                    "resultCount": len(records),
                    "relevantCount": relevant_count,
                }
            )
            fresh = await self._repository.get_investigation(investigation.id)
            if (
                fresh
                and fresh.status is FullAgenticInvestigationStatus.CANCEL_REQUESTED
            ):
                investigation.status = fresh.status
                investigation.cancel(self._clock.now())
                break
            investigation.heartbeat(self._clock.now())
            await self._repository.save_investigation(investigation)
            await self._uow.commit()
            if investigation.usage.candidates >= investigation.budget.max_candidates:
                break

        if investigation.status is FullAgenticInvestigationStatus.RUNNING:
            investigation.complete(self._clock.now())
        run.status = RunStatus.COMPLETED
        run.completed_at = self._clock.now()
        run.source_count = len(executed_sources)
        run.candidate_count = investigation.usage.candidates
        run.new_candidate_count = new_candidate_count
        await self._scientific_repository.save_run(run)
        await self._repository.save_investigation(investigation)
        await self._append_event(
            investigation,
            AgenticTrajectoryEventKind.STOPPED,
            {"status": investigation.status.value},
        )
        await self._uow.commit()

    async def _execute_searches(
        self,
        investigation: FullAgenticInvestigation,
        run: ScientificReturnSearchRun,
        iteration: int,
        queries: tuple[str, ...],
        sources: tuple[str, ...],
        executed_sources: set[str],
    ) -> list[tuple[BibliographicRecord, str]]:
        invocation: dict[str, object] = {
            "contractVersion": "authorless-search-v2",
            "queries": list(queries),
            "sources": list(sources),
        }
        sequence = iteration
        key = normalized_tool_idempotency_key(
            str(investigation.id), sequence, invocation
        )
        prior = await self._repository.get_tool_execution(key)
        if prior and prior.status is AgenticToolExecutionStatus.COMPLETED:
            replayed = self._records_from_result(prior.result or {})
            executed_sources.update(record.source.upper() for record, _ in replayed)
            return replayed
        if prior is not None:
            execution = prior
            execution.status = AgenticToolExecutionStatus.RUNNING
            execution.attempts += 1
            execution.lease_expires_at = self._clock.now() + timedelta(
                seconds=self._configuration.tool_lease_seconds
            )
            await self._repository.save_tool_execution(execution)
        else:
            execution = AgenticToolExecution(
                id=AgenticToolExecutionId(str(uuid4())),
                investigation_id=investigation.id,
                trajectory_sequence=sequence,
                idempotency_key=key,
                status=AgenticToolExecutionStatus.RUNNING,
                invocation=invocation,
                started_at=self._clock.now(),
                lease_expires_at=self._clock.now()
                + timedelta(seconds=self._configuration.tool_lease_seconds),
            )
            await self._repository.add_tool_execution(execution)
        await self._uow.commit()
        found: list[tuple[BibliographicRecord, str]] = []
        for source_name in sources:
            source = self._sources.get(source_name.upper())
            if source is None:
                continue
            executed_sources.add(source.name.upper())
            for query in queries:
                if investigation.usage.queries >= investigation.budget.max_queries:
                    break
                sent_at = self._clock.now()
                error: str | None = None
                try:
                    await self._renew_lease(investigation)
                    records = await source.search(
                        query,
                        min(20, investigation.budget.max_results),
                        author=None,
                    )
                except _InvestigationLeaseLost:
                    raise
                except Exception as exc:
                    records = []
                    error = f"{type(exc).__name__}: {exc}"[:500]
                await self._scientific_repository.add_query(
                    ScientificReturnQuery(
                        id=ScientificReturnQueryId(str(uuid4())),
                        run_id=run.id,
                        source=source_name,
                        query_text=query,
                        query_type=QueryType.AGENTIC,
                        sent_at=sent_at,
                        result_count=len(records),
                        status=QueryStatus.FAILED if error else QueryStatus.COMPLETED,
                        error_message=error,
                    )
                )
                remaining = (
                    investigation.budget.max_results - investigation.usage.results
                )
                accepted = records[: max(0, remaining)]
                found.extend((record, query) for record in accepted)
                investigation.usage = replace(
                    investigation.usage,
                    queries=investigation.usage.queries + 1,
                    results=investigation.usage.results + len(accepted),
                )
                await self._uow.commit()
                if investigation.usage.results >= investigation.budget.max_results:
                    break
        result: dict[str, object] = {
            "records": [self._record_payload(record, query) for record, query in found]
        }
        execution.status = AgenticToolExecutionStatus.COMPLETED
        execution.result = result
        execution.result_hash = hashlib.sha256(repr(result).encode()).hexdigest()
        execution.completed_at = self._clock.now()
        await self._repository.save_tool_execution(execution)
        await self._append_event(
            investigation,
            AgenticTrajectoryEventKind.TOOL_COMPLETED,
            {"resultCount": len(found), "toolExecutionId": str(execution.id)},
        )
        await self._uow.commit()
        return found

    async def _present_candidate(
        self,
        investigation: FullAgenticInvestigation,
        run: ScientificReturnSearchRun,
        record: BibliographicRecord,
        assessment: object,
        query: str,
        knowledge_ids: tuple[str, ...],
    ) -> bool:
        from app.scientific_return.domain.full_agentic_models import ArticleAssessment

        assert isinstance(assessment, ArticleAssessment)
        key = deduplication_key(record)
        candidate = await self._scientific_repository.get_candidate_by_key(
            investigation.watch_id, key
        )
        relation = AgenticCandidateRelationKind.REDISCOVERED
        if candidate is None:
            relation = AgenticCandidateRelationKind.CREATED
            candidate = CandidatePublication(
                id=CandidatePublicationId(str(uuid4())),
                watch_id=investigation.watch_id,
                first_seen_run_id=run.id,
                source=record.source,
                source_record_id=record.source_record_id,
                deduplication_key=key,
                doi=record.doi,
                title=record.title,
                authors=record.authors,
                publication_date=record.publication_date,
                abstract=record.abstract,
                url=record.url,
                raw_metadata_hash=record.raw_metadata_hash,
                status=CandidateStatus.PENDING,
                created_at=self._clock.now(),
            )
            await self._scientific_repository.add_candidate(candidate)
        linked = await self._repository.link_candidate(
            AgenticCandidateLink(
                investigation_id=investigation.id,
                candidate_id=candidate.id,
                relation_kind=relation,
                rank=investigation.usage.candidates + 1,
                linked_at=self._clock.now(),
            )
        )
        analysis = CandidateAgentAnalysis(
            id=CandidateAgentAnalysisId(str(uuid4())),
            candidate_id=candidate.id,
            run_id=run.id,
            status=AgentAnalysisStatus.RUNNING,
            model=self._reasoner.model_name,
            prompt_version_id="scientific_return_full_agentic_reader",
            prompt_version="scientific-return-full-agentic-reader-v1",
            input_payload={
                "query": query,
                "source": record.source,
                "passages": list(assessment.passages),
                "inventoryForms": list(assessment.inventory_forms),
                "knowledgeItemIds": list(knowledge_ids),
            },
            input_hash=hashlib.sha256(
                f"{record.source}|{record.source_record_id}|{query}".encode()
            ).hexdigest(),
            started_at=self._clock.now(),
            created_by=investigation.created_by,
        )
        analysis.complete(
            CandidateAnalysisResult(
                summary=assessment.explanation,
                supporting_evidence=assessment.passages,
                contradictions=assessment.contradictions,
                missing_evidence=(),
                recommended_action=AgentRecommendedAction.PRESENT_FOR_REVIEW,
                proposed_queries=(),
                reasoning_summary=assessment.explanation,
                confidence=assessment.confidence,
            ),
            response_hash=hashlib.sha256(assessment.explanation.encode()).hexdigest(),
            completed_at=self._clock.now(),
        )
        await self._scientific_repository.add_agent_analysis(analysis)
        if linked:
            investigation.usage = replace(
                investigation.usage,
                candidates=investigation.usage.candidates + 1,
            )
            await self._append_event(
                investigation,
                AgenticTrajectoryEventKind.CANDIDATE_LINKED,
                {
                    "candidateId": str(candidate.id),
                    "relationKind": relation.value,
                    "analysisId": str(analysis.id),
                },
            )
        return linked and relation is AgenticCandidateRelationKind.CREATED

    async def _renew_lease(self, investigation: FullAgenticInvestigation) -> None:
        now = self._clock.now()
        investigation.lease_expires_at = now + timedelta(
            seconds=self._configuration.investigation_lease_seconds
        )
        next_version = await self._repository.renew_investigation_lease(
            investigation.id,
            investigation.lease_owner or "unknown-worker",
            now,
            investigation.lease_expires_at,
        )
        if next_version is None:
            raise _InvestigationLeaseLost(
                f"Worker lost the lease for investigation {investigation.id}"
            )
        investigation.version = next_version
        await self._uow.commit()

    async def _append_event(
        self,
        investigation: FullAgenticInvestigation,
        kind: AgenticTrajectoryEventKind,
        payload: dict[str, object],
    ) -> None:
        sequence = await self._repository.next_event_sequence(investigation.id)
        await self._repository.append_event(
            AgenticTrajectoryEvent(
                id=AgenticTrajectoryEventId(str(uuid4())),
                investigation_id=investigation.id,
                sequence=sequence,
                kind=kind,
                payload=payload,
                occurred_at=self._clock.now(),
            )
        )

    @staticmethod
    def _record_payload(record: BibliographicRecord, query: str) -> dict[str, object]:
        return {
            "query": query,
            "source": record.source,
            "source_record_id": record.source_record_id,
            "title": record.title,
            "authors": list(record.authors),
            "publication_date": record.publication_date,
            "abstract": record.abstract,
            "url": record.url,
            "doi": record.doi,
            "raw_metadata_hash": record.raw_metadata_hash,
            "indexed_text_hash": (
                hashlib.sha256(record.indexed_text.encode()).hexdigest()
                if record.indexed_text
                else None
            ),
            "indexed_text_source": record.indexed_text_source,
        }

    @staticmethod
    def _records_from_result(
        result: dict[str, object],
    ) -> list[tuple[BibliographicRecord, str]]:
        raw = result.get("records")
        if not isinstance(raw, list):
            return []
        output: list[tuple[BibliographicRecord, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            output.append(
                (
                    BibliographicRecord(
                        source=str(item["source"]),
                        source_record_id=str(item["source_record_id"]),
                        title=str(item["title"]),
                        authors=tuple(str(value) for value in item.get("authors", [])),
                        publication_date=str(item["publication_date"])
                        if item.get("publication_date")
                        else None,
                        abstract=str(item["abstract"])
                        if item.get("abstract")
                        else None,
                        url=str(item["url"]) if item.get("url") else None,
                        doi=str(item["doi"]) if item.get("doi") else None,
                        raw_metadata_hash=str(item["raw_metadata_hash"]),
                        indexed_text=None,
                        indexed_text_source=str(item["indexed_text_source"])
                        if item.get("indexed_text_source")
                        else None,
                    ),
                    str(item["query"]),
                )
            )
        return output


class GetFullAgenticInvestigation:
    def __init__(self, repository: FullAgenticRepository) -> None:
        self._repository = repository

    async def execute(
        self, investigation_id: FullAgenticInvestigationId, caller: Actor
    ) -> FullAgenticInvestigation:
        require_staff(caller)
        item = await self._repository.get_investigation(investigation_id)
        if item is None:
            raise LookupError(f"Investigation {investigation_id} not found")
        return item


class CancelFullAgenticInvestigation:
    def __init__(
        self,
        repository: FullAgenticRepository,
        unit_of_work: FullAgenticUnitOfWork,
        clock: FullAgenticClock,
    ) -> None:
        self._repository = repository
        self._uow = unit_of_work
        self._clock = clock

    async def execute(
        self, investigation_id: FullAgenticInvestigationId, caller: Actor
    ) -> FullAgenticInvestigation:
        require_group(caller, *_MUTATION_GROUPS)
        item = await self._repository.get_investigation(investigation_id)
        if item is None:
            raise LookupError(f"Investigation {investigation_id} not found")
        item.request_cancel(caller.id, self._clock.now())
        await self._repository.save_investigation(item)
        await self._uow.commit()
        return item
