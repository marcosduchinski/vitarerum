"""KG-RAG museum-narrative endpoint (the driving adapter).

Staff-only. Maps the pipeline's domain errors onto the spec's HTTP statuses via
``HTTPException(detail=...)`` and ``main.py``'s normaliser:
- unsupported style          → 400 INVALID_NARRATIVE_TYPE
- record missing             → 404 IN_SITU_VISIT_NOT_FOUND
- reasoner/SHACL rejection   → 422 SEMANTIC_VALIDATION_FAILED
- model unreachable / slow   → 503 / 504
"""

from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.ai.museum_narrative.application.use_cases import (
    GenerateNarrativeInput,
    GetNarrativeInput,
    ListNarrativesInput,
    UpdateNarrativeInput,
)
from app.ai.museum_narrative.domain.ports import (
    ModelTimeout,
    ModelUnavailable,
    NarrativeNotFound,
    RecordNotFound,
    SemanticValidationFailed,
    UnsupportedNarrativeType,
)
from app.ai.museum_narrative.presentation.dependencies import (
    DBSession,
    GetUseCase,
    ListUseCase,
    NarrativeUseCase,
    UpdateUseCase,
)
from app.ai.museum_narrative.presentation.mappers import (
    fact_snapshot_response,
    narrative_meta,
    stored_narrative_response,
)
from app.ai.museum_narrative.presentation.schemas import (
    NarrativeData,
    NarrativeRequest,
    NarrativeResponse,
    PaginatedNarrativesResponse,
    StoredNarrativeResponse,
    UpdateNarrativeRequest,
)
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission

museum_narrative_router = APIRouter(
    prefix="/cidoc-mapping/in-situ-visit", tags=["kg-rag-narrative"]
)


@museum_narrative_router.post(
    "/{record_id}/narrative", response_model=NarrativeResponse
)
async def generate_narrative(
    record_id: str,
    body: NarrativeRequest,
    caller: CallerPermission,
    use_case: NarrativeUseCase,
    session: DBSession,
) -> NarrativeResponse:
    require_staff(caller)
    try:
        result = await use_case.execute(
            GenerateNarrativeInput(
                record_id=record_id,
                narrative_type=body.narrative_type,
                target_language=body.target_language,
                creativity_temperature=body.creativity_temperature,
            )
        )
    except UnsupportedNarrativeType as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_NARRATIVE_TYPE", "message": str(exc)},
        ) from None
    except RecordNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "IN_SITU_VISIT_NOT_FOUND", "message": str(exc)},
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
    return NarrativeResponse(
        narrative_id=result.id,
        record_id=result.record_id,
        status="success",
        generated_at=result.generated_at,
        meta=narrative_meta(result),
        data=NarrativeData(narrative=result.narrative),
        facts_snapshot=fact_snapshot_response(result),
    )


@museum_narrative_router.get(
    "/{record_id}/narratives", response_model=PaginatedNarrativesResponse
)
async def list_narratives(
    record_id: str,
    caller: CallerPermission,
    use_case: ListUseCase,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedNarrativesResponse:
    """List stored narratives for an in-situ visit record, newest first."""
    require_staff(caller)
    records, total = await use_case.execute(
        ListNarrativesInput(record_id=record_id, page=page, size=size)
    )
    return PaginatedNarrativesResponse(
        content=[stored_narrative_response(r) for r in records],
        page=page,
        size=size,
        total_elements=total,
        total_pages=math.ceil(total / size) if size > 0 else 0,
    )


@museum_narrative_router.get(
    "/{record_id}/narratives/{narrative_id}",
    response_model=StoredNarrativeResponse,
)
async def get_narrative(
    record_id: str,
    narrative_id: str,
    caller: CallerPermission,
    use_case: GetUseCase,
) -> StoredNarrativeResponse:
    """Return one stored narrative by id."""
    require_staff(caller)
    try:
        record = await use_case.execute(
            GetNarrativeInput(record_id=record_id, narrative_id=narrative_id)
        )
    except NarrativeNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NARRATIVE_NOT_FOUND", "message": str(exc)},
        ) from None
    return stored_narrative_response(record)


@museum_narrative_router.patch(
    "/{record_id}/narratives/{narrative_id}",
    response_model=StoredNarrativeResponse,
)
async def update_narrative(
    record_id: str,
    narrative_id: str,
    body: UpdateNarrativeRequest,
    caller: CallerPermission,
    use_case: UpdateUseCase,
    session: DBSession,
) -> StoredNarrativeResponse:
    """Edit the text of a stored narrative (manual editorial correction)."""
    require_staff(caller)
    try:
        record = await use_case.execute(
            UpdateNarrativeInput(
                record_id=record_id,
                narrative_id=narrative_id,
                narrative=body.narrative,
            )
        )
    except NarrativeNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NARRATIVE_NOT_FOUND", "message": str(exc)},
        ) from None
    await session.commit()
    return stored_narrative_response(record)
