"""Composition root for the Museum Questions inbound adapter.

Wires the SQLAlchemy repository with the captcha verifier, rate limiter and
clock — selecting the local/dev stand-in (always-pass captcha) when
``app_env`` is local, matching ``public_submission``'s composition root.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_session
from app.identity.public import (
    GroupName,
    PermissionReader,
    PermissionView,
    get_permission_reader,
)
from app.museum_questions.application.ports import (
    CaptchaVerifier,
    FileStorage,
    MuseumQuestionEmailSender,
    MuseumQuestionRepository,
)
from app.museum_questions.application.use_cases import (
    AnswerMuseumQuestion,
    CloseMuseumQuestion,
    ForwardMuseumQuestion,
    GetMuseumQuestion,
    ListMuseumQuestions,
    MarkMuseumQuestionOutOfScope,
    NotifyOverdueMuseumQuestions,
    SubmitMuseumQuestion,
)
from app.museum_questions.infrastructure.captcha import (
    AlwaysPassVerifier,
    CloudflareTurnstileVerifier,
)
from app.museum_questions.infrastructure.clock import SystemClock
from app.museum_questions.infrastructure.email import (
    LoggingMuseumQuestionEmailSender,
    SmtpMuseumQuestionEmailSender,
)
from app.museum_questions.infrastructure.rate_limiter import (
    InMemorySlidingWindowRateLimiter,
)
from app.museum_questions.infrastructure.repositories import (
    SqlAlchemyMuseumQuestionRepository,
)
from app.notifications.public import NotificationDispatcher
from app.notifications.public import (
    get_notification_dispatcher as build_notification_dispatcher,
)
from app.shared.field_encryption import FieldEncryptor
from app.shared.file_storage import build_file_storage

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

_LOCAL_ENVS = {"local", "test", "development"}

# Process-wide singletons (rate-limit windows must persist across requests).
_rate_limiter = InMemorySlidingWindowRateLimiter()
_clock = SystemClock()


def _field_encryptor() -> FieldEncryptor:
    return FieldEncryptor.from_base64(settings.db_field_encryption_key)


def _captcha_verifier() -> CaptchaVerifier:
    if settings.app_env.lower() in _LOCAL_ENVS:
        return AlwaysPassVerifier()
    return CloudflareTurnstileVerifier(
        secret_key=settings.turnstile_secret_key,
        verify_url=settings.turnstile_verify_url,
    )


def _email_sender() -> MuseumQuestionEmailSender:
    if not settings.smtp_host:
        return LoggingMuseumQuestionEmailSender()
    return SmtpMuseumQuestionEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        from_address=settings.smtp_from_address,
        use_tls=settings.smtp_use_tls,
    )


def _repository(session: AsyncSession) -> MuseumQuestionRepository:
    return SqlAlchemyMuseumQuestionRepository(session, _field_encryptor())


def get_file_storage() -> FileStorage:
    return build_file_storage(settings.data_dir, settings.file_encryption_key)


def get_submit_use_case(session: DBSession) -> SubmitMuseumQuestion:
    return SubmitMuseumQuestion(
        repository=_repository(session),
        captcha=_captcha_verifier(),
        rate_limiter=_rate_limiter,
        clock=_clock,
        file_storage=get_file_storage(),
    )


def get_reader(session: DBSession) -> PermissionReader:
    return get_permission_reader(session)


def get_list_use_case(
    session: DBSession,
    reader: Annotated[PermissionReader, Depends(get_reader)],
) -> ListMuseumQuestions:
    return ListMuseumQuestions(_repository(session), reader)


def get_get_use_case(session: DBSession) -> GetMuseumQuestion:
    return GetMuseumQuestion(_repository(session))


def get_answer_use_case(session: DBSession) -> AnswerMuseumQuestion:
    return AnswerMuseumQuestion(_repository(session), _clock)


def get_mark_out_of_scope_use_case(
    session: DBSession,
) -> MarkMuseumQuestionOutOfScope:
    return MarkMuseumQuestionOutOfScope(_repository(session), _clock)


def get_close_use_case(session: DBSession) -> CloseMuseumQuestion:
    return CloseMuseumQuestion(_repository(session), _clock)


def get_forward_use_case(session: DBSession) -> ForwardMuseumQuestion:
    return ForwardMuseumQuestion(_repository(session))


def get_notify_overdue_use_case(
    session: AsyncSession,
    reader: PermissionReader,
    dispatcher: NotificationDispatcher,
) -> NotifyOverdueMuseumQuestions:
    return NotifyOverdueMuseumQuestions(
        _repository(session), reader, dispatcher, _clock
    )


def get_email_sender() -> MuseumQuestionEmailSender:
    return _email_sender()


async def _recipients_for_groups(
    reader: PermissionReader, groups: tuple[GroupName, ...]
) -> list[PermissionView]:
    recipients: dict[str, PermissionView] = {}
    for group in groups:
        for permission in await reader.list_by_group(group):
            recipients.setdefault(permission.permission_id, permission)
    return list(recipients.values())


async def get_museum_question_notification_recipients(
    reader: Annotated[PermissionReader, Depends(get_reader)],
) -> list[PermissionView]:
    return await _recipients_for_groups(
        reader, (GroupName.CURATORIAL, GroupName.COLLECTIONS_MANAGEMENT)
    )


async def get_museum_question_notification_email_recipients(
    reader: Annotated[PermissionReader, Depends(get_reader)],
) -> list[PermissionView]:
    return await _recipients_for_groups(
        reader, (GroupName.CURATORIAL, GroupName.COLLECTIONS_MANAGEMENT)
    )


def distinct_email_recipients(recipients: list[PermissionView]) -> list[PermissionView]:
    distinct: dict[str, PermissionView] = {}
    for recipient in recipients:
        key = recipient.user.id or recipient.user.email.lower()
        distinct.setdefault(key, recipient)
    return list(distinct.values())


def get_notifications_dispatcher(session: DBSession) -> NotificationDispatcher:
    return build_notification_dispatcher(session)


SubmitUseCase = Annotated[SubmitMuseumQuestion, Depends(get_submit_use_case)]
ListUseCase = Annotated[ListMuseumQuestions, Depends(get_list_use_case)]
GetUseCase = Annotated[GetMuseumQuestion, Depends(get_get_use_case)]
AnswerUseCase = Annotated[AnswerMuseumQuestion, Depends(get_answer_use_case)]
MarkOutOfScopeUseCase = Annotated[
    MarkMuseumQuestionOutOfScope, Depends(get_mark_out_of_scope_use_case)
]
CloseUseCase = Annotated[CloseMuseumQuestion, Depends(get_close_use_case)]
ForwardUseCase = Annotated[ForwardMuseumQuestion, Depends(get_forward_use_case)]
EmailSender = Annotated[MuseumQuestionEmailSender, Depends(get_email_sender)]
QuestionFileStorage = Annotated[FileStorage, Depends(get_file_storage)]
MuseumQuestionNotificationDispatch = Annotated[
    NotificationDispatcher, Depends(get_notifications_dispatcher)
]
MuseumQuestionNotificationRecipients = Annotated[
    list[PermissionView], Depends(get_museum_question_notification_recipients)
]
MuseumQuestionNotificationEmailRecipients = Annotated[
    list[PermissionView], Depends(get_museum_question_notification_email_recipients)
]
