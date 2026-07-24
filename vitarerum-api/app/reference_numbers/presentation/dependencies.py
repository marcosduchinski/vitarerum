from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.reference_numbers.application.use_cases import (
    ActivateReferencePolicy,
    CreateReferencePolicy,
    DeactivateReferencePolicy,
    GetReferencePolicy,
    ListReferencePolicies,
    PreviewReferencePolicy,
)
from app.reference_numbers.domain.ports import ReferencePolicyRepository
from app.reference_numbers.infrastructure.repositories import (
    SqlAlchemyReferencePolicyRepository,
)

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def get_policy_repository(session: DBSession) -> ReferencePolicyRepository:
    return SqlAlchemyReferencePolicyRepository(session)


PolicyRepository = Annotated[
    ReferencePolicyRepository, Depends(get_policy_repository)
]


def get_preview_use_case() -> PreviewReferencePolicy:
    return PreviewReferencePolicy()


def get_create_use_case(repository: PolicyRepository) -> CreateReferencePolicy:
    return CreateReferencePolicy(repository)


def get_activate_use_case(repository: PolicyRepository) -> ActivateReferencePolicy:
    return ActivateReferencePolicy(repository)


def get_deactivate_use_case(repository: PolicyRepository) -> DeactivateReferencePolicy:
    return DeactivateReferencePolicy(repository)


def get_list_use_case(repository: PolicyRepository) -> ListReferencePolicies:
    return ListReferencePolicies(repository)


def get_get_use_case(repository: PolicyRepository) -> GetReferencePolicy:
    return GetReferencePolicy(repository)


PreviewUseCase = Annotated[PreviewReferencePolicy, Depends(get_preview_use_case)]
CreateUseCase = Annotated[CreateReferencePolicy, Depends(get_create_use_case)]
ActivateUseCase = Annotated[ActivateReferencePolicy, Depends(get_activate_use_case)]
DeactivateUseCase = Annotated[
    DeactivateReferencePolicy, Depends(get_deactivate_use_case)
]
ListUseCase = Annotated[ListReferencePolicies, Depends(get_list_use_case)]
GetUseCase = Annotated[GetReferencePolicy, Depends(get_get_use_case)]
