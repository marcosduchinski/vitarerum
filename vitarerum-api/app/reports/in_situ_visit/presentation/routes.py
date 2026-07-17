"""In-Situ Visit Report endpoint (the driving adapter).

Staff-only. Composes the project export and the KG-RAG narrative generation,
then persists an ``InSituVisitReport`` tying them together, under a single
transaction. Maps the composed steps' domain errors onto the spec's HTTP
statuses via ``HTTPException(detail=...)`` and ``main.py``'s normaliser:
- project missing            → 404 PROJECT_NOT_FOUND
- project not IN_SITU_VISIT  → 409 INVALID_USE_TYPE
- visit not evidenced        → 409 VISIT_NOT_EVIDENCED
- unsupported style          → 400 INVALID_NARRATIVE_TYPE
- reasoner/SHACL rejection   → 422 SEMANTIC_VALIDATION_FAILED
- model unreachable / slow   → 503 / 504
"""

from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.ai.museum_narrative.public import (
    ModelTimeout,
    ModelUnavailable,
    SemanticValidationFailed,
    UnsupportedNarrativeType,
)
from app.cidoc_crm.public import (
    NotInSituVisit,
    ProjectNotFound,
    VisitNotEvidenced,
)
from app.reports.in_situ_visit.application.use_cases import (
    GenerateInSituVisitReportInput,
    GetInSituVisitReportInput,
    InSituVisitReportNotFound,
    InSituVisitReportSummary,
    ListAllInSituVisitReportsInput,
    ListInSituVisitReportsInput,
)
from app.reports.in_situ_visit.domain.models import InSituVisitReport
from app.reports.in_situ_visit.presentation.dependencies import (
    DBSession,
    DetailUseCase,
    GetUseCase,
    ListAllUseCase,
    ListUseCase,
    ReportUseCase,
)
from app.reports.in_situ_visit.presentation.schemas import (
    InSituVisitReportDetailResponse,
    InSituVisitReportRequest,
    InSituVisitReportResponse,
    InSituVisitReportSummaryResponse,
    PaginatedInSituVisitReportsResponse,
    PaginatedInSituVisitReportSummariesResponse,
)
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission

reports_router = APIRouter(prefix="/reports/collection-use", tags=["reports"])


def _to_response(report: InSituVisitReport) -> InSituVisitReportResponse:
    return InSituVisitReportResponse(
        id=report.id,
        createdAt=report.created_at,
        createdBy=report.created_by,
        projectId=report.project_id,
        narrativeId=report.narrative_id,
        inSituVisitRecordId=report.in_situ_visit_record_id,
    )


@reports_router.post(
    "/{project_id}/in_situ_visit",
    response_model=InSituVisitReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_in_situ_visit_report(
    project_id: str,
    body: InSituVisitReportRequest,
    caller: CallerPermission,
    use_case: ReportUseCase,
    session: DBSession,
) -> InSituVisitReportResponse:
    require_staff(caller)
    try:
        report = await use_case.execute(
            GenerateInSituVisitReportInput(
                project_id=project_id,
                created_by=caller.id,
                narrative_type=body.narrative_type,
                target_language=body.target_language,
                creativity_temperature=body.creativity_temperature,
            )
        )
    except ProjectNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "PROJECT_NOT_FOUND", "message": str(exc)},
        ) from None
    except NotInSituVisit as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "INVALID_USE_TYPE", "message": str(exc)},
        ) from None
    except VisitNotEvidenced as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "VISIT_NOT_EVIDENCED", "message": str(exc)},
        ) from None
    except UnsupportedNarrativeType as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_NARRATIVE_TYPE", "message": str(exc)},
        ) from None
    except SemanticValidationFailed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "SEMANTIC_VALIDATION_FAILED",
                "message": (
                    "The reasoner rejected the generated graph due to ontology "
                    "constraints."
                ),
            },
        ) from None
    except ModelUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "MODEL_UNAVAILABLE", "message": str(exc)},
        ) from None
    except ModelTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error": "MODEL_TIMEOUT", "message": str(exc)},
        ) from None

    await session.commit()
    return _to_response(report)


def _to_summary(
    summary: InSituVisitReportSummary,
) -> InSituVisitReportSummaryResponse:
    report = summary.report
    return InSituVisitReportSummaryResponse(
        id=report.id,
        createdAt=report.created_at,
        createdBy=report.created_by,
        projectId=report.project_id,
        narrativeId=report.narrative_id,
        inSituVisitRecordId=report.in_situ_visit_record_id,
        code=summary.code,
        visitorName=summary.visitor_name,
        placeName=summary.place_name,
        visitBeginDate=summary.visit_begin_date,
        visitEndDate=summary.visit_end_date,
    )


@reports_router.get(
    "/in_situ_visit",
    response_model=PaginatedInSituVisitReportSummariesResponse,
)
async def list_all_in_situ_visit_reports(
    caller: CallerPermission,
    use_case: ListAllUseCase,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedInSituVisitReportSummariesResponse:
    """List reports across all projects, newest first, each enriched with the
    visit's display fields (code, visitor, place, dates). Staff-only."""
    require_staff(caller)
    summaries, total = await use_case.execute(
        ListAllInSituVisitReportsInput(page=page, size=size)
    )
    return PaginatedInSituVisitReportSummariesResponse(
        content=[_to_summary(s) for s in summaries],
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@reports_router.get(
    "/{project_id}/in_situ_visit",
    response_model=PaginatedInSituVisitReportsResponse,
)
async def list_in_situ_visit_reports(
    project_id: str,
    caller: CallerPermission,
    use_case: ListUseCase,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedInSituVisitReportsResponse:
    """List the reports generated for a project, newest first. Staff-only."""
    require_staff(caller)
    reports, total = await use_case.execute(
        ListInSituVisitReportsInput(project_id=project_id, page=page, size=size)
    )
    return PaginatedInSituVisitReportsResponse(
        content=[_to_response(r) for r in reports],
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@reports_router.get(
    "/{project_id}/in_situ_visit/{report_id}",
    response_model=InSituVisitReportResponse,
)
async def get_in_situ_visit_report(
    project_id: str,
    report_id: str,
    caller: CallerPermission,
    use_case: GetUseCase,
) -> InSituVisitReportResponse:
    """Return one report by id (must belong to the project). Staff-only."""
    require_staff(caller)
    try:
        report = await use_case.execute(
            GetInSituVisitReportInput(project_id=project_id, report_id=report_id)
        )
    except InSituVisitReportNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "REPORT_NOT_FOUND", "message": str(exc)},
        ) from None
    return _to_response(report)


@reports_router.get(
    "/{project_id}/in_situ_visit/{report_id}/detail",
    response_model=InSituVisitReportDetailResponse,
)
async def get_in_situ_visit_report_detail(
    project_id: str,
    report_id: str,
    caller: CallerPermission,
    use_case: DetailUseCase,
) -> InSituVisitReportDetailResponse:
    """Return a report with its embedded narrative and in-situ visit record
    (with attachments). Must belong to the project. Staff-only."""
    require_staff(caller)
    try:
        detail = await use_case.execute(
            GetInSituVisitReportInput(project_id=project_id, report_id=report_id)
        )
    except InSituVisitReportNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "REPORT_NOT_FOUND", "message": str(exc)},
        ) from None
    report = detail.report
    return InSituVisitReportDetailResponse(
        id=report.id,
        createdAt=report.created_at,
        createdBy=report.created_by,
        projectId=report.project_id,
        narrativeId=report.narrative_id,
        inSituVisitRecordId=report.in_situ_visit_record_id,
        narrative=detail.narrative,
        record=detail.record,
    )
