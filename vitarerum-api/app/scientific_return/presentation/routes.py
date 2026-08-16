from __future__ import annotations

import logging
from math import ceil
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.notifications.public import NotificationKind, RelatedResourceType
from app.scientific_return.application.use_cases import (
    ActivateScientificReturnWatch,
    ActivateWatchInput,
    CandidateNotFound,
    ChangeWatchStatus,
    DecideCandidate,
    DecideCandidateInput,
    RunScientificReturnSearch,
    WatchNotFound,
)
from app.scientific_return.domain.enums import CandidateStatus, EvidenceStrength
from app.scientific_return.domain.models import (
    CandidateCorrection,
    CandidateDecision,
    CandidatePublication,
    CandidatePublicationId,
    ScientificReturnSearchRun,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)
from app.scientific_return.presentation.dependencies import (
    BibliographicSources,
    DBSession,
    MaxQueries,
    Notifications,
    ProjectProvider,
    PublicationWriter,
    Repository,
    ResultLimit,
)
from app.scientific_return.presentation.schemas import (
    ActivateWatchRequest,
    CandidateCorrectionRequest,
    CandidateDecisionRequest,
    CandidateDecisionResponse,
    CandidateEvidenceResponse,
    CandidatePublicationResponse,
    CandidateReviewItemResponse,
    ChangeWatchStatusRequest,
    PaginatedCandidateQueueResponse,
    PaginatedCandidatesResponse,
    PaginatedRunsResponse,
    ScientificReturnMetricsResponse,
    ScientificReturnQueryResponse,
    ScientificReturnRunResponse,
    ScientificReturnWatchResponse,
)
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission

scientific_return_router = APIRouter(
    prefix="/scientific-return", tags=["scientific-return"]
)
logger = logging.getLogger(__name__)


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": code, "message": message},
    )


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error": "SCIENTIFIC_RETURN_INVALID", "message": message},
    )


def _watch_response(watch: ScientificReturnWatch) -> ScientificReturnWatchResponse:
    return ScientificReturnWatchResponse(
        id=watch.id,
        projectId=watch.project_id,
        status=watch.status,
        reviewIntervalDays=watch.review_interval_days,
        createdBy=watch.created_by,
        createdAt=watch.created_at,
        lastRunAt=watch.last_run_at,
        nextRunAt=watch.next_run_at,
        projectSnapshotId=watch.project_snapshot_id,
    )


async def _run_response(
    run: ScientificReturnSearchRun, repository: Repository
) -> ScientificReturnRunResponse:
    queries = await repository.list_queries(str(run.id))
    return ScientificReturnRunResponse(
        id=run.id,
        watchId=run.watch_id,
        status=run.status,
        startedAt=run.started_at,
        completedAt=run.completed_at,
        sourceCount=run.source_count,
        candidateCount=run.candidate_count,
        newCandidateCount=run.new_candidate_count,
        errorMessage=run.error_message,
        queries=[
            ScientificReturnQueryResponse(
                id=query.id,
                source=query.source,
                queryText=query.query_text,
                queryType=query.query_type,
                sentAt=query.sent_at,
                resultCount=query.result_count,
                status=query.status,
                errorMessage=query.error_message,
            )
            for query in queries
        ],
    )


def _candidate_response(
    candidate: CandidatePublication,
) -> CandidatePublicationResponse:
    order = {"PRIMARY": 0, "SUPPORTING": 1, "WEAK": 2}
    evidences = sorted(candidate.evidences, key=lambda item: order[item.strength.value])
    return CandidatePublicationResponse(
        id=candidate.id,
        watchId=candidate.watch_id,
        source=candidate.source,
        sourceRecordId=candidate.source_record_id,
        doi=candidate.doi,
        title=candidate.title,
        authors=list(candidate.authors),
        publicationDate=candidate.publication_date,
        abstract=candidate.abstract,
        url=candidate.url,
        status=candidate.status,
        snoozedUntil=candidate.snoozed_until,
        confirmedPublicationEntryId=candidate.confirmed_publication_entry_id,
        firstSeenAt=candidate.created_at,
        evidences=[
            CandidateEvidenceResponse(
                id=evidence.id,
                type=evidence.type,
                strength=evidence.strength,
                value=evidence.value,
                sourceField=evidence.source_field,
                explanation=evidence.explanation,
                objectId=evidence.object_id,
            )
            for evidence in evidences
        ],
    )


@scientific_return_router.get(
    "/metrics", response_model=ScientificReturnMetricsResponse
)
async def get_metrics(
    caller: CallerPermission,
    repository: Repository,
) -> ScientificReturnMetricsResponse:
    require_staff(caller)
    metrics = await repository.get_metrics()
    return ScientificReturnMetricsResponse(
        activeWatches=metrics.active_watches,
        runs=metrics.runs,
        failedRuns=metrics.failed_runs,
        pendingCandidates=metrics.pending_candidates,
        confirmedCandidates=metrics.confirmed_candidates,
        dismissedCandidates=metrics.dismissed_candidates,
    )


def _correction_response(
    correction: CandidateCorrection | None,
) -> CandidateCorrectionRequest | None:
    if correction is None:
        return None
    return CandidateCorrectionRequest(
        title=correction.title,
        doi=correction.doi,
        url=correction.url,
        authors=list(correction.authors) if correction.authors is not None else None,
    )


def _decision_response(decision: CandidateDecision) -> CandidateDecisionResponse:
    return CandidateDecisionResponse(
        id=decision.id,
        candidateId=decision.candidate_id,
        decision=decision.decision,
        justification=decision.justification,
        decidedBy=decision.decided_by,
        decidedAt=decision.decided_at,
        evidenceSnapshot=list(decision.evidence_snapshot),
        correction=_correction_response(decision.correction),
    )


@scientific_return_router.post(
    "/projects/{project_id}/watch",
    status_code=status.HTTP_201_CREATED,
    response_model=ScientificReturnWatchResponse,
)
async def activate_watch(
    project_id: str,
    body: ActivateWatchRequest,
    caller: CallerPermission,
    repository: Repository,
    project_provider: ProjectProvider,
    session: DBSession,
) -> ScientificReturnWatchResponse:
    try:
        watch = await ActivateScientificReturnWatch(
            repository, project_provider
        ).execute(
            ActivateWatchInput(
                project_id=project_id,
                review_interval_days=body.reviewIntervalDays,
                caller=caller,
            )
        )
    except LookupError as exc:
        raise _not_found("COMPLETED_PROJECT_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    return _watch_response(watch)


@scientific_return_router.get(
    "/projects/{project_id}/watch", response_model=ScientificReturnWatchResponse
)
async def get_watch(
    project_id: str,
    caller: CallerPermission,
    repository: Repository,
) -> ScientificReturnWatchResponse:
    require_staff(caller)
    watch = await repository.get_watch_by_project(project_id)
    if watch is None:
        raise _not_found(
            "SCIENTIFIC_RETURN_WATCH_NOT_FOUND",
            f"No scientific-return watch exists for project {project_id}",
        )
    return _watch_response(watch)


@scientific_return_router.patch(
    "/watches/{watch_id}", response_model=ScientificReturnWatchResponse
)
async def change_watch_status(
    watch_id: str,
    body: ChangeWatchStatusRequest,
    caller: CallerPermission,
    repository: Repository,
    session: DBSession,
) -> ScientificReturnWatchResponse:
    try:
        watch = await ChangeWatchStatus(repository).execute(
            ScientificReturnWatchId(watch_id), body.status, caller
        )
    except WatchNotFound as exc:
        raise _not_found("SCIENTIFIC_RETURN_WATCH_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    return _watch_response(watch)


@scientific_return_router.post(
    "/watches/{watch_id}/runs",
    status_code=status.HTTP_201_CREATED,
    response_model=ScientificReturnRunResponse,
)
async def run_watch(
    watch_id: str,
    caller: CallerPermission,
    repository: Repository,
    sources: BibliographicSources,
    result_limit: ResultLimit,
    max_queries: MaxQueries,
    notifications: Notifications,
    session: DBSession,
) -> ScientificReturnRunResponse:
    try:
        run = await RunScientificReturnSearch(
            repository,
            sources,
            result_limit,
            max_queries,
        ).execute(ScientificReturnWatchId(watch_id), caller)
    except WatchNotFound as exc:
        raise _not_found("SCIENTIFIC_RETURN_WATCH_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    if run.new_candidate_count:
        watch = await repository.get_watch(ScientificReturnWatchId(watch_id))
        if watch is not None:
            try:
                await notifications.notify(
                    recipient_permission_id=watch.created_by,
                    kind=NotificationKind.SCIENTIFIC_RETURN_CANDIDATES_FOUND,
                    triggered_by=caller.id,
                    related_resource_type=RelatedResourceType.PROJECT,
                    related_resource_id=watch.project_id,
                    note=(
                        f"Scientific return found {run.new_candidate_count} new "
                        "candidate(s) for review."
                    ),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("Could not notify scientific-return run %s.", run.id)
    return await _run_response(run, repository)


@scientific_return_router.get(
    "/watches/{watch_id}/runs", response_model=PaginatedRunsResponse
)
async def list_runs(
    watch_id: str,
    caller: CallerPermission,
    repository: Repository,
    page: int = Query(0, ge=0),
    size: int = Query(10, ge=1, le=100),
) -> PaginatedRunsResponse:
    require_staff(caller)
    items, total = await repository.list_runs(
        ScientificReturnWatchId(watch_id), page, size
    )
    return PaginatedRunsResponse(
        content=[await _run_response(item, repository) for item in items],
        page=page,
        size=size,
        totalElements=total,
        totalPages=ceil(total / size) if total else 0,
    )


@scientific_return_router.get(
    "/projects/{project_id}/candidates", response_model=PaginatedCandidatesResponse
)
async def list_candidates(
    project_id: str,
    caller: CallerPermission,
    repository: Repository,
    candidate_status: Annotated[CandidateStatus | None, Query(alias="status")] = None,
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
) -> PaginatedCandidatesResponse:
    require_staff(caller)
    items, total = await repository.list_candidates(
        project_id, candidate_status, page, size
    )
    return PaginatedCandidatesResponse(
        content=[_candidate_response(item) for item in items],
        page=page,
        size=size,
        totalElements=total,
        totalPages=ceil(total / size) if total else 0,
    )


@scientific_return_router.get(
    "/candidates", response_model=PaginatedCandidateQueueResponse
)
async def list_candidate_queue(
    caller: CallerPermission,
    repository: Repository,
    candidate_status: Annotated[CandidateStatus | None, Query(alias="status")] = (
        CandidateStatus.PENDING
    ),
    project_id: Annotated[str | None, Query(alias="projectId")] = None,
    source: str | None = None,
    evidence_strength: Annotated[
        EvidenceStrength | None, Query(alias="evidenceStrength")
    ] = None,
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
) -> PaginatedCandidateQueueResponse:
    require_staff(caller)
    items, total = await repository.list_candidate_queue(
        candidate_status,
        project_id,
        source,
        evidence_strength,
        page,
        size,
    )
    return PaginatedCandidateQueueResponse(
        content=[
            CandidateReviewItemResponse(
                **_candidate_response(item.candidate).model_dump(),
                projectId=item.project_id,
            )
            for item in items
        ],
        page=page,
        size=size,
        totalElements=total,
        totalPages=ceil(total / size) if total else 0,
    )


@scientific_return_router.post(
    "/candidates/{candidate_id}/decision",
    response_model=CandidatePublicationResponse,
)
async def decide_candidate(
    candidate_id: str,
    body: CandidateDecisionRequest,
    caller: CallerPermission,
    repository: Repository,
    publication_writer: PublicationWriter,
    session: DBSession,
) -> CandidatePublicationResponse:
    correction = (
        CandidateCorrection(
            title=body.correction.title,
            doi=body.correction.doi,
            url=body.correction.url,
            authors=(
                tuple(body.correction.authors)
                if body.correction.authors is not None
                else None
            ),
        )
        if body.correction is not None
        else None
    )
    try:
        candidate = await DecideCandidate(repository, publication_writer).execute(
            DecideCandidateInput(
                candidate_id=CandidatePublicationId(candidate_id),
                decision=body.decision,
                caller=caller,
                justification=body.justification,
                snoozed_until=body.snoozedUntil,
                correction=correction,
            )
        )
    except CandidateNotFound as exc:
        raise _not_found("SCIENTIFIC_RETURN_CANDIDATE_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    return _candidate_response(candidate)


@scientific_return_router.get(
    "/candidates/{candidate_id}/decisions",
    response_model=list[CandidateDecisionResponse],
)
async def list_candidate_decisions(
    candidate_id: str,
    caller: CallerPermission,
    repository: Repository,
) -> list[CandidateDecisionResponse]:
    require_staff(caller)
    decisions = await repository.list_decisions(CandidatePublicationId(candidate_id))
    return [_decision_response(item) for item in decisions]
