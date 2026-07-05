"""Public, unauthenticated Museum Questions intake endpoint.

Takes NO credentials. Validation/captcha/rate-limit are enforced in the use
case; errors surface in the shared ``{ "message", "fieldErrors"? }`` shape via
the global handlers in ``app.main`` (mirrors ``public_submission``'s route).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.museum_questions.application.use_cases import (
    CaptchaFailed,
    CaptchaUnavailable,
    RateLimitExceeded,
    SubmitMuseumQuestionInput,
)
from app.museum_questions.presentation.dependencies import SubmitUseCase
from app.museum_questions.presentation.schemas import (
    MuseumQuestionReceipt,
    MuseumQuestionSubmission,
)

router = APIRouter(prefix="/public", tags=["public-museum-questions"])

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limited(exc: RateLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"message": str(exc)},
        headers={"Retry-After": str(exc.retry_after)},
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
