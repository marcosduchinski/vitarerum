from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
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
    BibliographicSource,
    ConfirmedPublicationWriter,
    ProjectSnapshotProvider,
    ScientificReturnRepository,
)
from app.scientific_return.domain.enums import (
    CandidateStatus,
    DecisionType,
    QueryStatus,
    RunStatus,
    WatchStatus,
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
            next_run_at=now,
            project_snapshot_id=snapshot.id,
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
                    records = await source.search(planned.text, self._result_limit)
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
                        existing.make_pending_if_snooze_expired(started_at)
                        await self._repository.save_candidate(existing)
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
        watch.record_run(
            completed_at,
            completed_at + timedelta(days=watch.review_interval_days),
        )
        await self._repository.save_run(run)
        await self._repository.save_watch(watch)
        return run


@dataclass(frozen=True, slots=True)
class DecideCandidateInput:
    candidate_id: CandidatePublicationId
    decision: DecisionType
    caller: Actor
    justification: str | None = None
    snoozed_until: datetime | None = None
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
        elif data.decision is DecisionType.SNOOZE:
            if data.snoozed_until is None:
                raise ValueError("snoozedUntil is required when snoozing a candidate")
            candidate.snooze(data.snoozed_until, now)
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
        )
        await self._repository.save_candidate(candidate)
        await self._repository.add_decision(decision)
        return candidate

    async def _project_id(self, candidate: CandidatePublication) -> str:
        watch = await self._repository.get_watch(candidate.watch_id)
        if watch is None:
            raise RuntimeError("Candidate watch is missing")
        return watch.project_id
