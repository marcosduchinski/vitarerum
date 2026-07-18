from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.application.use_cases import (
    ArchivePromptVersion,
    CreatePromptDraft,
    GetPromptVersion,
    ListPromptTemplates,
    ListPromptVersions,
    PublishPromptVersion,
)
from app.ai.prompts.domain.ports import PromptTemplateRepository
from app.ai.prompts.infrastructure.repositories import (
    SqlAlchemyPromptTemplateRepository,
)
from app.database import get_async_session

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def get_prompt_repository(session: DBSession) -> PromptTemplateRepository:
    return SqlAlchemyPromptTemplateRepository(session)


Repository = Annotated[PromptTemplateRepository, Depends(get_prompt_repository)]


def get_read_templates_use_case(repository: Repository) -> ListPromptTemplates:
    return ListPromptTemplates(repository)


def get_read_versions_use_case(repository: Repository) -> ListPromptVersions:
    return ListPromptVersions(repository)


def get_read_version_use_case(repository: Repository) -> GetPromptVersion:
    return GetPromptVersion(repository)


def get_draft_use_case(repository: Repository) -> CreatePromptDraft:
    return CreatePromptDraft(repository)


def get_publish_use_case(repository: Repository) -> PublishPromptVersion:
    return PublishPromptVersion(repository)


def get_archive_use_case(repository: Repository) -> ArchivePromptVersion:
    return ArchivePromptVersion(repository)


ReadTemplatesUseCase = Annotated[
    ListPromptTemplates, Depends(get_read_templates_use_case)
]
ReadVersionsUseCase = Annotated[ListPromptVersions, Depends(get_read_versions_use_case)]
ReadVersionUseCase = Annotated[GetPromptVersion, Depends(get_read_version_use_case)]
DraftUseCase = Annotated[CreatePromptDraft, Depends(get_draft_use_case)]
PublishUseCase = Annotated[PublishPromptVersion, Depends(get_publish_use_case)]
ArchiveUseCase = Annotated[ArchivePromptVersion, Depends(get_archive_use_case)]
