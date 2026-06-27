"""In Situ Visit CEDOC mapping endpoints (the driving adapter).

Two staff-only operations over the ``InSituVisitRecord`` aggregate: persist one
(POST) and list them paginated (GET). Authentication uses the shared
``Authorization`` / ``X-Permission-Id`` headers; authorization is staff-only via
``require_staff``. Errors follow the shared ``{ "error": CODE, "message": str }``
shape through ``main.py``'s normaliser.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cidoc_crm.in_situ_visit_mapping.application.use_cases import (
    BuildInSituVisitCidocInput,
    ExportInSituVisitInput,
    InSituVisitRecordNotFound,
    ListInSituVisitsInput,
    NotInSituVisit,
    ProjectNotFound,
    RecordInSituVisitInput,
)
from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    AttachmentData,
    ChildData,
)
from app.cidoc_crm.in_situ_visit_mapping.presentation.dependencies import (
    CidocUseCase,
    ExportUseCase,
    ListUseCase,
    RecordUseCase,
)
from app.cidoc_crm.in_situ_visit_mapping.presentation.mappers import record_to_response
from app.cidoc_crm.in_situ_visit_mapping.presentation.schemas import (
    InSituVisitRecordRequest,
    InSituVisitRecordResponse,
    LogRequest,
    OccurrenceRequest,
    PaginatedInSituVisitRecordsResponse,
    PublicationRequest,
    RequestedObjectRequest,
)
from app.database import get_async_session
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission

in_situ_visit_router = APIRouter(
    prefix="/cedoc-mapping/in-situ-visit", tags=["cedoc-mapping"]
)

project_export_router = APIRouter(
    prefix="/collection-use-projects", tags=["cedoc-mapping"]
)

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

ChildRequest = (
    RequestedObjectRequest | OccurrenceRequest | LogRequest | PublicationRequest
)


def _to_child_data(item: ChildRequest) -> ChildData:
    attachments = getattr(item, "attachments", [])
    return ChildData(
        source_id=item.sourceId,
        description=item.description,
        position=item.position,
        attachments=[
            AttachmentData(
                source_id=att.sourceId,
                description=att.description,
                reference=att.reference,
                position=att.position,
            )
            for att in attachments
        ],
    )


@in_situ_visit_router.post(
    "",
    response_model=InSituVisitRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_in_situ_visit(
    body: InSituVisitRecordRequest,
    caller: CallerPermission,
    use_case: RecordUseCase,
    session: DBSession,
) -> InSituVisitRecordResponse:
    require_staff(caller)
    record = await use_case.execute(
        RecordInSituVisitInput(
            code=body.code,
            visit_begin_date=body.visitBeginDate,
            visit_end_date=body.visitEndDate,
            visitor_name=body.visitorName,
            place_name=body.placeName,
            requested_objects=[_to_child_data(ro) for ro in body.requestedObjects],
            in_situ_occurrences=[_to_child_data(o) for o in body.inSituOccurrences],
            in_situ_logs=[_to_child_data(log) for log in body.inSituLogs],
            in_situ_publications=[_to_child_data(p) for p in body.inSituPublications],
        )
    )
    await session.commit()
    return record_to_response(record)


@in_situ_visit_router.get(
    "",
    response_model=PaginatedInSituVisitRecordsResponse,
)
async def list_in_situ_visits(
    caller: CallerPermission,
    use_case: ListUseCase,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedInSituVisitRecordsResponse:
    require_staff(caller)
    records, total = await use_case.execute(ListInSituVisitsInput(page=page, size=size))
    return PaginatedInSituVisitRecordsResponse(
        content=[record_to_response(r) for r in records],
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@in_situ_visit_router.get("/{record_id}/cidoc-crm", response_model=None)
async def get_in_situ_visit_cidoc(
    record_id: str,
    caller: CallerPermission,
    use_case: CidocUseCase,
) -> dict[str, Any]:
    """Return the CIDOC-CRM 7.1.3 JSON-LD representation of a stored record."""
    require_staff(caller)
    try:
        return await use_case.execute(BuildInSituVisitCidocInput(record_id=record_id))
    except InSituVisitRecordNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "IN_SITU_VISIT_NOT_FOUND", "message": str(exc)},
        ) from None


@project_export_router.post(
    "/{project_id}/export-in-situ-visit-record",
    response_model=InSituVisitRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def export_in_situ_visit_record(
    project_id: str,
    caller: CallerPermission,
    use_case: ExportUseCase,
    session: DBSession,
) -> InSituVisitRecordResponse:
    """Generate and persist an in-situ visit record from an IN_SITU_VISIT project."""
    require_staff(caller)
    try:
        record = await use_case.execute(ExportInSituVisitInput(project_id=project_id))
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
    await session.commit()
    return record_to_response(record)
