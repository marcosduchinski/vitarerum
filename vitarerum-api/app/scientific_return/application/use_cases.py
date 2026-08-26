from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from app.identity.public import Actor, GroupName
from app.scientific_return.application.analysis import (
    PlannedQuery,
    build_evidences,
    deduplication_key,
    is_actionable,
    plan_adaptive_queries,
    plan_queries,
)
from app.scientific_return.application.ports import (
    FULL_AGENTIC_READER_PROMPT_ID_PREFIX,
    BibliographicSource,
    ConfirmedPublicationWriter,
    ProjectSnapshotProvider,
    ScientificReturnRepository,
)
from app.scientific_return.domain.enums import (
    CandidateStatus,
    DecisionType,
    EvidenceSourceField,
    InventoryEvidenceStatus,
    QueryStatus,
    RunStatus,
    WatchStatus,
)
from app.scientific_return.domain.full_agentic_models import (
    CandidateDecisionContext,
    GroundedInventoryForm,
    KnowledgeItemId,
)
from app.scientific_return.domain.models import (
    CandidateCorrection,
    CandidateDecision,
    CandidateDecisionId,
    CandidatePublication,
    CandidatePublicationId,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnQuery,
    ScientificReturnQueryId,
    ScientificReturnRunId,
    ScientificReturnSearchRun,
    ScientificReturnSnapshotId,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)
from app.shared.authorization import require_group

_REVIEW_GROUPS = (
    GroupName.CURATORIAL,
    GroupName.COLLECTIONS_MANAGEMENT,
    GroupName.DIRECTION,
)
_SNAPSHOT_BUILDER_VERSION = "scientific-return-snapshot-v1"


class WatchNotFound(LookupError):
    pass


class CandidateNotFound(LookupError):
    pass


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _new_id() -> str:
    return str(uuid4())


def _snapshot_hash(payload: ProjectSnapshotPayload) -> str:
    serialized = json.dumps(asdict(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ActivateWatchInput:
    project_id: str
    review_interval_days: int
    caller: Actor
    schedule_anchor_at: datetime | None = None


class ActivateScientificReturnWatch:
    def __init__(
        self,
        repository: ScientificReturnRepository,
        project_provider: ProjectSnapshotProvider,
    ) -> None:
        self._repository = repository
        self._project_provider = project_provider

    async def execute(self, data: ActivateWatchInput) -> ScientificReturnWatch:
        require_group(data.caller, *_REVIEW_GROUPS)
        existing = await self._repository.get_watch_by_project(data.project_id)
        if existing is not None:
            return existing
        payload = await self._project_provider.get_completed_project(data.project_id)
        if payload is None:
            raise LookupError("Completed project not found")
        if not payload.researcher.strip():
            raise ValueError("The project researcher name is required")
        if not payload.consulted_objects:
            raise ValueError("The project must contain at least one consulted object")
        for obj in payload.consulted_objects:
            if not obj.inventory_number.strip() or not obj.object_name.strip():
                raise ValueError(
                    "Every consulted object needs an inventory number and object name"
                )

        now = _now()
        # An anchor the curator did not choose is simply now, which reproduces
        # the previous behaviour: the first review is owed immediately.
        anchor = data.schedule_anchor_at or now
        snapshot = ScientificReturnProjectSnapshot(
            id=ScientificReturnSnapshotId(_new_id()),
            project_id=data.project_id,
            payload=payload,
            payload_hash=_snapshot_hash(payload),
            builder_version=_SNAPSHOT_BUILDER_VERSION,
            created_at=now,
        )
        watch = ScientificReturnWatch(
            id=ScientificReturnWatchId(_new_id()),
            project_id=data.project_id,
            status=WatchStatus.ACTIVE,
            review_interval_days=data.review_interval_days,
            created_by=data.caller.id,
            created_at=now,
            next_run_at=anchor,
            project_snapshot_id=snapshot.id,
            schedule_anchor_at=anchor,
        )
        await self._repository.add_snapshot(snapshot)
        await self._repository.add_watch(watch)
        return watch


class ChangeWatchStatus:
    def __init__(self, repository: ScientificReturnRepository) -> None:
        self._repository = repository

    async def execute(
        self, watch_id: ScientificReturnWatchId, status: WatchStatus, caller: Actor
    ) -> ScientificReturnWatch:
        require_group(caller, *_REVIEW_GROUPS)
        watch = await self._repository.get_watch(watch_id)
        if watch is None:
            raise WatchNotFound(f"Scientific-return watch {watch_id} not found")
        watch.change_status(status)
        await self._repository.save_watch(watch)
        return watch


class ChangeWatchReviewInterval:
    """Re-cadence an existing watch. The aggregate owns what the new date is."""

    def __init__(self, repository: ScientificReturnRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        watch_id: ScientificReturnWatchId,
        review_interval_days: int,
        caller: Actor,
    ) -> ScientificReturnWatch:
        require_group(caller, *_REVIEW_GROUPS)
        watch = await self._repository.get_watch(watch_id)
        if watch is None:
            raise WatchNotFound(f"Scientific-return watch {watch_id} not found")
        watch.change_review_interval(review_interval_days)
        await self._repository.save_watch(watch)
        return watch


class ChangeWatchScheduleAnchor:
    """Move the date the review series is measured from. The aggregate owns it."""

    def __init__(self, repository: ScientificReturnRepository) -> None:
        self._repository = repository

    async def execute(
        self,
        watch_id: ScientificReturnWatchId,
        schedule_anchor_at: datetime,
        caller: Actor,
    ) -> ScientificReturnWatch:
        require_group(caller, *_REVIEW_GROUPS)
        watch = await self._repository.get_watch(watch_id)
        if watch is None:
            raise WatchNotFound(f"Scientific-return watch {watch_id} not found")
        watch.change_schedule_anchor(schedule_anchor_at)
        await self._repository.save_watch(watch)
        return watch


class RunScientificReturnSearch:
    def __init__(
        self,
        repository: ScientificReturnRepository,
        sources: tuple[BibliographicSource, ...],
        result_limit: int = 20,
        max_queries: int = 40,
    ) -> None:
        self._repository = repository
        self._sources = sources
        self._result_limit = result_limit
        self._max_queries = max_queries

    async def execute(
        self, watch_id: ScientificReturnWatchId, caller: Actor
    ) -> ScientificReturnSearchRun:
        require_group(caller, *_REVIEW_GROUPS)
        return await self.execute_scheduled(watch_id)

    async def execute_scheduled(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnSearchRun:
        watch = await self._repository.get_watch(watch_id)
        if watch is None:
            raise WatchNotFound(f"Scientific-return watch {watch_id} not found")
        if watch.status is not WatchStatus.ACTIVE:
            raise ValueError("Only an active watch can be searched")
        snapshot = await self._repository.get_snapshot_for_watch(watch_id)
        if snapshot is None:
            raise RuntimeError("Scientific-return snapshot is missing")

        started_at = _now()
        run = ScientificReturnSearchRun(
            id=ScientificReturnRunId(_new_id()),
            watch_id=watch.id,
            status=RunStatus.RUNNING,
            started_at=started_at,
        )
        await self._repository.add_run(run)
        candidate_ids: set[CandidatePublicationId] = set()
        new_candidate_ids: set[CandidatePublicationId] = set()
        errors: list[str] = []
        query_count = 0
        queried_sources: set[str] = set()

        planned_queries = plan_queries(snapshot.payload)
        for source in self._sources:
            remaining_run_budget = self._max_queries - query_count
            if remaining_run_budget <= 0:
                break
            source_candidate_count = len(candidate_ids)
            source_queries = list(planned_queries[:remaining_run_budget])
            initial_query_count = len(source_queries)

            def add_adaptive_queries(
                index: int,
                initial_count: int,
                candidate_count_before: int,
                used_query_count: int,
                queries: list[PlannedQuery],
            ) -> None:
                if (
                    index + 1 != initial_count
                    or len(candidate_ids) != candidate_count_before
                ):
                    return
                remaining = self._max_queries - used_query_count
                if remaining > 0:
                    queries.extend(plan_adaptive_queries(snapshot.payload)[:remaining])

            for index, planned in enumerate(source_queries):
                query_count += 1
                queried_sources.add(source.name)
                sent_at = _now()
                try:
                    records = await source.search(
                        planned.text, self._result_limit, author=planned.author
                    )
                    await self._repository.add_query(
                        ScientificReturnQuery(
                            id=ScientificReturnQueryId(_new_id()),
                            run_id=run.id,
                            source=source.name,
                            query_text=planned.text,
                            query_type=planned.query_type,
                            sent_at=sent_at,
                            result_count=len(records),
                            status=QueryStatus.COMPLETED,
                        )
                    )
                except Exception as exc:
                    message = f"{type(exc).__name__}: {exc}"[:500]
                    errors.append(f"{source.name}: {message}")
                    await self._repository.add_query(
                        ScientificReturnQuery(
                            id=ScientificReturnQueryId(_new_id()),
                            run_id=run.id,
                            source=source.name,
                            query_text=planned.text,
                            query_type=planned.query_type,
                            sent_at=sent_at,
                            result_count=0,
                            status=QueryStatus.FAILED,
                            error_message=message,
                        )
                    )
                    add_adaptive_queries(
                        index,
                        initial_query_count,
                        source_candidate_count,
                        query_count,
                        source_queries,
                    )
                    continue

                for record in records:
                    key = deduplication_key(record)
                    existing = await self._repository.get_candidate_by_key(
                        watch.id, key
                    )
                    if existing is not None:
                        candidate_ids.add(existing.id)
                        continue
                    candidate_id = CandidatePublicationId(_new_id())
                    evidences = build_evidences(
                        candidate_id, snapshot.payload, record, started_at
                    )
                    if not is_actionable(evidences):
                        continue
                    candidate = CandidatePublication(
                        id=candidate_id,
                        watch_id=watch.id,
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
                        created_at=started_at,
                        evidences=evidences,
                    )
                    await self._repository.add_candidate(candidate)
                    candidate_ids.add(candidate.id)
                    new_candidate_ids.add(candidate.id)

                add_adaptive_queries(
                    index,
                    initial_query_count,
                    source_candidate_count,
                    query_count,
                    source_queries,
                )

        completed_at = _now()
        run.completed_at = completed_at
        run.source_count = len(queried_sources)
        run.candidate_count = len(candidate_ids)
        run.new_candidate_count = len(new_candidate_ids)
        if errors and len(errors) == query_count:
            run.status = RunStatus.FAILED
            run.error_message = "; ".join(errors)[:2000]
        else:
            run.status = RunStatus.COMPLETED
            run.error_message = "; ".join(errors)[:2000] or None
        watch.record_run(completed_at)
        await self._repository.save_run(run)
        await self._repository.save_watch(watch)
        return run


@dataclass(frozen=True, slots=True)
class DecideCandidateInput:
    candidate_id: CandidatePublicationId
    decision: DecisionType
    caller: Actor
    justification: str | None = None
    correction: CandidateCorrection | None = None


class DecideCandidate:
    def __init__(
        self,
        repository: ScientificReturnRepository,
        publication_writer: ConfirmedPublicationWriter,
    ) -> None:
        self._repository = repository
        self._publication_writer = publication_writer

    async def execute(self, data: DecideCandidateInput) -> CandidatePublication:
        require_group(data.caller, *_REVIEW_GROUPS)
        candidate = await self._repository.get_candidate(data.candidate_id)
        if candidate is None:
            raise CandidateNotFound(f"Candidate {data.candidate_id} not found")
        if candidate.status in {
            CandidateStatus.CONFIRMED,
            CandidateStatus.DISMISSED,
        }:
            raise ValueError("A final candidate decision has already been recorded")
        now = _now()
        correction = data.correction
        if data.decision is DecisionType.DISMISS:
            if not data.justification or not data.justification.strip():
                raise ValueError(
                    "justification is required when dismissing a candidate"
                )
            candidate.dismiss()
        elif data.decision is DecisionType.CORRECT_AND_CONFIRM:
            if correction is None:
                raise ValueError("correction is required when correcting a candidate")
            candidate = replace(
                candidate,
                title=correction.title or candidate.title,
                doi=correction.doi if correction.doi is not None else candidate.doi,
                url=correction.url if correction.url is not None else candidate.url,
                authors=(
                    correction.authors
                    if correction.authors is not None
                    else candidate.authors
                ),
            )
            entry_id = await self._publication_writer.add_confirmed_publication(
                project_id=(await self._project_id(candidate)),
                caller=data.caller,
                candidate=candidate,
            )
            candidate.confirm(entry_id)
        elif data.decision is DecisionType.CONFIRM:
            entry_id = await self._publication_writer.add_confirmed_publication(
                project_id=(await self._project_id(candidate)),
                caller=data.caller,
                candidate=candidate,
            )
            candidate.confirm(entry_id)

        decision = CandidateDecision(
            id=CandidateDecisionId(_new_id()),
            candidate_id=candidate.id,
            decision=data.decision,
            justification=data.justification.strip() if data.justification else None,
            decided_by=data.caller.id,
            decided_at=now,
            evidence_snapshot=tuple(
                {
                    "type": evidence.type.value,
                    "strength": evidence.strength.value,
                    "value": evidence.value,
                    "sourceField": evidence.source_field,
                    "explanation": evidence.explanation,
                }
                for evidence in candidate.evidences
            ),
            correction=correction,
            decision_context=await self._decision_context(candidate.id),
        )
        await self._repository.save_candidate(candidate)
        await self._repository.add_decision(decision)
        return candidate

    async def _decision_context(
        self, candidate_id: CandidatePublicationId
    ) -> CandidateDecisionContext | None:
        analyses = await self._repository.list_agent_analyses(candidate_id)
        completed = [
            item
            for item in analyses
            if item.result is not None
            and item.prompt_version_id.startswith(FULL_AGENTIC_READER_PROMPT_ID_PREFIX)
        ]
        if not completed:
            return None
        # The repository contract returns analyses newest first.
        analysis = completed[0]
        assert analysis.result is not None

        def strings(key: str) -> tuple[str, ...]:
            value = analysis.input_payload.get(key, [])
            if not isinstance(value, list):
                return ()
            return tuple(str(item) for item in value)

        query = analysis.input_payload.get("query")
        source = analysis.input_payload.get("source")
        raw_grounded_forms = analysis.input_payload.get("groundedInventoryForms")
        grounded_forms: list[GroundedInventoryForm] = []
        if isinstance(raw_grounded_forms, list):
            for item in raw_grounded_forms:
                if not isinstance(item, dict):
                    continue
                observed = item.get("observedForm")
                source_field = item.get("sourceField")
                if not isinstance(observed, str) or not isinstance(source_field, str):
                    continue
                try:
                    grounded_forms.append(
                        GroundedInventoryForm(
                            observed_form=observed,
                            source_field=EvidenceSourceField(source_field),
                            source_locator=(
                                str(item["sourceLocator"])
                                if item.get("sourceLocator")
                                else None
                            ),
                        )
                    )
                except ValueError:
                    continue
        raw_evidence_status = analysis.input_payload.get("inventoryEvidenceStatus")
        evidence_status = None
        if isinstance(raw_evidence_status, str):
            try:
                evidence_status = InventoryEvidenceStatus(raw_evidence_status)
            except ValueError:
                pass
        return CandidateDecisionContext(
            version=2,
            passages=strings("passages"),
            inventory_forms=strings("inventoryForms"),
            queries=(str(query),) if query else (),
            sources=(str(source),) if source else (),
            explanation=analysis.result.reasoning_summary,
            confidence=analysis.result.confidence,
            contradictions=analysis.result.contradictions,
            knowledge_item_ids=tuple(
                KnowledgeItemId(value) for value in strings("knowledgeItemIds")
            ),
            discovery_basis=(
                str(analysis.input_payload["discoveryBasis"])
                if analysis.input_payload.get("discoveryBasis")
                else None
            ),
            search_intent=(
                str(analysis.input_payload["searchIntent"])
                if analysis.input_payload.get("searchIntent")
                else None
            ),
            search_strategy=(
                str(analysis.input_payload["searchStrategy"])
                if analysis.input_payload.get("searchStrategy")
                else None
            ),
            inventory_evidence_status=evidence_status,
            grounded_inventory_forms=tuple(grounded_forms),
        )

    async def _project_id(self, candidate: CandidatePublication) -> str:
        watch = await self._repository.get_watch(candidate.watch_id)
        if watch is None:
            raise RuntimeError("Candidate watch is missing")
        return watch.project_id
