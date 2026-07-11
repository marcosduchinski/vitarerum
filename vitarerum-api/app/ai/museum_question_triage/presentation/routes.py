"""Museum-question triage endpoints (the driving adapter).

Staff-only. Co-located as a sub-resource of the existing internal
museum-questions prefix, even though the router is physically defined under
``app/ai/`` — mirrors how ``museum_narrative``'s router lives under ``app/ai/``
but is addressed by its own resource path.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_question_triage.application.use_cases import (
    ClassifyPendingUseCategory,
    ClassifyPendingUseCategoryInput,
    CreatePendingUseCategoryClassificationInput,
    GetLatestTriageInput,
    OverrideTriageVerdictInput,
    SyncTriageSearchTermsInput,
    TriageMuseumQuestionInput,
)
from app.ai.museum_question_triage.domain.models import (
    ClassifierKind,
    MessageClassification,
    TriageId,
    TriageVerdict,
)
from app.ai.museum_question_triage.domain.ports import (
    ModelTimeout,
    ModelUnavailable,
    QuestionNotFound,
    TriageNotFound,
    TriageNotInScope,
    TriageTermValidationError,
)
from app.ai.museum_question_triage.infrastructure.model_ollama import (
    OllamaTriageAdapter,
)
from app.ai.museum_question_triage.infrastructure.museum_questions_acl import (
    MuseumQuestionAdapter,
)
from app.ai.museum_question_triage.infrastructure.repositories import (
    SqlAlchemyMessageClassificationRepository,
    SqlAlchemyTriageRepository,
)
from app.ai.museum_question_triage.presentation.dependencies import (
    ClassificationRepository,
    CreatePendingUseCategoryUseCase,
    GetLatestTriageUseCase,
    OverrideVerdictUseCase,
    SyncSearchTermsUseCase,
    TriageUseCase,
)
from app.ai.museum_question_triage.presentation.mappers import triage_response
from app.ai.museum_question_triage.presentation.schemas import (
    OverrideTriageVerdictRequest,
    TriageResponse,
    TriageSearchTermsRequest,
)
from app.config import settings
from app.database import async_session_factory, get_async_session
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

museum_question_triage_router = APIRouter(
    prefix="/museum-questions", tags=["museum-question-triage"]
)


def _not_found(question_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "MUSEUM_QUESTION_NOT_FOUND",
            "message": f"Museum question {question_id!r} was not found.",
        },
    )


def _triage_not_found(question_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "TRIAGE_NOT_FOUND",
            "message": f"No triage has been run for question {question_id!r} yet.",
        },
    )


async def _current_llm_use_category_classification(
    classification_repository: ClassificationRepository, triage_id: str
) -> MessageClassification | None:
    return await classification_repository.get_current_by_triage(
        TriageId(triage_id), ClassifierKind.LLM
    )


async def _classify_use_categories_background(classification_id: str) -> None:
    async with async_session_factory() as session:
        use_case = ClassifyPendingUseCategory(
            MuseumQuestionAdapter(session),
            OllamaTriageAdapter(
                base_url=settings.ollama_base_url,
                model=settings.triage_model,
                timeout_seconds=settings.triage_timeout_seconds,
                api_key=settings.ollama_api_key,
            ),
            SqlAlchemyTriageRepository(session),
            SqlAlchemyMessageClassificationRepository(session),
        )
        try:
            await use_case.execute(
                ClassifyPendingUseCategoryInput(classification_id=classification_id)
            )
        except Exception:
            await session.rollback()
            raise
        await session.commit()


@museum_question_triage_router.post(
    "/{question_id}/triage", response_model=TriageResponse
)
async def triage_museum_question(
    question_id: str,
    background_tasks: BackgroundTasks,
    caller: CallerPermission,
    use_case: TriageUseCase,
    create_pending_use_category: CreatePendingUseCategoryUseCase,
    classification_repository: ClassificationRepository,
    session: DBSession,
) -> TriageResponse:
    require_staff(caller)
    try:
        result = await use_case.execute(
            TriageMuseumQuestionInput(question_id=question_id, caller=caller)
        )
    except QuestionNotFound as exc:
        raise _not_found(question_id) from exc
    except ModelUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "MODEL_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except ModelTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error": "MODEL_TIMEOUT", "message": str(exc)},
        ) from exc
    pending_classification_id: str | None = None
    if settings.use_category_classification_enabled:
        pending = await create_pending_use_category.execute(
            CreatePendingUseCategoryClassificationInput(triage_id=result.id)
        )
        pending_classification_id = pending.id
    await session.commit()
    if pending_classification_id is not None:
        background_tasks.add_task(
            _classify_use_categories_background, pending_classification_id
        )
    use_category_classification = await _current_llm_use_category_classification(
        classification_repository, result.id
    )
    return triage_response(result, use_category_classification)


@museum_question_triage_router.get(
    "/{question_id}/triage", response_model=TriageResponse
)
async def get_latest_museum_question_triage(
    question_id: str,
    caller: CallerPermission,
    use_case: GetLatestTriageUseCase,
    classification_repository: ClassificationRepository,
) -> TriageResponse:
    require_staff(caller)
    result = await use_case.execute(GetLatestTriageInput(question_id=question_id))
    if result is None:
        raise _triage_not_found(question_id)
    use_category_classification = await _current_llm_use_category_classification(
        classification_repository, result.id
    )
    return triage_response(result, use_category_classification)


@museum_question_triage_router.patch(
    "/{question_id}/triage/verdict", response_model=TriageResponse
)
async def override_triage_verdict(
    question_id: str,
    body: OverrideTriageVerdictRequest,
    caller: CallerPermission,
    use_case: OverrideVerdictUseCase,
    classification_repository: ClassificationRepository,
    session: DBSession,
) -> TriageResponse:
    """Staff contesting the AI's scope verdict — see
    docs/plans/museum-questions-ai-triage-refinements-plan.md, checkpoint 1."""
    require_staff(caller)
    try:
        result = await use_case.execute(
            OverrideTriageVerdictInput(
                question_id=question_id,
                verdict=TriageVerdict(body.verdict),
                caller=caller,
            )
        )
    except TriageNotFound as exc:
        raise _triage_not_found(question_id) from exc
    except QuestionNotFound as exc:
        raise _not_found(question_id) from exc
    except ModelUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "MODEL_UNAVAILABLE", "message": str(exc)},
        ) from exc
    except ModelTimeout as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"error": "MODEL_TIMEOUT", "message": str(exc)},
        ) from exc
    await session.commit()
    use_category_classification = await _current_llm_use_category_classification(
        classification_repository, result.id
    )
    return triage_response(result, use_category_classification)


@museum_question_triage_router.put(
    "/{question_id}/triage/search-terms", response_model=TriageResponse
)
async def sync_triage_search_terms(
    question_id: str,
    body: TriageSearchTermsRequest,
    caller: CallerPermission,
    use_case: SyncSearchTermsUseCase,
    classification_repository: ClassificationRepository,
    session: DBSession,
) -> TriageResponse:
    """Staff editing/adding/removing extracted search terms — see
    docs/plans/museum-questions-ai-triage-refinements-plan.md, checkpoint 2.
    Rejects with 409 while the triage is OUT_OF_SCOPE (valid payload, wrong
    state) and 422 on validation failures (field too long, too many terms)."""
    require_staff(caller)
    try:
        result = await use_case.execute(
            SyncTriageSearchTermsInput(
                question_id=question_id,
                terms=[(term.english, term.portuguese) for term in body.terms],
                caller=caller,
            )
        )
    except TriageNotFound as exc:
        raise _triage_not_found(question_id) from exc
    except TriageNotInScope as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "TRIAGE_NOT_IN_SCOPE", "message": str(exc)},
        ) from exc
    except TriageTermValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "INVALID_SEARCH_TERMS", "message": str(exc)},
        ) from exc
    await session.commit()
    use_category_classification = await _current_llm_use_category_classification(
        classification_repository, result.id
    )
    return triage_response(result, use_category_classification)
