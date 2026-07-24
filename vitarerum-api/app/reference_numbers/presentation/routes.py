from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.reference_numbers.application.use_cases import ReferencePolicyNotFound
from app.reference_numbers.domain.models import (
    InvalidReferencePolicyTransition,
    ReferenceKind,
)
from app.reference_numbers.domain.ports import ActiveReferencePolicyConflict
from app.reference_numbers.presentation.dependencies import (
    ActivateUseCase,
    CreateUseCase,
    DBSession,
    DeactivateUseCase,
    GetUseCase,
    ListUseCase,
    PreviewUseCase,
)
from app.reference_numbers.presentation.schemas import (
    CreateReferencePolicyRequest,
    PreviewReferencePolicyRequest,
    ReferencePolicyPreviewResponse,
    ReferencePolicyResponse,
    policy_response,
    preview_response,
)
from app.shared.dependencies import CallerPermission

reference_policies_router = APIRouter(
    prefix="/admin/reference-number-policies",
    tags=["reference-number-policies"],
)


@reference_policies_router.get("", response_model=list[ReferencePolicyResponse])
async def list_reference_policies(
    caller: CallerPermission,
    use_case: ListUseCase,
    kind: Annotated[ReferenceKind | None, Query()] = None,
) -> list[ReferencePolicyResponse]:
    policies = await use_case.execute(caller=caller, kind=kind)
    return [policy_response(policy) for policy in policies]


@reference_policies_router.post(
    "/preview", response_model=ReferencePolicyPreviewResponse
)
async def preview_reference_policy(
    body: PreviewReferencePolicyRequest,
    caller: CallerPermission,
    use_case: PreviewUseCase,
) -> ReferencePolicyPreviewResponse:
    try:
        preview = use_case.execute(
            kind=body.kind, mask=body.mask, sample_date=body.sampleDate, caller=caller
        )
    except ValueError as exc:
        raise _unprocessable("INVALID_REFERENCE_MASK", str(exc)) from None
    return preview_response(preview)


@reference_policies_router.post(
    "",
    response_model=ReferencePolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reference_policy(
    body: CreateReferencePolicyRequest,
    caller: CallerPermission,
    use_case: CreateUseCase,
    session: DBSession,
) -> ReferencePolicyResponse:
    try:
        policy = await use_case.execute(kind=body.kind, mask=body.mask, caller=caller)
    except ValueError as exc:
        raise _unprocessable("INVALID_REFERENCE_MASK", str(exc)) from None
    await session.commit()
    return policy_response(policy)


@reference_policies_router.get(
    "/{policy_id}", response_model=ReferencePolicyResponse
)
async def get_reference_policy(
    policy_id: str,
    caller: CallerPermission,
    use_case: GetUseCase,
) -> ReferencePolicyResponse:
    try:
        policy = await use_case.execute(policy_id=policy_id, caller=caller)
    except ReferencePolicyNotFound as exc:
        raise _not_found("REFERENCE_POLICY_NOT_FOUND", str(exc)) from None
    return policy_response(policy)


@reference_policies_router.post(
    "/{policy_id}/activate", response_model=ReferencePolicyResponse
)
async def activate_reference_policy(
    policy_id: str,
    caller: CallerPermission,
    use_case: ActivateUseCase,
    session: DBSession,
) -> ReferencePolicyResponse:
    try:
        policy = await use_case.execute(policy_id=policy_id, caller=caller)
    except ReferencePolicyNotFound as exc:
        raise _not_found("REFERENCE_POLICY_NOT_FOUND", str(exc)) from None
    except ActiveReferencePolicyConflict as exc:
        raise _conflict("ACTIVE_REFERENCE_POLICY_CONFLICT", str(exc)) from None
    except InvalidReferencePolicyTransition as exc:
        raise _conflict("INVALID_REFERENCE_POLICY_TRANSITION", str(exc)) from None
    await session.commit()
    return policy_response(policy)


@reference_policies_router.post(
    "/{policy_id}/deactivate", response_model=ReferencePolicyResponse
)
async def deactivate_reference_policy(
    policy_id: str,
    caller: CallerPermission,
    use_case: DeactivateUseCase,
    session: DBSession,
) -> ReferencePolicyResponse:
    try:
        policy = await use_case.execute(policy_id=policy_id, caller=caller)
    except ReferencePolicyNotFound as exc:
        raise _not_found("REFERENCE_POLICY_NOT_FOUND", str(exc)) from None
    except InvalidReferencePolicyTransition as exc:
        raise _conflict("INVALID_REFERENCE_POLICY_TRANSITION", str(exc)) from None
    await session.commit()
    return policy_response(policy)


def _not_found(error: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": error, "message": message},
    )


def _conflict(error: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": error, "message": message},
    )


def _unprocessable(error: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error": error, "message": message},
    )
