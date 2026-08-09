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
from app.museum_questions.application.ports import (
    CaptchaVerifier,
    FileStorage,
    MuseumQuestionEmailSender,
    MuseumQuestionRepository,
)
from app.museum_questions.application.use_cases import (
    AnswerMuseumQuestion,
    CloseMuseumQuestion,
    GetMuseumQuestion,
    ListMuseumQuestions,
    MarkMuseumQuestionOutOfScope,
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


def get_list_use_case(session: DBSession) -> ListMuseumQuestions:
    return ListMuseumQuestions(_repository(session))


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


def get_email_sender() -> MuseumQuestionEmailSender:
    return _email_sender()


SubmitUseCase = Annotated[SubmitMuseumQuestion, Depends(get_submit_use_case)]
ListUseCase = Annotated[ListMuseumQuestions, Depends(get_list_use_case)]
GetUseCase = Annotated[GetMuseumQuestion, Depends(get_get_use_case)]
AnswerUseCase = Annotated[AnswerMuseumQuestion, Depends(get_answer_use_case)]
MarkOutOfScopeUseCase = Annotated[
    MarkMuseumQuestionOutOfScope, Depends(get_mark_out_of_scope_use_case)
]
CloseUseCase = Annotated[CloseMuseumQuestion, Depends(get_close_use_case)]
EmailSender = Annotated[MuseumQuestionEmailSender, Depends(get_email_sender)]
QuestionFileStorage = Annotated[FileStorage, Depends(get_file_storage)]
