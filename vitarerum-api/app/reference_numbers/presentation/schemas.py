from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.reference_numbers.application.use_cases import PreviewReferencePolicyOutput
from app.reference_numbers.domain.models import ReferenceKind, ReferencePolicy


class PreviewReferencePolicyRequest(BaseModel):
    kind: ReferenceKind
    mask: str
    sampleDate: date


class CreateReferencePolicyRequest(BaseModel):
    kind: ReferenceKind
    mask: str


class ReferencePolicyPreviewResponse(BaseModel):
    kind: ReferenceKind
    mask: str
    sequenceScope: str
    example: str
    tokens: list[str]


class ReferencePolicyResponse(BaseModel):
    id: str
    kind: ReferenceKind
    mask: str
    sequenceScope: str
    status: str
    activeFrom: datetime | None
    activeUntil: datetime | None
    createdBy: str
    createdAt: datetime
    updatedBy: str | None
    updatedAt: datetime | None
    activatedBy: str | None
    activatedAt: datetime | None


def policy_response(policy: ReferencePolicy) -> ReferencePolicyResponse:
    return ReferencePolicyResponse(
        id=policy.id,
        kind=policy.kind,
        mask=policy.mask.value,
        sequenceScope=policy.sequence_scope.value,
        status=policy.status.value,
        activeFrom=policy.active_from,
        activeUntil=policy.active_until,
        createdBy=policy.created_by,
        createdAt=policy.created_at,
        updatedBy=policy.updated_by,
        updatedAt=policy.updated_at,
        activatedBy=policy.activated_by,
        activatedAt=policy.activated_at,
    )


def preview_response(
    preview: PreviewReferencePolicyOutput,
) -> ReferencePolicyPreviewResponse:
    return ReferencePolicyPreviewResponse(
        kind=preview.kind,
        mask=preview.mask,
        sequenceScope=preview.sequence_scope,
        example=preview.example,
        tokens=list(preview.tokens),
    )
