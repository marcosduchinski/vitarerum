"""Composition root for the password-reset flow (request/confirm).

Wires the SQLAlchemy repositories with the rate limiter, clock, and e-mail
sender — selecting the logging stand-in when SMTP isn't configured, matching
``museum_questions``'s and ``public_submission``'s composition roots.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_session
from app.identity.application.ports import PasswordEmailSender
from app.identity.application.use_cases import (
    ConfirmPasswordReset,
    RequestPasswordReset,
)
from app.identity.infrastructure.clock import SystemClock
from app.identity.infrastructure.email import (
    LoggingPasswordEmailSender,
    SmtpPasswordEmailSender,
)
from app.identity.infrastructure.rate_limiter import InMemorySlidingWindowRateLimiter
from app.identity.infrastructure.repositories import (
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyUserRepository,
)
from app.identity.infrastructure.security import BcryptPasswordHasher

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

# Process-wide singletons (rate-limit windows must persist across requests).
_rate_limiter = InMemorySlidingWindowRateLimiter()
_clock = SystemClock()


def get_password_email_sender() -> PasswordEmailSender:
    if not settings.smtp_host:
        return LoggingPasswordEmailSender(
            settings.public_origin, settings.password_reset_public_path
        )
    return SmtpPasswordEmailSender(
        public_origin=settings.public_origin,
        public_path=settings.password_reset_public_path,
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        from_address=settings.smtp_from_address,
        use_tls=settings.smtp_use_tls,
    )


def get_request_password_reset_use_case(session: DBSession) -> RequestPasswordReset:
    return RequestPasswordReset(
        user_repo=SqlAlchemyUserRepository(session),
        token_repo=SqlAlchemyPasswordResetTokenRepository(session),
        rate_limiter=_rate_limiter,
        clock=_clock,
        token_ttl=timedelta(minutes=settings.password_reset_token_ttl_minutes),
    )


def get_confirm_password_reset_use_case(session: DBSession) -> ConfirmPasswordReset:
    return ConfirmPasswordReset(
        user_repo=SqlAlchemyUserRepository(session),
        token_repo=SqlAlchemyPasswordResetTokenRepository(session),
        hasher=BcryptPasswordHasher(),
        rate_limiter=_rate_limiter,
        clock=_clock,
    )


RequestPasswordResetUseCase = Annotated[
    RequestPasswordReset, Depends(get_request_password_reset_use_case)
]
ConfirmPasswordResetUseCase = Annotated[
    ConfirmPasswordReset, Depends(get_confirm_password_reset_use_case)
]
PasswordEmailSenderDep = Annotated[
    PasswordEmailSender, Depends(get_password_email_sender)
]
