from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, cast

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.scientific_return.application.ports import (
    CandidateReviewItem,
    ScientificReturnMetrics,
)
from app.scientific_return.domain.enums import (
    AgentConfidence,
    AgentRecommendedAction,
    CandidateStatus,
    EvidenceStrength,
    RunStatus,
    WatchStatus,
)
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidateAnalysisResult,
    CandidateCorrection,
    CandidateDecision,
    CandidateDecisionId,
    CandidateEvidence,
    CandidateEvidenceId,
    CandidatePublication,
    CandidatePublicationId,
    ConsultedObjectSnapshot,
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
from app.scientific_return.infrastructure.models import (
    CandidateAgentAnalysisRecord,
    CandidateDecisionRecord,
    CandidateEvidenceRecord,
    CandidatePublicationRecord,
    ScientificReturnQueryRecord,
    ScientificReturnRunRecord,
    ScientificReturnSnapshotRecord,
    ScientificReturnWatchRecord,
)
from app.shared.field_encryption import FieldEncryptor
from app.shared.kernel import PermissionId

_SNAPSHOT_PAYLOAD = "scientific_return_snapshots.payload"
_QUERY_TEXT = "scientific_return_queries.query_text"
_AGENT_INPUT = "scientific_return_agent_analyses.input_payload"
_AGENT_ANALYSIS = "scientific_return_agent_analyses.analysis_payload"


def _payload_to_dict(payload: ProjectSnapshotPayload) -> dict[str, object]:
    return asdict(payload)


def _payload_to_domain(payload: dict[str, object]) -> ProjectSnapshotPayload:
    raw_objects = cast(list[dict[str, object]], payload.get("consulted_objects", []))
    objects = tuple(
        ConsultedObjectSnapshot(
            id=str(item["id"]),
            inventory_number=str(item["inventory_number"]),
            object_name=str(item["object_name"]),
        )
        for item in raw_objects
        if isinstance(item, dict)
    )
    return ProjectSnapshotPayload(
        project_id=str(payload["project_id"]),
        project_reference=str(payload["project_reference"]),
        researcher=str(payload["researcher"]),
        consulted_objects=objects,
    )


def _watch_to_domain(record: ScientificReturnWatchRecord) -> ScientificReturnWatch:
    return ScientificReturnWatch(
        id=ScientificReturnWatchId(record.id),
        project_id=record.project_id,
        status=record.status,
        review_interval_days=record.review_interval_days,
        created_by=PermissionId(record.created_by),
        created_at=record.created_at,
        last_run_at=record.last_run_at,
        next_run_at=record.next_run_at,
        project_snapshot_id=ScientificReturnSnapshotId(record.project_snapshot_id),
    )


def _run_to_domain(record: ScientificReturnRunRecord) -> ScientificReturnSearchRun:
    return ScientificReturnSearchRun(
        id=ScientificReturnRunId(record.id),
        watch_id=ScientificReturnWatchId(record.watch_id),
        status=record.status,
        started_at=record.started_at,
        completed_at=record.completed_at,
        source_count=record.source_count,
        candidate_count=record.candidate_count,
        new_candidate_count=record.new_candidate_count,
        error_message=record.error_message,
    )


def _query_to_domain(
    record: ScientificReturnQueryRecord, encryptor: FieldEncryptor
) -> ScientificReturnQuery:
    return ScientificReturnQuery(
        id=ScientificReturnQueryId(record.id),
        run_id=ScientificReturnRunId(record.run_id),
        source=record.source,
        query_text=encryptor.decrypt_text(record.query_text, _QUERY_TEXT) or "",
        query_type=record.query_type,
        sent_at=record.sent_at,
        result_count=record.result_count,
        status=record.status,
        error_message=record.error_message,
    )


def _evidence_to_domain(record: CandidateEvidenceRecord) -> CandidateEvidence:
    return CandidateEvidence(
        id=CandidateEvidenceId(record.id),
        candidate_id=CandidatePublicationId(record.candidate_id),
        type=record.type,
        strength=record.strength,
        value=record.value,
        source_field=record.source_field,
        explanation=record.explanation,
        created_at=record.created_at,
        object_id=record.object_id,
    )


def _candidate_to_domain(record: CandidatePublicationRecord) -> CandidatePublication:
    return CandidatePublication(
        id=CandidatePublicationId(record.id),
        watch_id=ScientificReturnWatchId(record.watch_id),
        first_seen_run_id=ScientificReturnRunId(record.first_seen_run_id),
        source=record.source,
        source_record_id=record.source_record_id,
        deduplication_key=record.deduplication_key,
        doi=record.doi,
        title=record.title,
        authors=tuple(record.authors),
        publication_date=record.publication_date,
        abstract=record.abstract,
        url=record.url,
        raw_metadata_hash=record.raw_metadata_hash,
        status=record.status,
        snoozed_until=record.snoozed_until,
        confirmed_publication_entry_id=record.confirmed_publication_entry_id,
        created_at=record.created_at,
        evidences=[_evidence_to_domain(item) for item in record.evidences],
    )


def _decision_to_domain(record: CandidateDecisionRecord) -> CandidateDecision:
    correction = (
        CandidateCorrection(
            title=record.correction.get("title"),
            doi=record.correction.get("doi"),
            url=record.correction.get("url"),
            authors=(
                tuple(record.correction["authors"])
                if record.correction.get("authors") is not None
                else None
            ),
        )
        if record.correction is not None
        else None
    )
    return CandidateDecision(
        id=CandidateDecisionId(record.id),
        candidate_id=CandidatePublicationId(record.candidate_id),
        decision=record.decision,
        justification=record.justification,
        decided_by=PermissionId(record.decided_by),
        decided_at=record.decided_at,
        evidence_snapshot=tuple(record.evidence_snapshot),
        correction=correction,
    )


def _analysis_result_to_dict(result: CandidateAnalysisResult) -> dict[str, object]:
    return {
        "summary": result.summary,
        "supporting_evidence": list(result.supporting_evidence),
        "contradictions": list(result.contradictions),
        "missing_evidence": list(result.missing_evidence),
        "recommended_action": result.recommended_action.value,
        "proposed_queries": list(result.proposed_queries),
        "reasoning_summary": result.reasoning_summary,
        "confidence": result.confidence.value,
    }


def _analysis_result_to_domain(payload: dict[str, object]) -> CandidateAnalysisResult:
    def strings(key: str) -> tuple[str, ...]:
        value = payload.get(key, [])
        return tuple(str(item) for item in value) if isinstance(value, list) else ()

    return CandidateAnalysisResult(
        summary=str(payload["summary"]),
        supporting_evidence=strings("supporting_evidence"),
        contradictions=strings("contradictions"),
        missing_evidence=strings("missing_evidence"),
        recommended_action=AgentRecommendedAction(
            str(payload["recommended_action"])
        ),
        proposed_queries=strings("proposed_queries"),
        reasoning_summary=str(payload["reasoning_summary"]),
        confidence=AgentConfidence(str(payload["confidence"])),
    )


def _agent_analysis_to_domain(
    record: CandidateAgentAnalysisRecord, encryptor: FieldEncryptor
) -> CandidateAgentAnalysis:
    raw_result = encryptor.decrypt_json(record.analysis_payload, _AGENT_ANALYSIS)
    raw_input = encryptor.decrypt_json(record.input_payload, _AGENT_INPUT)
    return CandidateAgentAnalysis(
        id=CandidateAgentAnalysisId(record.id),
        candidate_id=CandidatePublicationId(record.candidate_id),
        run_id=ScientificReturnRunId(record.run_id),
        status=record.status,
        model=record.model,
        prompt_version_id=record.prompt_version_id,
        prompt_version=record.prompt_version,
        input_payload=cast(dict[str, object], raw_input),
        input_hash=record.input_hash,
        result=(
            _analysis_result_to_domain(cast(dict[str, object], raw_result))
            if raw_result is not None
            else None
        ),
        response_hash=record.response_hash,
        started_at=record.started_at,
        completed_at=record.completed_at,
        latency_ms=record.latency_ms,
        error_message=record.error_message,
        created_by=PermissionId(record.created_by),
        staff_feedback=record.staff_feedback,
        feedback_comment=record.feedback_comment,
        feedback_by=(
            PermissionId(record.feedback_by) if record.feedback_by is not None else None
        ),
        feedback_at=record.feedback_at,
    )


class SqlAlchemyScientificReturnRepository:
    def __init__(self, session: AsyncSession, encryptor: FieldEncryptor) -> None:
        self._session = session
        self._encryptor = encryptor

    async def add_watch(self, watch: ScientificReturnWatch) -> None:
        self._session.add(
            ScientificReturnWatchRecord(
                id=watch.id,
                project_id=watch.project_id,
                status=watch.status,
                review_interval_days=watch.review_interval_days,
                created_by=watch.created_by,
                created_at=watch.created_at,
                last_run_at=watch.last_run_at,
                next_run_at=watch.next_run_at,
                project_snapshot_id=watch.project_snapshot_id,
            )
        )
        await self._session.flush()

    async def save_watch(self, watch: ScientificReturnWatch) -> None:
        record = await self._session.get(ScientificReturnWatchRecord, watch.id)
        if record is None:
            raise LookupError(f"Scientific-return watch {watch.id} not found")
        record.status = watch.status
        record.review_interval_days = watch.review_interval_days
        record.last_run_at = watch.last_run_at
        record.next_run_at = watch.next_run_at
        await self._session.flush()

    async def get_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnWatch | None:
        record = await self._session.get(ScientificReturnWatchRecord, watch_id)
        return _watch_to_domain(record) if record is not None else None

    async def get_watch_by_project(
        self, project_id: str
    ) -> ScientificReturnWatch | None:
        result = await self._session.execute(
            select(ScientificReturnWatchRecord).where(
                ScientificReturnWatchRecord.project_id == project_id
            )
        )
        record = result.scalar_one_or_none()
        return _watch_to_domain(record) if record is not None else None

    async def list_due_watches(
        self, now: datetime, limit: int
    ) -> list[ScientificReturnWatch]:
        result = await self._session.execute(
            select(ScientificReturnWatchRecord)
            .where(
                ScientificReturnWatchRecord.status == WatchStatus.ACTIVE,
                ScientificReturnWatchRecord.next_run_at <= now,
            )
            .order_by(ScientificReturnWatchRecord.next_run_at)
            .limit(limit)
        )
        return [_watch_to_domain(item) for item in result.scalars().all()]

    async def add_snapshot(self, snapshot: ScientificReturnProjectSnapshot) -> None:
        self._session.add(
            ScientificReturnSnapshotRecord(
                id=snapshot.id,
                project_id=snapshot.project_id,
                payload=self._encryptor.encrypt_json(
                    _payload_to_dict(snapshot.payload), _SNAPSHOT_PAYLOAD
                )
                or "",
                payload_hash=snapshot.payload_hash,
                builder_version=snapshot.builder_version,
                created_at=snapshot.created_at,
            )
        )
        await self._session.flush()

    async def get_snapshot_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnProjectSnapshot | None:
        result = await self._session.execute(
            select(ScientificReturnSnapshotRecord)
            .join(
                ScientificReturnWatchRecord,
                ScientificReturnWatchRecord.project_snapshot_id
                == ScientificReturnSnapshotRecord.id,
            )
            .where(ScientificReturnWatchRecord.id == watch_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return ScientificReturnProjectSnapshot(
            id=ScientificReturnSnapshotId(record.id),
            project_id=record.project_id,
            payload=_payload_to_domain(
                cast(
                    dict[str, object],
                    self._encryptor.decrypt_json(record.payload, _SNAPSHOT_PAYLOAD),
                )
            ),
            payload_hash=record.payload_hash,
            builder_version=record.builder_version,
            created_at=record.created_at,
        )

    async def add_run(self, run: ScientificReturnSearchRun) -> None:
        self._session.add(
            ScientificReturnRunRecord(
                id=run.id,
                watch_id=run.watch_id,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                source_count=run.source_count,
                candidate_count=run.candidate_count,
                new_candidate_count=run.new_candidate_count,
                error_message=run.error_message,
            )
        )
        await self._session.flush()

    async def save_run(self, run: ScientificReturnSearchRun) -> None:
        record = await self._session.get(ScientificReturnRunRecord, run.id)
        if record is None:
            raise LookupError(f"Scientific-return run {run.id} not found")
        record.status = run.status
        record.completed_at = run.completed_at
        record.source_count = run.source_count
        record.candidate_count = run.candidate_count
        record.new_candidate_count = run.new_candidate_count
        record.error_message = run.error_message
        await self._session.flush()

    async def list_runs(
        self, watch_id: ScientificReturnWatchId, page: int, size: int
    ) -> tuple[list[ScientificReturnSearchRun], int]:
        where = ScientificReturnRunRecord.watch_id == watch_id
        total = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(ScientificReturnRunRecord)
                    .where(where)
                )
            ).scalar_one()
        )
        result = await self._session.execute(
            select(ScientificReturnRunRecord)
            .where(where)
            .order_by(ScientificReturnRunRecord.started_at.desc())
            .offset(page * size)
            .limit(size)
        )
        return [_run_to_domain(item) for item in result.scalars().all()], total

    async def add_query(self, query: ScientificReturnQuery) -> None:
        self._session.add(
            ScientificReturnQueryRecord(
                id=query.id,
                run_id=query.run_id,
                source=query.source,
                query_text=self._encryptor.encrypt_required_text(
                    query.query_text, _QUERY_TEXT
                ),
                query_type=query.query_type,
                sent_at=query.sent_at,
                result_count=query.result_count,
                status=query.status,
                error_message=query.error_message,
            )
        )
        await self._session.flush()

    async def list_queries(self, run_id: str) -> list[ScientificReturnQuery]:
        result = await self._session.execute(
            select(ScientificReturnQueryRecord)
            .where(ScientificReturnQueryRecord.run_id == run_id)
            .order_by(
                ScientificReturnQueryRecord.sent_at,
                ScientificReturnQueryRecord.id,
            )
        )
        return [
            _query_to_domain(item, self._encryptor) for item in result.scalars().all()
        ]

    async def get_candidate(
        self, candidate_id: CandidatePublicationId
    ) -> CandidatePublication | None:
        result = await self._session.execute(
            select(CandidatePublicationRecord)
            .where(CandidatePublicationRecord.id == candidate_id)
            .options(selectinload(CandidatePublicationRecord.evidences))
        )
        record = result.scalar_one_or_none()
        return _candidate_to_domain(record) if record is not None else None

    async def get_candidate_by_key(
        self, watch_id: ScientificReturnWatchId, key: str
    ) -> CandidatePublication | None:
        result = await self._session.execute(
            select(CandidatePublicationRecord)
            .where(
                CandidatePublicationRecord.watch_id == watch_id,
                CandidatePublicationRecord.deduplication_key == key,
            )
            .options(selectinload(CandidatePublicationRecord.evidences))
        )
        record = result.scalar_one_or_none()
        return _candidate_to_domain(record) if record is not None else None

    async def add_candidate(self, candidate: CandidatePublication) -> None:
        self._session.add(
            CandidatePublicationRecord(
                id=candidate.id,
                watch_id=candidate.watch_id,
                first_seen_run_id=candidate.first_seen_run_id,
                source=candidate.source,
                source_record_id=candidate.source_record_id,
                deduplication_key=candidate.deduplication_key,
                doi=candidate.doi,
                title=candidate.title,
                authors=list(candidate.authors),
                publication_date=candidate.publication_date,
                abstract=candidate.abstract,
                url=candidate.url,
                raw_metadata_hash=candidate.raw_metadata_hash,
                status=candidate.status,
                snoozed_until=candidate.snoozed_until,
                confirmed_publication_entry_id=candidate.confirmed_publication_entry_id,
                created_at=candidate.created_at,
                evidences=[
                    CandidateEvidenceRecord(
                        id=evidence.id,
                        candidate_id=candidate.id,
                        type=evidence.type,
                        strength=evidence.strength,
                        value=evidence.value,
                        source_field=evidence.source_field,
                        explanation=evidence.explanation,
                        created_at=evidence.created_at,
                        object_id=evidence.object_id,
                    )
                    for evidence in candidate.evidences
                ],
            )
        )
        await self._session.flush()

    async def save_candidate(self, candidate: CandidatePublication) -> None:
        record = await self._session.get(CandidatePublicationRecord, candidate.id)
        if record is None:
            raise LookupError(f"Candidate {candidate.id} not found")
        record.title = candidate.title
        record.authors = list(candidate.authors)
        record.doi = candidate.doi
        record.url = candidate.url
        record.status = candidate.status
        record.snoozed_until = candidate.snoozed_until
        record.confirmed_publication_entry_id = candidate.confirmed_publication_entry_id
        await self._session.flush()

    async def list_candidates(
        self,
        project_id: str,
        status: CandidateStatus | None,
        page: int,
        size: int,
    ) -> tuple[list[CandidatePublication], int]:
        filters = [ScientificReturnWatchRecord.project_id == project_id]
        if status is not None:
            filters.append(CandidatePublicationRecord.status == status)
        total = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(CandidatePublicationRecord)
                    .join(
                        ScientificReturnWatchRecord,
                        CandidatePublicationRecord.watch_id
                        == ScientificReturnWatchRecord.id,
                    )
                    .where(*filters)
                )
            ).scalar_one()
        )
        result = await self._session.execute(
            select(CandidatePublicationRecord)
            .join(
                ScientificReturnWatchRecord,
                CandidatePublicationRecord.watch_id == ScientificReturnWatchRecord.id,
            )
            .where(*filters)
            .options(selectinload(CandidatePublicationRecord.evidences))
            .order_by(
                CandidatePublicationRecord.created_at.desc(),
                CandidatePublicationRecord.id.desc(),
            )
            .offset(page * size)
            .limit(size)
        )
        return [_candidate_to_domain(item) for item in result.scalars().all()], total

    async def add_decision(self, decision: CandidateDecision) -> None:
        self._session.add(
            CandidateDecisionRecord(
                id=decision.id,
                candidate_id=decision.candidate_id,
                decision=decision.decision,
                justification=decision.justification,
                decided_by=decision.decided_by,
                decided_at=decision.decided_at,
                evidence_snapshot=list(decision.evidence_snapshot),
                correction=(
                    asdict(decision.correction) if decision.correction else None
                ),
            )
        )
        await self._session.flush()

    async def list_candidate_queue(
        self,
        status: CandidateStatus | None,
        project_id: str | None,
        source: str | None,
        evidence_strength: EvidenceStrength | None,
        page: int,
        size: int,
    ) -> tuple[list[CandidateReviewItem], int]:
        filters: list[ColumnElement[bool]] = []
        if status is not None:
            filters.append(CandidatePublicationRecord.status == status)
        if project_id:
            filters.append(ScientificReturnWatchRecord.project_id == project_id)
        if source:
            filters.append(CandidatePublicationRecord.source == source)
        if evidence_strength is not None:
            filters.append(
                exists().where(
                    CandidateEvidenceRecord.candidate_id
                    == CandidatePublicationRecord.id,
                    CandidateEvidenceRecord.strength == evidence_strength,
                )
            )

        joined = (
            select(CandidatePublicationRecord, ScientificReturnWatchRecord.project_id)
            .join(
                ScientificReturnWatchRecord,
                CandidatePublicationRecord.watch_id == ScientificReturnWatchRecord.id,
            )
            .where(*filters)
        )
        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(
                        joined.with_only_columns(
                            CandidatePublicationRecord.id
                        ).subquery()
                    )
                )
            ).scalar_one()
        )
        result = await self._session.execute(
            joined.options(selectinload(CandidatePublicationRecord.evidences))
            .order_by(
                CandidatePublicationRecord.created_at.desc(),
                CandidatePublicationRecord.id.desc(),
            )
            .offset(page * size)
            .limit(size)
        )
        return (
            [
                CandidateReviewItem(
                    project_id=project_id_value,
                    candidate=_candidate_to_domain(candidate),
                )
                for candidate, project_id_value in result.all()
            ],
            total,
        )

    async def list_decisions(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateDecision]:
        result = await self._session.execute(
            select(CandidateDecisionRecord)
            .where(CandidateDecisionRecord.candidate_id == candidate_id)
            .order_by(CandidateDecisionRecord.decided_at, CandidateDecisionRecord.id)
        )
        return [_decision_to_domain(item) for item in result.scalars().all()]

    async def get_metrics(self) -> ScientificReturnMetrics:
        async def count(model: type[Any], *filters: ColumnElement[bool]) -> int:
            statement = select(func.count()).select_from(model)
            if filters:
                statement = statement.where(*filters)
            return int((await self._session.execute(statement)).scalar_one())

        return ScientificReturnMetrics(
            active_watches=await count(
                ScientificReturnWatchRecord,
                ScientificReturnWatchRecord.status == WatchStatus.ACTIVE,
            ),
            runs=await count(ScientificReturnRunRecord),
            failed_runs=await count(
                ScientificReturnRunRecord,
                ScientificReturnRunRecord.status == RunStatus.FAILED,
            ),
            pending_candidates=await count(
                CandidatePublicationRecord,
                CandidatePublicationRecord.status == CandidateStatus.PENDING,
            ),
            confirmed_candidates=await count(
                CandidatePublicationRecord,
                CandidatePublicationRecord.status == CandidateStatus.CONFIRMED,
            ),
            dismissed_candidates=await count(
                CandidatePublicationRecord,
                CandidatePublicationRecord.status == CandidateStatus.DISMISSED,
            ),
        )

    async def add_agent_analysis(self, analysis: CandidateAgentAnalysis) -> None:
        self._session.add(
            CandidateAgentAnalysisRecord(
                id=analysis.id,
                candidate_id=analysis.candidate_id,
                run_id=analysis.run_id,
                status=analysis.status,
                model=analysis.model,
                prompt_version_id=analysis.prompt_version_id,
                prompt_version=analysis.prompt_version,
                input_payload=self._encryptor.encrypt_json(
                    analysis.input_payload, _AGENT_INPUT
                )
                or "",
                input_hash=analysis.input_hash,
                analysis_payload=(
                    self._encryptor.encrypt_json(
                        _analysis_result_to_dict(analysis.result), _AGENT_ANALYSIS
                    )
                    if analysis.result is not None
                    else None
                ),
                recommended_action=(
                    analysis.result.recommended_action if analysis.result else None
                ),
                confidence=analysis.result.confidence if analysis.result else None,
                response_hash=analysis.response_hash,
                started_at=analysis.started_at,
                completed_at=analysis.completed_at,
                latency_ms=analysis.latency_ms,
                error_message=analysis.error_message,
                created_by=analysis.created_by,
                staff_feedback=analysis.staff_feedback,
                feedback_comment=analysis.feedback_comment,
                feedback_by=analysis.feedback_by,
                feedback_at=analysis.feedback_at,
            )
        )
        await self._session.flush()

    async def save_agent_analysis(self, analysis: CandidateAgentAnalysis) -> None:
        record = await self._session.get(CandidateAgentAnalysisRecord, analysis.id)
        if record is None:
            raise LookupError(f"Agent analysis {analysis.id} not found")
        record.status = analysis.status
        record.analysis_payload = (
            self._encryptor.encrypt_json(
                _analysis_result_to_dict(analysis.result), _AGENT_ANALYSIS
            )
            if analysis.result is not None
            else None
        )
        record.recommended_action = (
            analysis.result.recommended_action if analysis.result else None
        )
        record.confidence = analysis.result.confidence if analysis.result else None
        record.response_hash = analysis.response_hash
        record.completed_at = analysis.completed_at
        record.latency_ms = analysis.latency_ms
        record.error_message = analysis.error_message
        record.staff_feedback = analysis.staff_feedback
        record.feedback_comment = analysis.feedback_comment
        record.feedback_by = analysis.feedback_by
        record.feedback_at = analysis.feedback_at
        await self._session.flush()

    async def get_agent_analysis(
        self, analysis_id: CandidateAgentAnalysisId
    ) -> CandidateAgentAnalysis | None:
        record = await self._session.get(CandidateAgentAnalysisRecord, analysis_id)
        return (
            _agent_analysis_to_domain(record, self._encryptor)
            if record is not None
            else None
        )

    async def list_agent_analyses(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateAgentAnalysis]:
        result = await self._session.execute(
            select(CandidateAgentAnalysisRecord)
            .where(CandidateAgentAnalysisRecord.candidate_id == candidate_id)
            .order_by(
                CandidateAgentAnalysisRecord.started_at.desc(),
                CandidateAgentAnalysisRecord.id.desc(),
            )
        )
        return [
            _agent_analysis_to_domain(item, self._encryptor)
            for item in result.scalars().all()
        ]
