"""Use cases for the public, unauthenticated proposal submission flow.

``SubmitPublicProposal`` (step 1) enforces the server-side defences — honeypot,
rate limits, captcha verification — and stores a pending record, e-mailing a
single-use confirmation token. ``ConfirmPublicProposal`` (step 2) consumes the
token and materialises the real proposal by composing the published
``ProvisionExternalRequester`` (Identity OHS) and ``SubmitProposal`` (Use of
Collections) use cases — the same composition the legacy e-mail intake used.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from app.identity.public import ProvisionExternalRequester
from app.public_submission.application.ports import (
    CaptchaVerifier,
    Clock,
    PendingSubmissionRepository,
    RateLimiter,
    UniqueRetryRunner,
)
from app.public_submission.domain.models import PendingPublicSubmission
from app.use_of_collections.application.use_cases import (
    SubmitProposal,
    SubmitProposalInput,
)

# Rate limits as (max_requests, window_seconds), mirroring the reference impl.
RATE_LIMIT_PER_IP = (5, 60 * 60)
RATE_LIMIT_PER_EMAIL = (3, 24 * 60 * 60)
RATE_LIMIT_GLOBAL = (500, 60 * 60)
RETRY_AFTER_SECONDS = 60


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int = RETRY_AFTER_SECONDS) -> None:
        super().__init__("Too many requests. Please try again later.")
        self.retry_after = retry_after


class CaptchaFailed(Exception):
    """The captcha token was missing, invalid, or expired."""


class CaptchaUnavailable(Exception):
    """The captcha provider could not be reached to verify the token."""


# ── Step 1: submit ─────────────────────────────────────────────────────────────


@dataclass(slots=True)
class SubmitPublicProposalInput:
    citizen_name: str
    citizen_email: str
    subject: str
    body: str
    consent: bool
    captcha_token: str
    website: str
    remote_ip: str


@dataclass(slots=True)
class SubmitPublicProposalOutput:
    email: str
    # The confirmation e-mail is dispatched by the route AFTER commit, so the
    # token is only ever e-mailed once it is durably persisted. ``token`` is
    # ``None`` for the honeypot accept-and-drop path (nothing to send).
    name: str = ""
    token: str | None = None


class SubmitPublicProposal:
    def __init__(
        self,
        repository: PendingSubmissionRepository,
        captcha: CaptchaVerifier,
        rate_limiter: RateLimiter,
        clock: Clock,
    ) -> None:
        self._repo = repository
        self._captcha = captcha
        self._rate_limiter = rate_limiter
        self._clock = clock

    async def execute(
        self, data: SubmitPublicProposalInput
    ) -> SubmitPublicProposalOutput:
        # 1) Honeypot: accept-and-drop. Same 202 shape so a bot learns nothing.
        if data.website:
            return SubmitPublicProposalOutput(email=data.citizen_email, token=None)

        # 2) Rate limits (IP, e-mail, global).
        email_key = data.citizen_email.strip().lower()
        if (
            self._rate_limiter.too_many(f"ip:{data.remote_ip}", *RATE_LIMIT_PER_IP)
            or self._rate_limiter.too_many(f"email:{email_key}", *RATE_LIMIT_PER_EMAIL)
            or self._rate_limiter.too_many("global", *RATE_LIMIT_GLOBAL)
        ):
            raise RateLimitExceeded()

        # 3) Verify the captcha token server-side.
        try:
            ok = await self._captcha.verify(data.captcha_token, data.remote_ip)
        except Exception as exc:  # provider unreachable → 503
            raise CaptchaUnavailable(str(exc)) from exc
        if not ok:
            raise CaptchaFailed("Captcha verification failed.")

        # 4) Double opt-in: stash a pending record keyed by a single-use token.
        submission = PendingPublicSubmission(
            id=str(uuid.uuid4()),
            token=secrets.token_urlsafe(32),
            citizen_name=data.citizen_name,
            citizen_email=data.citizen_email,
            subject=data.subject,
            body=data.body,
            consent=data.consent,
            created_at=self._clock.now(),
        )
        await self._repo.add(submission)
        # The route sends the confirmation e-mail only after it commits, so the
        # citizen never receives a link whose token failed to persist.
        return SubmitPublicProposalOutput(
            email=data.citizen_email,
            name=data.citizen_name,
            token=submission.token,
        )


# ── Step 2: confirm ────────────────────────────────────────────────────────────

ConfirmStatus = Literal["CONFIRMED", "ALREADY_CONFIRMED", "EXPIRED", "INVALID"]


@dataclass(slots=True)
class ConfirmPublicProposalOutput:
    status: ConfirmStatus
    reference_number: str | None = None


class ConfirmPublicProposal:
    def __init__(
        self,
        repository: PendingSubmissionRepository,
        provision_requester: ProvisionExternalRequester,
        submit_proposal: SubmitProposal,
        rate_limiter: RateLimiter,
        clock: Clock,
        token_ttl: timedelta,
        retry_runner: UniqueRetryRunner,
    ) -> None:
        self._repo = repository
        self._provision = provision_requester
        self._submit = submit_proposal
        self._rate_limiter = rate_limiter
        self._clock = clock
        self._ttl = token_ttl
        self._retry_runner = retry_runner

    async def execute(
        self, token: str, remote_ip: str
    ) -> ConfirmPublicProposalOutput:
        if self._rate_limiter.too_many(f"confirm-ip:{remote_ip}", *RATE_LIMIT_PER_IP):
            raise RateLimitExceeded()
        # Lock the row for the rest of the transaction so two concurrent
        # confirmations of the same token cannot both materialise a proposal.
        submission = await self._repo.get_by_token_for_update(token)
        if submission is None:
            return ConfirmPublicProposalOutput(status="INVALID")
        if submission.is_confirmed:
            # Idempotent re-click of an already-used link (or the loser of a race).
            return ConfirmPublicProposalOutput(
                status="ALREADY_CONFIRMED",
                reference_number=submission.proposal_reference,
            )
        now = self._clock.now()
        if submission.is_expired(now, self._ttl):
            return ConfirmPublicProposalOutput(status="EXPIRED")

        # Retry the proposal materialisation on a reference-number unique
        # conflict (sequential MAX+1 allocation), matching authenticated submit.
        reference = await self._retry_runner(lambda: self._materialise(submission))
        submission.confirm(proposal_reference=reference, occurred_at=now)
        await self._repo.save(submission)
        return ConfirmPublicProposalOutput(
            status="CONFIRMED", reference_number=reference
        )

    async def _materialise(self, submission: PendingPublicSubmission) -> str:
        provisioned = await self._provision.execute(
            email=submission.citizen_email, name=submission.citizen_name
        )
        output = await self._submit.execute(
            SubmitProposalInput(
                title=None,
                intended_use=None,
                purpose=None,
                begin_date=None,
                end_date=None,
                requested_by=provisioned.actor,
                initial_message_subject=submission.subject,
                initial_message_body=submission.body,
            )
        )
        return output.proposal.reference_number.value
