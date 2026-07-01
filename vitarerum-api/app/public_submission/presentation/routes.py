"""Public, unauthenticated proposal submission endpoints (double opt-in).

These take NO credentials. Validation/captcha/rate-limit are enforced in the use
cases; errors surface in the shared ``{ "message", "fieldErrors"? }`` shape via
the global handlers in ``app.main``. The confirm endpoint returns ``200`` for all
friendly outcomes (CONFIRMED/ALREADY_CONFIRMED/EXPIRED/INVALID) so the public SPA
can render a message; only rate limiting / unexpected faults are non-2xx.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.public_submission.application.use_cases import (
    CaptchaFailed,
    CaptchaUnavailable,
    RateLimitExceeded,
    SubmitPublicProposalInput,
    UploadedDocument,
)
from app.public_submission.domain.models import (
    MAX_PUBLIC_DOCUMENTS,
    MIN_PUBLIC_DOCUMENTS,
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

PUBLIC_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
_UPLOAD_CHUNK = 1024 * 1024


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limited(exc: RateLimitExceeded) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"message": str(exc)},
        headers={"Retry-After": str(exc.retry_after)},
    )


async def _read_public_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > PUBLIC_UPLOAD_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail={
                    "error": "FILE_TOO_LARGE",
                    "message": (
                        "Each public submission document must be 10 MB or smaller."
                    ),
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _is_docx(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return "[Content_Types].xml" in set(archive.namelist())
    except zipfile.BadZipFile:
        return False


def _ensure_allowed_public_file(content: bytes) -> None:
    if content.startswith(b"%PDF-"):
        return
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return
    if content.startswith(b"\xff\xd8\xff"):
        return
    if _is_docx(content):
        return
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail={
            "error": "UNSUPPORTED_FILE_TYPE",
            "message": "Only PDF, JPG, PNG, and DOCX files are accepted.",
        },
    )


async def _uploaded_documents(files: list[UploadFile]) -> list[UploadedDocument]:
    if len(files) < MIN_PUBLIC_DOCUMENTS or len(files) > MAX_PUBLIC_DOCUMENTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Validation failed",
                "errors": [
                    {
                        "field": "documents",
                        "message": (
                            f"Attach between {MIN_PUBLIC_DOCUMENTS} and "
                            f"{MAX_PUBLIC_DOCUMENTS} supporting documents."
                        ),
                    }
                ],
            },
        )
    documents: list[UploadedDocument] = []
    for file in files:
        content = await _read_public_upload(file)
        _ensure_allowed_public_file(content)
        documents.append(
            UploadedDocument(file_name=file.filename or "document", content=content)
        )
    return documents


@router.post(
    "/proposals",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=PublicSubmissionReceipt,
)
async def submit_public_proposal(
    citizenName: Annotated[str, Form(min_length=1, max_length=120)],
    citizenEmail: Annotated[str, Form(max_length=180)],
    subject: Annotated[str, Form(min_length=1, max_length=160)],
    body: Annotated[str, Form(min_length=1, max_length=4000)],
    useType: Annotated[str, Form()],
    proposedBeginDate: Annotated[date, Form()],
    proposedEndDate: Annotated[date, Form()],
    consent: Annotated[bool, Form()],
    captchaToken: Annotated[str, Form(min_length=1, max_length=2048)],
    request: Request,
    use_case: SubmitUseCase,
    email_sender: EmailSender,
    session: DBSession,
    documents: Annotated[list[UploadFile], File(default_factory=list)],
    website: Annotated[str, Form(max_length=255)] = "",
) -> PublicSubmissionReceipt:
    try:
        form = PublicProposalSubmission(
            citizenName=citizenName,
            citizenEmail=citizenEmail,
            subject=subject,
            body=body,
            useType=useType,
            proposedBeginDate=proposedBeginDate,
            proposedEndDate=proposedEndDate,
            consent=consent,
            captchaToken=captchaToken,
            website=website,
        )
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc

    remote_ip = _client_ip(request)
    # Run the rate-limit / captcha gates BEFORE buffering any upload, so abusive
    # traffic is shed without the server first reading up to 5×10 MB into memory.
    try:
        honeypot = await use_case.admit(
            remote_ip=remote_ip,
            citizen_email=str(form.citizenEmail),
            website=form.website,
            captcha_token=form.captchaToken,
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
        # Accept-and-drop: same 202 shape a real submit returns, no files buffered.
        return PublicSubmissionReceipt(email=str(form.citizenEmail))

    uploaded_documents = await _uploaded_documents(documents)
    output = await use_case.persist(
        SubmitPublicProposalInput(
            citizen_name=form.citizenName,
            citizen_email=str(form.citizenEmail),
            subject=form.subject,
            body=form.body,
            use_type=form.useType,
            consent=form.consent,
            captcha_token=form.captchaToken,
            website=form.website,
            remote_ip=remote_ip,
            proposed_begin_date=form.proposedBeginDate,
            proposed_end_date=form.proposedEndDate,
            documents=uploaded_documents,
        )
    )
    try:
        await session.commit()
    except Exception:
        await use_case.discard_uploaded_files(output.file_references)
        raise
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
