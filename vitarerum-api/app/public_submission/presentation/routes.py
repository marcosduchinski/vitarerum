"""Public, unauthenticated proposal submission endpoints (double opt-in).

These take NO credentials. Validation/captcha/rate-limit are enforced in the use
cases; errors surface in the shared ``{ "message", "fieldErrors"? }`` shape via
the global handlers in ``app.main``. The confirm endpoint returns ``200`` for all
friendly outcomes (CONFIRMED/ALREADY_CONFIRMED/EXPIRED/INVALID) so the public SPA
can render a message; only rate limiting / unexpected faults are non-2xx.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.public_submission.application.use_cases import (
    CaptchaFailed,
    CaptchaUnavailable,
    RateLimitExceeded,
    SubmitPublicProposalInput,
)
from app.public_submission.presentation.dependencies import (
    ConfirmUseCase,
    EmailSender,
    SubmitUseCase,
)
from app.public_submission.presentation.schemas import (
    PublicConfirmationRequest,
    PublicConfirmationResult,
    PublicProposalSubmission,
    PublicSubmissionReceipt,
)

router = APIRouter(prefix="/public", tags=["public-proposals"])

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
    "/proposals",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PublicSubmissionReceipt,
)
async def submit_public_proposal(
    body: PublicProposalSubmission,
    request: Request,
    use_case: SubmitUseCase,
    email_sender: EmailSender,
    session: DBSession,
) -> PublicSubmissionReceipt:
    try:
        output = await use_case.execute(
            SubmitPublicProposalInput(
                citizen_name=body.citizenName,
                citizen_email=str(body.citizenEmail),
                subject=body.subject,
                body=body.body,
                consent=body.consent,
                captcha_token=body.captchaToken,
                website=body.website,
                remote_ip=_client_ip(request),
            )
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
    await session.commit()
    # Send the confirmation link only after the pending row is durably committed,
    # so the citizen never receives a token that was rolled back. Skipped for the
    # honeypot path (token is None).
    if output.token is not None:
        await email_sender.send(output.email, output.name, output.token)
    return PublicSubmissionReceipt(email=output.email)


@router.post("/proposals/confirm", response_model=PublicConfirmationResult)
async def confirm_public_proposal(
    body: PublicConfirmationRequest,
    request: Request,
    use_case: ConfirmUseCase,
    session: DBSession,
) -> PublicConfirmationResult:
    try:
        result = await use_case.execute(body.token, _client_ip(request))
    except RateLimitExceeded as exc:
        raise _rate_limited(exc) from exc
    await session.commit()
    return PublicConfirmationResult(
        status=result.status, referenceNumber=result.reference_number
    )
