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
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.ai.museum_narrative.public import (
    ModelTimeout,
    ModelUnavailable,
    NarrativePromptUnavailable,
    SemanticValidationFailed,
    UnsupportedNarrativeType,
)
from app.cidoc_crm.public import (
    NotInSituVisit,
    ProjectNotFound,
    VisitNotEvidenced,
)
from app.reports.in_situ_visit.application.ports import InSituVisitReportFilters
from app.reports.in_situ_visit.application.use_cases import (
    DeleteInSituVisitReportInput,
    GenerateInSituVisitReportInput,
    GetInSituVisitReportInput,
    InSituVisitReportAuditTrail,
    InSituVisitReportNotFound,
    InSituVisitReportSummary,
    ListAllInSituVisitReportsInput,
    ListInSituVisitReportsInput,
)
from app.reports.in_situ_visit.domain.models import InSituVisitReport
from app.reports.in_situ_visit.presentation.dependencies import (
    AuditTrailUseCase,
    DBSession,
    DeleteUseCase,
    DetailUseCase,
    GetUseCase,
    ListAllUseCase,
    ListUseCase,
    ReportUseCase,
)
from app.reports.in_situ_visit.presentation.schemas import (
    InSituVisitAuditCidocResponse,
    InSituVisitAuditEvidenceResponse,
    InSituVisitAuditFactsResponse,
    InSituVisitAuditGenerationResponse,
    InSituVisitAuditTrailResponse,
    InSituVisitAuditValidationResponse,
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
    except NarrativePromptUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "NARRATIVE_PROMPT_UNAVAILABLE", "message": str(exc)},
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
        narrativeType=summary.narrative_type,
        targetLanguage=summary.target_language,
        creativityTemperature=summary.creativity_temperature,
    )


def _to_audit_trail_response(
    audit: InSituVisitReportAuditTrail,
) -> InSituVisitAuditTrailResponse:
    report = audit.report
    record = audit.record
    narrative = audit.narrative
    meta = narrative.meta if narrative else None
    snapshot = narrative.facts_snapshot if narrative else None
    return InSituVisitAuditTrailResponse(
        id=report.id,
        createdAt=report.created_at,
        createdBy=report.created_by,
        projectId=report.project_id,
        narrativeId=report.narrative_id,
        inSituVisitRecordId=report.in_situ_visit_record_id,
        record=record,
        narrative=narrative,
        evidence=InSituVisitAuditEvidenceResponse(
            recordId=record.id if record else None,
            projectId=report.project_id,
            code=record.code if record else None,
            executionEvidenceType=record.executionEvidenceType if record else None,
            executionOccurredAt=record.executionOccurredAt if record else None,
            executionRecordedBy=record.executionRecordedBy if record else None,
            executionEvidenceGaps=record.executionEvidenceGaps if record else [],
            approvedAt=record.approvedAt if record else None,
            approvedBy=record.approvedBy if record else None,
            approvalNote=record.approvalNote if record else None,
        ),
        cidoc=InSituVisitAuditCidocResponse(
            documentJson=snapshot.cidoc_document_json if snapshot else None,
            mappingVersion=record.mappingVersion if record else None,
            crmVersion=record.crmVersion if record else None,
            recordSchemaVersion=record.recordSchemaVersion if record else None,
            conforms=snapshot.cidoc_conforms if snapshot else None,
            validationReport=(snapshot.cidoc_validation_report if snapshot else None),
        ),
        facts=InSituVisitAuditFactsResponse(
            snapshotId=snapshot.id if snapshot else None,
            payloadJson=snapshot.payload_json if snapshot else None,
            payloadHash=snapshot.payload_hash if snapshot else None,
            builderVersion=snapshot.builder_version if snapshot else None,
            promptVersion=snapshot.prompt_version if snapshot else None,
            createdAt=snapshot.created_at if snapshot else None,
        ),
        generation=InSituVisitAuditGenerationResponse(
            narrativeId=narrative.narrative_id if narrative else None,
            generatedAt=narrative.generated_at if narrative else None,
            narrativeType=meta.resolved_narrative_type if meta else None,
            resolutionSource=meta.resolution_source if meta else None,
            targetLanguage=meta.target_language if meta else None,
            creativityTemperature=meta.creativity_temperature if meta else None,
            llmModel=meta.llm_model if meta else None,
            promptVersionId=meta.prompt_version_id if meta else None,
            promptVersion=meta.prompt_version if meta else None,
            responseHash=meta.model_response_hash if meta else None,
        ),
        validation=InSituVisitAuditValidationResponse(
            conforms=meta.validation_conforms if meta else None,
            findings=meta.validation_findings if meta else [],
        ),
        revisions=audit.revisions,
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
    search: Annotated[str | None, Query(max_length=255)] = None,
    generated_from: Annotated[datetime | None, Query(alias="generatedFrom")] = None,
    generated_to: Annotated[datetime | None, Query(alias="generatedTo")] = None,
    visit_from: Annotated[date | None, Query(alias="visitFrom")] = None,
    visit_to: Annotated[date | None, Query(alias="visitTo")] = None,
    narrative_type: Annotated[str | None, Query(alias="narrativeType")] = None,
) -> PaginatedInSituVisitReportSummariesResponse:
    """List reports across all projects, newest first, each enriched with the
    visit's display fields (code, visitor, place, dates). Staff-only."""
    require_staff(caller)
    filters = InSituVisitReportFilters(
        search=search,
        generated_from=generated_from,
        generated_to=generated_to,
        visit_from=visit_from,
        visit_to=visit_to,
        narrative_type=narrative_type,
    )
    summaries, total = await use_case.execute(
        ListAllInSituVisitReportsInput(page=page, size=size, filters=filters)
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


@reports_router.delete(
    "/{project_id}/in_situ_visit/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_in_situ_visit_report(
    project_id: str,
    report_id: str,
    caller: CallerPermission,
    use_case: DeleteUseCase,
    session: DBSession,
) -> None:
    """Hard delete one generated report and its generated narrative artifacts.

    The exported in-situ visit record is preserved.
    """
    require_staff(caller)
    try:
        await use_case.execute(
            DeleteInSituVisitReportInput(
                project_id=project_id,
                report_id=report_id,
                deleted_by=caller.id,
            )
        )
    except InSituVisitReportNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "REPORT_NOT_FOUND", "message": str(exc)},
        ) from None
    await session.commit()


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


@reports_router.get(
    "/{project_id}/in_situ_visit/{report_id}/audit-trail",
    response_model=InSituVisitAuditTrailResponse,
)
async def get_in_situ_visit_report_audit_trail(
    project_id: str,
    report_id: str,
    caller: CallerPermission,
    use_case: AuditTrailUseCase,
    revisions_page: Annotated[int, Query(ge=0)] = 0,
    revisions_size: Annotated[int, Query(ge=1, le=100)] = 100,
) -> InSituVisitAuditTrailResponse:
    """Return the complete audit trail for one generated in-situ visit report."""
    require_staff(caller)
    try:
        audit = await use_case.execute(
            GetInSituVisitReportInput(project_id=project_id, report_id=report_id),
            revisions_page=revisions_page,
            revisions_size=revisions_size,
        )
    except InSituVisitReportNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "REPORT_NOT_FOUND", "message": str(exc)},
        ) from None
    return _to_audit_trail_response(audit)
