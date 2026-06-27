"""Composition root for the public submission inbound adapter.

Wires the SQLAlchemy repo with the captcha verifier, e-mail sender, rate limiter
and clock — selecting local/dev stand-ins (always-pass captcha, logging mailer)
when ``app_env`` is local or when SMTP is not configured. The confirm flow reuses
the published ``ProvisionExternalRequester`` (Identity) and ``SubmitProposal``
(Use of Collections), exactly as the legacy e-mail intake did.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_session
from app.identity.infrastructure.repositories import (
    SqlAlchemyGroupRepository,
    SqlAlchemyPermissionRepository,
    SqlAlchemyUserRepository,
)
from app.identity.public import ProvisionExternalRequester
from app.public_submission.application.ports import (
    CaptchaVerifier,
    ConfirmationEmailSender,
)
from app.public_submission.application.use_cases import (
    ConfirmPublicProposal,
    SubmitPublicProposal,
)
from app.public_submission.infrastructure.captcha import (
    AlwaysPassVerifier,
    CloudflareTurnstileVerifier,
)
from app.public_submission.infrastructure.clock import SystemClock
from app.public_submission.infrastructure.email import (
    LoggingConfirmationEmailSender,
    SmtpConfirmationEmailSender,
)
from app.public_submission.infrastructure.rate_limiter import (
    InMemorySlidingWindowRateLimiter,
)
from app.public_submission.infrastructure.repositories import (
    SqlAlchemyPendingSubmissionRepository,
)
from app.use_of_collections.application.use_cases import SubmitProposal
from app.use_of_collections.infrastructure.repositories import (
    SqlAlchemyConversationRepository,
    SqlAlchemyProposalRepository,
)

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

_LOCAL_ENVS = {"local", "test", "development"}

# Process-wide singletons (rate-limit windows must persist across requests).
_rate_limiter = InMemorySlidingWindowRateLimiter()
_clock = SystemClock()


def _captcha_verifier() -> CaptchaVerifier:
    if settings.app_env.lower() in _LOCAL_ENVS:
        return AlwaysPassVerifier()
    return CloudflareTurnstileVerifier(
        secret_key=settings.turnstile_secret_key,
        verify_url=settings.turnstile_verify_url,
    )


def _email_sender() -> ConfirmationEmailSender:
    if not settings.smtp_host:
        return LoggingConfirmationEmailSender(settings.public_origin)
    return SmtpConfirmationEmailSender(
        public_origin=settings.public_origin,
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        from_address=settings.smtp_from_address,
        use_tls=settings.smtp_use_tls,
    )


def get_submit_use_case(session: DBSession) -> SubmitPublicProposal:
    return SubmitPublicProposal(
        repository=SqlAlchemyPendingSubmissionRepository(session),
        captcha=_captcha_verifier(),
        email_sender=_email_sender(),
        rate_limiter=_rate_limiter,
        clock=_clock,
    )


def get_confirm_use_case(session: DBSession) -> ConfirmPublicProposal:
    provision = ProvisionExternalRequester(
        user_repo=SqlAlchemyUserRepository(session),
        group_repo=SqlAlchemyGroupRepository(session),
        permission_repo=SqlAlchemyPermissionRepository(session),
    )
    submit = SubmitProposal(
        SqlAlchemyProposalRepository(session),
        SqlAlchemyConversationRepository(session),
    )
    return ConfirmPublicProposal(
        repository=SqlAlchemyPendingSubmissionRepository(session),
        provision_requester=provision,
        submit_proposal=submit,
        rate_limiter=_rate_limiter,
        clock=_clock,
        token_ttl=timedelta(hours=settings.public_confirm_token_ttl_hours),
    )


SubmitUseCase = Annotated[SubmitPublicProposal, Depends(get_submit_use_case)]
ConfirmUseCase = Annotated[ConfirmPublicProposal, Depends(get_confirm_use_case)]
