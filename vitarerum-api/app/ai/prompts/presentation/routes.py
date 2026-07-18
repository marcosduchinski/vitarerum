"""Administrative endpoints for institutional AI prompts.

V1 maps the conceptual prompt capabilities to the existing staff policy. A
future permission model can replace the `require_staff` calls at these handler
boundaries without changing the application use cases.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.ai.prompts.application.use_cases import (
    CreatePromptDraftInput,
    PromptTemplateNotFound,
    PromptVersionNotFound,
)
from app.ai.prompts.domain.models import (
    PromptInvariantError,
    PromptPurpose,
    PromptStatus,
    PublishedPromptRequired,
)
from app.ai.prompts.domain.ports import PromptPublicationConflict
from app.ai.prompts.presentation.dependencies import (
    ArchiveUseCase,
    DBSession,
    DraftUseCase,
    PublishUseCase,
    ReadTemplatesUseCase,
    ReadVersionsUseCase,
    ReadVersionUseCase,
)
from app.ai.prompts.presentation.schemas import (
    CreatePromptDraftRequest,
    PromptTemplateResponse,
    PromptTemplateVersionResponse,
    prompt_template_response,
    prompt_version_response,
)
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission

ai_prompts_router = APIRouter(prefix="/ai/prompts", tags=["ai-prompts"])


@ai_prompts_router.get("", response_model=list[PromptTemplateResponse])
async def read_ai_prompt_templates(
    caller: CallerPermission,
    use_case: ReadTemplatesUseCase,
    purpose: Annotated[PromptPurpose | None, Query()] = None,
    status_filter: Annotated[
        PromptStatus | None, Query(alias="status")
    ] = None,
) -> list[PromptTemplateResponse]:
    require_staff(caller)
    templates = await use_case.execute(purpose=purpose, status=status_filter)
    return [prompt_template_response(template) for template in templates]


@ai_prompts_router.get(
    "/{template_id}/versions", response_model=list[PromptTemplateVersionResponse]
)
async def read_ai_prompt_versions(
    template_id: str,
    caller: CallerPermission,
    use_case: ReadVersionsUseCase,
) -> list[PromptTemplateVersionResponse]:
    require_staff(caller)
    try:
        versions = await use_case.execute(template_id)
    except PromptTemplateNotFound as exc:
        raise _not_found("PROMPT_TEMPLATE_NOT_FOUND", str(exc)) from None
    return [prompt_version_response(version) for version in versions]


@ai_prompts_router.get(
    "/versions/{version_id}", response_model=PromptTemplateVersionResponse
)
async def read_ai_prompt_version(
    version_id: str,
    caller: CallerPermission,
    use_case: ReadVersionUseCase,
) -> PromptTemplateVersionResponse:
    require_staff(caller)
    try:
        version = await use_case.execute(version_id)
    except PromptVersionNotFound as exc:
        raise _not_found("PROMPT_VERSION_NOT_FOUND", str(exc)) from None
    return prompt_version_response(version)


@ai_prompts_router.post(
    "/{template_id}/versions",
    response_model=PromptTemplateVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def draft_ai_prompt_version(
    template_id: str,
    body: CreatePromptDraftRequest,
    caller: CallerPermission,
    use_case: DraftUseCase,
    session: DBSession,
) -> PromptTemplateVersionResponse:
    require_staff(caller)
    try:
        version = await use_case.execute(
            CreatePromptDraftInput(
                template_id=template_id,
                version_label=body.version_label,
                content=body.content,
                default_temperature=body.default_temperature,
                created_by=caller.id,
                source_version_id=body.source_version_id,
            )
        )
    except PromptTemplateNotFound as exc:
        raise _not_found("PROMPT_TEMPLATE_NOT_FOUND", str(exc)) from None
    except PromptVersionNotFound as exc:
        raise _not_found("PROMPT_VERSION_NOT_FOUND", str(exc)) from None
    except (PromptInvariantError, ValueError) as exc:
        raise _unprocessable("INVALID_PROMPT_DRAFT", str(exc)) from None
    await session.commit()
    return prompt_version_response(version)


@ai_prompts_router.post(
    "/versions/{version_id}/publish", response_model=PromptTemplateVersionResponse
)
async def publish_ai_prompt_version(
    version_id: str,
    caller: CallerPermission,
    use_case: PublishUseCase,
    session: DBSession,
) -> PromptTemplateVersionResponse:
    require_staff(caller)
    try:
        version = await use_case.execute(version_id, published_by=caller.id)
    except PromptTemplateNotFound as exc:
        raise _not_found("PROMPT_TEMPLATE_NOT_FOUND", str(exc)) from None
    except PromptVersionNotFound as exc:
        raise _not_found("PROMPT_VERSION_NOT_FOUND", str(exc)) from None
    except (PromptInvariantError, PromptPublicationConflict) as exc:
        raise _conflict("PROMPT_PUBLICATION_CONFLICT", str(exc)) from None
    await session.commit()
    return prompt_version_response(version)


@ai_prompts_router.post(
    "/versions/{version_id}/archive", response_model=PromptTemplateVersionResponse
)
async def archive_ai_prompt_version(
    version_id: str,
    caller: CallerPermission,
    use_case: ArchiveUseCase,
    session: DBSession,
) -> PromptTemplateVersionResponse:
    require_staff(caller)
    try:
        version = await use_case.execute(version_id)
    except PromptVersionNotFound as exc:
        raise _not_found("PROMPT_VERSION_NOT_FOUND", str(exc)) from None
    except PublishedPromptRequired as exc:
        raise _conflict("PUBLISHED_PROMPT_REQUIRED", str(exc)) from None
    await session.commit()
    return prompt_version_response(version)


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
