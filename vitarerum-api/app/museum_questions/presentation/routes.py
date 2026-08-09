"""Museum Questions public intake and authenticated staff response endpoints."""

from __future__ import annotations

import math
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.config import settings
from app.database import get_async_session
from app.identity.public import GroupName, PermissionReader, PermissionView
from app.museum_questions.application.read_models import MuseumQuestionListItem
from app.museum_questions.application.use_cases import (
    AnswerMuseumQuestionInput,
    CaptchaFailed,
    CaptchaUnavailable,
    CloseMuseumQuestionInput,
    ForwardMuseumQuestionInput,
    MarkMuseumQuestionOutOfScopeInput,
    RateLimitExceeded,
    SubmitMuseumQuestionInput,
    UploadedMuseumQuestionImage,
)
from app.museum_questions.domain.models import (
    InvalidMuseumQuestionTransition,
    MuseumQuestion,
    MuseumQuestionAttachment,
    MuseumQuestionNotFound,
    MuseumQuestionStatus,
)
from app.museum_questions.presentation.dependencies import (
    AnswerUseCase,
    CloseUseCase,
    EmailSender,
    ForwardUseCase,
    GetUseCase,
    ListUseCase,
    MarkOutOfScopeUseCase,
    MuseumQuestionNotificationDispatch,
    MuseumQuestionNotificationEmailRecipients,
    MuseumQuestionNotificationRecipients,
    QuestionFileStorage,
    SubmitUseCase,
    distinct_email_recipients,
    get_reader,
)
from app.museum_questions.presentation.schemas import (
    AnswerMuseumQuestionRequest,
    ForwardMuseumQuestionRequest,
    MarkOutOfScopeRequest,
    MuseumQuestionAttachmentResponse,
    MuseumQuestionDetailResponse,
    MuseumQuestionListItemResponse,
    MuseumQuestionReceipt,
    MuseumQuestionSubmission,
    PaginatedMuseumQuestionsResponse,
    PermissionDetail,
    UserSummary,
)
from app.notifications.public import NotificationKind, RelatedResourceType
from app.shared.dependencies import CallerPermission
from app.shared.kernel import PermissionId
from app.shared.uploads import (
    ALLOWED_IMAGE_MAX_BYTES,
    ALLOWED_IMAGE_MAX_COUNT,
    ALLOWED_IMAGE_TOTAL_MAX_BYTES,
    content_disposition_attachment,
    ensure_allowed_image,
    read_upload_capped,
    safe_basename,
)

router = APIRouter(prefix="/public", tags=["public-museum-questions"])
internal_router = APIRouter(prefix="/museum-questions", tags=["museum-questions"])

DBSession = Annotated[AsyncSession, Depends(get_async_session)]
PermissionReaderDep = Annotated[PermissionReader, Depends(get_reader)]
FORWARD_TARGET_GROUPS = (GroupName.CURATORIAL, GroupName.COLLECTIONS_MANAGEMENT)


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


def _attachment_not_found(attachment_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "MUSEUM_QUESTION_ATTACHMENT_NOT_FOUND",
            "message": f"Museum question attachment {attachment_id!r} was not found.",
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


def _attachment_response(
    attachment: MuseumQuestionAttachment,
) -> MuseumQuestionAttachmentResponse:
    return MuseumQuestionAttachmentResponse(
        id=attachment.id,
        fileName=attachment.file_name,
        contentType=attachment.content_type,
        sizeBytes=attachment.size_bytes,
        createdAt=attachment.created_at,
    )


def _permission_detail(view: PermissionView | None) -> PermissionDetail | None:
    if view is None:
        return None
    return PermissionDetail(
        permissionId=view.permission_id,
        user=UserSummary(id=view.user.id, name=view.user.name, email=view.user.email),
        group=view.group,
    )


async def _hydrate_permission_detail(
    permission_id: str | None,
    reader: PermissionReader,
) -> PermissionDetail | None:
    if permission_id is None:
        return None
    return _permission_detail(await reader.get_detail(PermissionId(permission_id)))


async def _require_forward_target(
    permission_id: PermissionId,
    reader: PermissionReader,
) -> PermissionView:
    view = await reader.get_detail(permission_id)
    if view is None or view.group not in FORWARD_TARGET_GROUPS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "INVALID_PERMISSION_TARGET",
                "message": (
                    "Forward target must be a curatorial or collections "
                    "management permission."
                ),
            },
        )
    return view


def _question_list_item_response(
    item: MuseumQuestionListItem,
) -> MuseumQuestionListItemResponse:
    question = item.question
    return MuseumQuestionListItemResponse(
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
        assignedTo=_permission_detail(item.assigned_to),
        attachmentCount=item.attachment_count,
    )


async def _question_detail_response(
    question: MuseumQuestion,
    reader: PermissionReader,
) -> MuseumQuestionDetailResponse:
    return MuseumQuestionDetailResponse(
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
        assignedTo=await _hydrate_permission_detail(question.assigned_to, reader),
        attachments=[
            _attachment_response(attachment)
            for attachment in question.attachments or []
        ],
    )


def _validation_failed(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={
            "message": "Validation failed",
            "errors": [{"field": field, "message": message}],
        },
    )


def _payload_too_large(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail={"error": "FILE_TOO_LARGE", "message": message},
    )


def _content_type(request: Request) -> str:
    return request.headers.get("content-type", "").lower()


async def _submission_from_request(
    request: Request,
) -> tuple[MuseumQuestionSubmission, list[StarletteUploadFile]]:
    content_type = _content_type(request)
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        files = [
            value
            for value in form.getlist("attachments")
            if isinstance(value, StarletteUploadFile) and value.filename
        ]
        raw: dict[str, Any] = {}
        for field in (
            "requesterName",
            "requesterEmail",
            "subject",
            "message",
            "consent",
            "captchaToken",
            "website",
        ):
            value = form.get(field)
            if value is not None and not isinstance(value, StarletteUploadFile):
                raw[field] = value
        if raw.get("consent") == "true":
            raw["consent"] = True
    else:
        try:
            raw = await request.json()
        except Exception as exc:
            raise RequestValidationError(
                [
                    {
                        "type": "json_invalid",
                        "loc": ("body",),
                        "msg": "Invalid JSON body",
                        "input": None,
                    }
                ]
            ) from exc
        if not isinstance(raw, dict):
            raise RequestValidationError(
                [
                    {
                        "type": "model_attributes_type",
                        "loc": ("body",),
                        "msg": "Input should be an object",
                        "input": raw,
                    }
                ]
            )
        files = []
    try:
        return MuseumQuestionSubmission(**raw), files
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


async def _uploaded_images(
    files: list[StarletteUploadFile],
    *,
    total_limit: int = ALLOWED_IMAGE_TOTAL_MAX_BYTES,
) -> list[UploadedMuseumQuestionImage]:
    if len(files) > ALLOWED_IMAGE_MAX_COUNT:
        raise _validation_failed(
            "attachments", f"Attach at most {ALLOWED_IMAGE_MAX_COUNT} images."
        )
    total = 0
    images: list[UploadedMuseumQuestionImage] = []
    for file in files:
        try:
            content = await read_upload_capped(file, limit=ALLOWED_IMAGE_MAX_BYTES)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_413_CONTENT_TOO_LARGE:
                raise _payload_too_large(
                    "Each museum question image must be 5 MB or smaller."
                ) from exc
            raise
        content_type, extension = ensure_allowed_image(content)
        total += len(content)
        if total > total_limit:
            raise _payload_too_large(
                "Museum question image attachments must be 25 MB or smaller in total."
            )
        images.append(
            UploadedMuseumQuestionImage(
                file_name=safe_basename(file.filename or "image", default="image"),
                content=content,
                content_type=content_type,
                extension=extension,
            )
        )
    return images


@router.post(
    "/museum-questions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MuseumQuestionReceipt,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": MuseumQuestionSubmission.model_json_schema()
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "requesterName": {"type": "string"},
                            "requesterEmail": {"type": "string", "format": "email"},
                            "subject": {"type": "string"},
                            "message": {"type": "string"},
                            "consent": {"type": "boolean"},
                            "captchaToken": {"type": "string"},
                            "website": {"type": "string"},
                            "attachments": {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                            },
                        },
                        "required": [
                            "requesterName",
                            "requesterEmail",
                            "subject",
                            "message",
                            "consent",
                            "captchaToken",
                        ],
                    }
                },
            }
        }
    },
)
async def submit_museum_question(
    request: Request,
    use_case: SubmitUseCase,
    notification_dispatcher: MuseumQuestionNotificationDispatch,
    notification_recipients: MuseumQuestionNotificationRecipients,
    notification_email_recipients: MuseumQuestionNotificationEmailRecipients,
    email_sender: EmailSender,
    session: DBSession,
) -> MuseumQuestionReceipt:
    body, files = await _submission_from_request(request)
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

    uploaded_images = await _uploaded_images(files)
    output = await use_case.persist(
        SubmitMuseumQuestionInput(
            requester_name=body.requesterName,
            requester_email=str(body.requesterEmail),
            subject=body.subject,
            message=body.message,
            captcha_token=body.captchaToken,
            website=body.website,
            remote_ip=remote_ip,
            attachments=uploaded_images,
        )
    )
    if output.question_id is not None:
        await notification_dispatcher.notify_many(
            recipient_permission_ids=[
                PermissionId(recipient.permission_id)
                for recipient in notification_recipients
            ],
            kind=NotificationKind.MUSEUM_QUESTION_SUBMITTED,
            triggered_by=None,
            related_resource_type=RelatedResourceType.MUSEUM_QUESTION,
            related_resource_id=output.question_id,
            related_resource_label=body.subject,
            note=f"Submitted by {body.requesterName} <{body.requesterEmail}>",
        )
    try:
        await session.commit()
    except Exception:
        await use_case.discard_uploaded_files(output.file_references)
        raise
    if output.question_id is not None:
        link = f"{settings.public_origin}/p/museum-questions/{output.question_id}"
        for recipient in distinct_email_recipients(notification_email_recipients):
            await email_sender.send_question_submitted(
                to_email=recipient.user.email,
                recipient_name=recipient.user.name,
                requester_name=body.requesterName,
                subject=body.subject,
                link=link,
            )
    return MuseumQuestionReceipt(email=output.email)


@internal_router.get("", response_model=PaginatedMuseumQuestionsResponse)
async def list_museum_questions(
    caller: CallerPermission,
    use_case: ListUseCase,
    status_filter: Annotated[MuseumQuestionStatus | None, Query(alias="status")] = None,
    requester_email: Annotated[str | None, Query(alias="requesterEmail")] = None,
    assigned_to: Annotated[str | None, Query(alias="assignedTo")] = None,
    unassigned_only: Annotated[bool, Query(alias="unassignedOnly")] = False,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedMuseumQuestionsResponse:
    result = await use_case.execute(
        caller,
        status=status_filter,
        requester_email=requester_email,
        assigned_to=assigned_to,
        unassigned_only=unassigned_only,
        page=page,
        size=size,
    )
    return PaginatedMuseumQuestionsResponse(
        content=[_question_list_item_response(item) for item in result.content],
        page=result.page,
        size=result.size,
        totalElements=result.total,
        totalPages=math.ceil(result.total / result.size) if result.size > 0 else 0,
    )


@internal_router.get("/{question_id}", response_model=MuseumQuestionDetailResponse)
async def get_museum_question(
    question_id: str,
    caller: CallerPermission,
    use_case: GetUseCase,
    reader: PermissionReaderDep,
) -> MuseumQuestionDetailResponse:
    try:
        question = await use_case.execute(caller, question_id)
    except MuseumQuestionNotFound as exc:
        raise _not_found(question_id) from exc
    return await _question_detail_response(question, reader)


@internal_router.post(
    "/{question_id}/answer", response_model=MuseumQuestionDetailResponse
)
async def answer_museum_question(
    question_id: str,
    body: AnswerMuseumQuestionRequest,
    caller: CallerPermission,
    use_case: AnswerUseCase,
    email_sender: EmailSender,
    session: DBSession,
    reader: PermissionReaderDep,
) -> MuseumQuestionDetailResponse:
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
    return await _question_detail_response(question, reader)


@internal_router.post(
    "/{question_id}/mark-out-of-scope", response_model=MuseumQuestionDetailResponse
)
async def mark_museum_question_out_of_scope(
    question_id: str,
    body: MarkOutOfScopeRequest,
    caller: CallerPermission,
    use_case: MarkOutOfScopeUseCase,
    email_sender: EmailSender,
    session: DBSession,
    reader: PermissionReaderDep,
) -> MuseumQuestionDetailResponse:
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
    return await _question_detail_response(question, reader)


@internal_router.post(
    "/{question_id}/forward", response_model=MuseumQuestionDetailResponse
)
async def forward_museum_question(
    question_id: str,
    body: ForwardMuseumQuestionRequest,
    caller: CallerPermission,
    use_case: ForwardUseCase,
    notification_dispatcher: MuseumQuestionNotificationDispatch,
    session: DBSession,
    reader: PermissionReaderDep,
) -> MuseumQuestionDetailResponse:
    target_permission_id = PermissionId(body.targetPermissionId)
    target = await _require_forward_target(target_permission_id, reader)
    try:
        question = await use_case.execute(
            ForwardMuseumQuestionInput(
                caller=caller,
                question_id=question_id,
                target_permission_id=target.permission_id,
            )
        )
    except MuseumQuestionNotFound as exc:
        raise _not_found(question_id) from exc
    except InvalidMuseumQuestionTransition as exc:
        raise _invalid_transition(exc) from exc
    if target_permission_id != caller.id:
        await notification_dispatcher.notify(
            recipient_permission_id=target_permission_id,
            kind=NotificationKind.MUSEUM_QUESTION_FORWARDED,
            triggered_by=caller.id,
            related_resource_type=RelatedResourceType.MUSEUM_QUESTION,
            related_resource_id=question.id,
            related_resource_label=question.subject,
        )
    await session.commit()
    return await _question_detail_response(question, reader)


@internal_router.get("/{question_id}/attachments/{attachment_id}")
async def download_museum_question_attachment(
    question_id: str,
    attachment_id: str,
    caller: CallerPermission,
    use_case: GetUseCase,
    file_storage: QuestionFileStorage,
) -> Response:
    try:
        question = await use_case.execute(caller, question_id)
    except MuseumQuestionNotFound as exc:
        raise _not_found(question_id) from exc
    attachment = next(
        (item for item in question.attachments or [] if item.id == attachment_id),
        None,
    )
    if attachment is None:
        raise _attachment_not_found(attachment_id)
    try:
        content = await file_storage.read(attachment.file_reference)
    except FileNotFoundError as exc:
        raise _attachment_not_found(attachment_id) from exc
    return Response(
        content=content,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": content_disposition_attachment(
                attachment.file_name, default="image", disposition="inline"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@internal_router.patch(
    "/{question_id}/close", response_model=MuseumQuestionDetailResponse
)
async def close_museum_question(
    question_id: str,
    caller: CallerPermission,
    use_case: CloseUseCase,
    session: DBSession,
    reader: PermissionReaderDep,
) -> MuseumQuestionDetailResponse:
    try:
        question = await use_case.execute(
            CloseMuseumQuestionInput(caller=caller, question_id=question_id)
        )
    except MuseumQuestionNotFound as exc:
        raise _not_found(question_id) from exc
    except InvalidMuseumQuestionTransition as exc:
        raise _invalid_transition(exc) from exc
    await session.commit()
    return await _question_detail_response(question, reader)
