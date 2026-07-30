"""Composition root for the public submission inbound adapter.

Wires the SQLAlchemy repo with the captcha verifier, e-mail sender, rate limiter
    and clock — selecting local/dev stand-ins (always-pass captcha, logging mailer)
    when ``app_env`` is local or when SMTP is not configured. The confirm flow reuses
    ``SubmitProposal`` (Use of Collections), while Identity provisioning is deferred
    to proposal approval.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_session
from app.identity.public import PermissionReader, get_permission_reader
from app.notifications.public import (
    NotificationDispatcher,
)
from app.notifications.public import (
    get_notification_dispatcher as build_notification_dispatcher,
)
from app.public_submission.application.ports import (
    AmendmentTokenRepository,
    CaptchaVerifier,
    ConfirmationEmailSender,
    PublicEmailSender,
)
from app.public_submission.application.use_cases import (
    ConfirmPublicProposal,
    SubmitPublicProposal,
)
from app.public_submission.infrastructure.amendment import (
    PublicAmendmentInvitationAdapter,
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
    SqlAlchemyAmendmentTokenRepository,
    SqlAlchemyPendingSubmissionRepository,
)
from app.reference_numbers.public import get_reference_generator
from app.shared.persistence import run_with_unique_retry
from app.use_of_collections.application.ports import (
    ProposalNotificationEmailSender,
    ProposalRepository,
)
from app.use_of_collections.application.use_cases import (
    RemoveAmendmentDocument,
    SubmitAmendmentCorrections,
    SubmitAmendmentDocument,
    SubmitProposal,
)
from app.use_of_collections.infrastructure.file_storage import LocalDiskFileStorage
from app.use_of_collections.infrastructure.proposal_notification_email import (
    LoggingProposalNotificationEmailSender,
    SmtpProposalNotificationEmailSender,
)
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


def _email_sender() -> PublicEmailSender:
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
        rate_limiter=_rate_limiter,
        clock=_clock,
        file_storage=LocalDiskFileStorage(settings.data_dir),
    )


def get_email_sender() -> ConfirmationEmailSender:
    return _email_sender()


def get_confirm_use_case(session: DBSession) -> ConfirmPublicProposal:
    submit = SubmitProposal(
        SqlAlchemyProposalRepository(session),
        SqlAlchemyConversationRepository(session),
        get_reference_generator(session),
    )

    async def retry_runner[T](operation: Callable[[], Awaitable[T]]) -> T:
        return await run_with_unique_retry(session, operation)

    return ConfirmPublicProposal(
        repository=SqlAlchemyPendingSubmissionRepository(session),
        submit_proposal=submit,
        rate_limiter=_rate_limiter,
        clock=_clock,
        token_ttl=timedelta(hours=settings.public_confirm_token_ttl_hours),
        retry_runner=retry_runner,
        file_storage=LocalDiskFileStorage(settings.data_dir),
    )


def get_amendment_token_repo(session: DBSession) -> AmendmentTokenRepository:
    return SqlAlchemyAmendmentTokenRepository(session)


def get_uoc_proposal_repo(session: DBSession) -> ProposalRepository:
    return SqlAlchemyProposalRepository(session)


def get_reader(session: DBSession) -> PermissionReader:
    return get_permission_reader(session)


def get_proposal_notification_email_sender() -> ProposalNotificationEmailSender:
    if not settings.smtp_host:
        return LoggingProposalNotificationEmailSender()
    return SmtpProposalNotificationEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password,
        from_address=settings.smtp_from_address,
        use_tls=settings.smtp_use_tls,
    )


def get_notifications_dispatcher(session: DBSession) -> NotificationDispatcher:
    return build_notification_dispatcher(session)


def get_submit_amendment_document(session: DBSession) -> SubmitAmendmentDocument:
    return SubmitAmendmentDocument(
        SqlAlchemyProposalRepository(session),
        LocalDiskFileStorage(settings.data_dir),
    )


def get_remove_amendment_document(session: DBSession) -> RemoveAmendmentDocument:
    return RemoveAmendmentDocument(
        SqlAlchemyProposalRepository(session),
        LocalDiskFileStorage(settings.data_dir),
    )


def get_submit_amendment_corrections(session: DBSession) -> SubmitAmendmentCorrections:
    return SubmitAmendmentCorrections(SqlAlchemyProposalRepository(session))


def get_amendment_invitation_adapter(
    session: DBSession,
) -> PublicAmendmentInvitationAdapter:
    """Real invitation adapter — installed over the ``use_of_collections`` default
    at the composition root (``app.main``) via ``dependency_overrides``."""
    return PublicAmendmentInvitationAdapter(
        session=session,
        token_repository=SqlAlchemyAmendmentTokenRepository(session),
        proposal_repository=SqlAlchemyProposalRepository(session),
        email_sender=_email_sender(),
        clock=_clock,
        token_ttl=timedelta(hours=settings.public_confirm_token_ttl_hours),
    )


def get_amendment_clock() -> SystemClock:
    return _clock


def get_amendment_rate_limiter() -> InMemorySlidingWindowRateLimiter:
    return _rate_limiter


SubmitUseCase = Annotated[SubmitPublicProposal, Depends(get_submit_use_case)]
EmailSender = Annotated[ConfirmationEmailSender, Depends(get_email_sender)]
ConfirmUseCase = Annotated[ConfirmPublicProposal, Depends(get_confirm_use_case)]
AmendmentTokenRepo = Annotated[
    AmendmentTokenRepository, Depends(get_amendment_token_repo)
]
AmendmentProposalRepo = Annotated[ProposalRepository, Depends(get_uoc_proposal_repo)]
AmendmentPermReader = Annotated[PermissionReader, Depends(get_reader)]
AmendmentProposalEmailSender = Annotated[
    ProposalNotificationEmailSender,
    Depends(get_proposal_notification_email_sender),
]
AmendmentNotificationDispatch = Annotated[
    NotificationDispatcher, Depends(get_notifications_dispatcher)
]
SubmitAmendmentDoc = Annotated[
    SubmitAmendmentDocument, Depends(get_submit_amendment_document)
]
RemoveAmendmentDoc = Annotated[
    RemoveAmendmentDocument, Depends(get_remove_amendment_document)
]
SubmitAmendmentCorr = Annotated[
    SubmitAmendmentCorrections, Depends(get_submit_amendment_corrections)
]
AmendmentClock = Annotated[SystemClock, Depends(get_amendment_clock)]
AmendmentRateLimiter = Annotated[
    InMemorySlidingWindowRateLimiter, Depends(get_amendment_rate_limiter)
]
