"""Museum Questions public intake and authenticated staff response endpoints."""

from __future__ import annotations

import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.museum_questions.application.use_cases import (
    AnswerMuseumQuestionInput,
    CaptchaFailed,
    CaptchaUnavailable,
    CloseMuseumQuestionInput,
    MarkMuseumQuestionOutOfScopeInput,
    RateLimitExceeded,
    SubmitMuseumQuestionInput,
)
from app.museum_questions.domain.models import (
    InvalidMuseumQuestionTransition,
    MuseumQuestion,
    MuseumQuestionNotFound,
    MuseumQuestionStatus,
)
from app.museum_questions.presentation.dependencies import (
    AnswerUseCase,
    CloseUseCase,
    EmailSender,
    GetUseCase,
    ListUseCase,
    MarkOutOfScopeUseCase,
    SubmitUseCase,
)
from app.museum_questions.presentation.schemas import (
    AnswerMuseumQuestionRequest,
    MarkOutOfScopeRequest,
    MuseumQuestionReceipt,
    MuseumQuestionResponse,
    MuseumQuestionSubmission,
    PaginatedMuseumQuestionsResponse,
)
from app.shared.dependencies import CallerPermission

router = APIRouter(prefix="/public", tags=["public-museum-questions"])
internal_router = APIRouter(prefix="/museum-questions", tags=["museum-questions"])

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limited(exc: RateLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"message": str(exc)},
        headers={"Retry-After": str(exc.retry_after)},
    )


def _not_found(question_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "MUSEUM_QUESTION_NOT_FOUND",
            "message": f"Museum question {question_id!r} was not found.",
        },
    )


def _invalid_transition(exc: InvalidMuseumQuestionTransition) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": "INVALID_MUSEUM_QUESTION_TRANSITION", "message": str(exc)},
    )


def _invalid_body(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"message": str(exc)},
    )


def _question_response(question: MuseumQuestion) -> MuseumQuestionResponse:
    return MuseumQuestionResponse(
        id=question.id,
        requesterName=question.requester_name,
        requesterEmail=question.requester_email,
        subject=question.subject,
        message=question.message,
        status=question.status.value,
        createdAt=question.created_at,
        answeredAt=question.answered_at,
        answeredBy=question.answered_by,
        answerBody=question.answer_body,
        answerSentAt=question.answer_sent_at,
        outOfScopeAt=question.out_of_scope_at,
        outOfScopeBy=question.out_of_scope_by,
        outOfScopeReason=question.out_of_scope_reason,
        outOfScopeEmailSentAt=question.out_of_scope_email_sent_at,
        closedAt=question.closed_at,
        closedBy=question.closed_by,
    )


@router.post(
    "/museum-questions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MuseumQuestionReceipt,
)
async def submit_museum_question(
    body: MuseumQuestionSubmission,
    request: Request,
    use_case: SubmitUseCase,
    session: DBSession,
) -> MuseumQuestionReceipt:
    remote_ip = _client_ip(request)
    try:
        honeypot = await use_case.admit(
            remote_ip=remote_ip,
            requester_email=str(body.requesterEmail),
            website=body.website,
            captcha_token=body.captchaToken,
        )
    except RateLimitExceeded as exc:
        raise _rate_limited(exc) from exc
    except CaptchaFailed as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": "Captcha verification failed."},
        ) from exc
    except CaptchaUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Captcha provider unreachable; please retry."},
        ) from exc
    if honeypot:
        # Accept-and-drop: same 202 shape a real submit returns, nothing persisted.
        return MuseumQuestionReceipt(email=body.requesterEmail)

    output = await use_case.persist(
        SubmitMuseumQuestionInput(
            requester_name=body.requesterName,
            requester_email=str(body.requesterEmail),
            subject=body.subject,
            message=body.message,
            captcha_token=body.captchaToken,
            website=body.website,
            remote_ip=remote_ip,
        )
    )
    await session.commit()
    return MuseumQuestionReceipt(email=output.email)


@internal_router.get("", response_model=PaginatedMuseumQuestionsResponse)
async def list_museum_questions(
    caller: CallerPermission,
    use_case: ListUseCase,
    status_filter: Annotated[
        MuseumQuestionStatus | None, Query(alias="status")
    ] = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedMuseumQuestionsResponse:
    result = await use_case.execute(caller, status=status_filter, page=page, size=size)
    return PaginatedMuseumQuestionsResponse(
        content=[_question_response(q) for q in result.content],
        page=result.page,
        size=result.size,
        totalElements=result.total,
        totalPages=math.ceil(result.total / result.size) if result.size > 0 else 0,
    )


@internal_router.get("/{question_id}", response_model=MuseumQuestionResponse)
async def get_museum_question(
    question_id: str,
    caller: CallerPermission,
    use_case: GetUseCase,
) -> MuseumQuestionResponse:
    try:
        question = await use_case.execute(caller, question_id)
    except MuseumQuestionNotFound as exc:
        raise _not_found(question_id) from exc
    return _question_response(question)


@internal_router.post("/{question_id}/answer", response_model=MuseumQuestionResponse)
async def answer_museum_question(
    question_id: str,
    body: AnswerMuseumQuestionRequest,
    caller: CallerPermission,
    use_case: AnswerUseCase,
    email_sender: EmailSender,
    session: DBSession,
) -> MuseumQuestionResponse:
    try:
        question = await use_case.execute(
            AnswerMuseumQuestionInput(
                caller=caller, question_id=question_id, answer_body=body.answerBody
            )
        )
    except MuseumQuestionNotFound as exc:
        raise _not_found(question_id) from exc
    except InvalidMuseumQuestionTransition as exc:
        raise _invalid_transition(exc) from exc
    except ValueError as exc:
        raise _invalid_body(exc) from exc
    await session.commit()
    # Send the answer only after the status change is durably committed, so
    # the citizen never receives a reply for an update that rolled back.
    await email_sender.send_answer(
        to_email=question.requester_email,
        requester_name=question.requester_name,
        subject=question.subject,
        answer_body=body.answerBody,
    )
    return _question_response(question)


@internal_router.post(
    "/{question_id}/mark-out-of-scope", response_model=MuseumQuestionResponse
)
async def mark_museum_question_out_of_scope(
    question_id: str,
    body: MarkOutOfScopeRequest,
    caller: CallerPermission,
    use_case: MarkOutOfScopeUseCase,
    email_sender: EmailSender,
    session: DBSession,
) -> MuseumQuestionResponse:
    try:
        question = await use_case.execute(
            MarkMuseumQuestionOutOfScopeInput(
                caller=caller, question_id=question_id, reason=body.reason
            )
        )
    except MuseumQuestionNotFound as exc:
        raise _not_found(question_id) from exc
    except InvalidMuseumQuestionTransition as exc:
        raise _invalid_transition(exc) from exc
    await session.commit()
    # Send only after commit — see answer_museum_question.
    await email_sender.send_out_of_scope(
        to_email=question.requester_email,
        requester_name=question.requester_name,
        subject=question.subject,
    )
    return _question_response(question)


@internal_router.patch("/{question_id}/close", response_model=MuseumQuestionResponse)
async def close_museum_question(
    question_id: str,
    caller: CallerPermission,
    use_case: CloseUseCase,
    session: DBSession,
) -> MuseumQuestionResponse:
    try:
        question = await use_case.execute(
            CloseMuseumQuestionInput(caller=caller, question_id=question_id)
        )
    except MuseumQuestionNotFound as exc:
        raise _not_found(question_id) from exc
    except InvalidMuseumQuestionTransition as exc:
        raise _invalid_transition(exc) from exc
    await session.commit()
    return _question_response(question)
