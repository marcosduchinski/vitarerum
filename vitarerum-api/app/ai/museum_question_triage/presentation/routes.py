"""Museum-question triage endpoints (the driving adapter).

Staff-only. Co-located as a sub-resource of the existing internal
museum-questions prefix, even though the router is physically defined under
``app/ai/`` — mirrors how ``museum_narrative``'s router lives under ``app/ai/``
but is addressed by its own resource path.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_question_triage.application.use_cases import (
    GetLatestTriageInput,
    TriageMuseumQuestionInput,
)
from app.ai.museum_question_triage.domain.ports import (
    ModelTimeout,
    ModelUnavailable,
    QuestionNotFound,
)
from app.ai.museum_question_triage.presentation.dependencies import (
    GetLatestTriageUseCase,
    TriageUseCase,
)
from app.ai.museum_question_triage.presentation.mappers import triage_response
from app.ai.museum_question_triage.presentation.schemas import TriageResponse
from app.database import get_async_session
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


@museum_question_triage_router.post(
    "/{question_id}/triage", response_model=TriageResponse
)
async def triage_museum_question(
    question_id: str,
    caller: CallerPermission,
    use_case: TriageUseCase,
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
    await session.commit()
    return triage_response(result)


@museum_question_triage_router.get(
    "/{question_id}/triage", response_model=TriageResponse
)
async def get_latest_museum_question_triage(
    question_id: str,
    caller: CallerPermission,
    use_case: GetLatestTriageUseCase,
) -> TriageResponse:
    require_staff(caller)
    result = await use_case.execute(GetLatestTriageInput(question_id=question_id))
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "TRIAGE_NOT_FOUND",
                "message": (
                    f"No triage has been run for question {question_id!r} yet."
                ),
            },
        )
    return triage_response(result)
