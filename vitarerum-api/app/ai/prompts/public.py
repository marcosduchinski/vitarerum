from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts.application.use_cases import (
    ActivePromptNotFound,
    GetPromptTemplate,
    GetPromptVersion,
    GetPublishedPrompt,
    PromptTemplateNotFound,
    PromptVersionNotFound,
)
from app.ai.prompts.domain.models import (
    PromptPurpose,
    PromptStatus,
    PromptTemplate,
    PromptTemplateVersion,
)
from app.ai.prompts.domain.ports import PromptPublicationConflict


async def get_published_prompt(
    session: AsyncSession, purpose: PromptPurpose, key: str
) -> PromptTemplateVersion:
    from app.ai.prompts.infrastructure.repositories import (
        SqlAlchemyPromptTemplateRepository,
    )

    return await GetPublishedPrompt(
        SqlAlchemyPromptTemplateRepository(session)
    ).execute(purpose=purpose, key=key)


async def get_prompt_template(
    session: AsyncSession, purpose: PromptPurpose, key: str
) -> PromptTemplate:
    from app.ai.prompts.infrastructure.repositories import (
        SqlAlchemyPromptTemplateRepository,
    )

    return await GetPromptTemplate(SqlAlchemyPromptTemplateRepository(session)).execute(
        purpose=purpose, key=key
    )


async def get_prompt_version(
    session: AsyncSession, version_id: str
) -> PromptTemplateVersion:
    from app.ai.prompts.infrastructure.repositories import (
        SqlAlchemyPromptTemplateRepository,
    )

    return await GetPromptVersion(SqlAlchemyPromptTemplateRepository(session)).execute(
        version_id
    )


__all__ = [
    "ActivePromptNotFound",
    "PromptPurpose",
    "PromptStatus",
    "PromptTemplate",
    "PromptTemplateNotFound",
    "PromptTemplateVersion",
    "PromptPublicationConflict",
    "PromptVersionNotFound",
    "get_prompt_template",
    "get_prompt_version",
    "get_published_prompt",
]
