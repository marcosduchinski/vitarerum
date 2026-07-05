"""Use cases for the public, unauthenticated "Pergunte ao Museu" intake.

``SubmitMuseumQuestion`` enforces the server-side defences — honeypot, rate
limits, captcha verification — then persists the question as ``SUBMITTED``.
Unlike ``public_submission``'s proposal flow, there is no double opt-in and no
file upload: a single call after admission is enough.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.museum_questions.application.ports import (
    CaptchaVerifier,
    Clock,
    MuseumQuestionRepository,
    RateLimiter,
)
from app.museum_questions.domain.models import MuseumQuestion

# Rate limits as (max_requests, window_seconds), mirroring public_submission's
# reference implementation (same policy, duplicated code — see the plan).
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


@dataclass(slots=True)
class SubmitMuseumQuestionInput:
    # Consent is enforced by the request schema (Literal[True]) before this
    # input is ever constructed, and the domain model doesn't persist it (see
    # museum-questions-public-page-plan.md's field list) — so it isn't
    # threaded through here.
    requester_name: str
    requester_email: str
    subject: str
    message: str
    captcha_token: str
    website: str
    remote_ip: str


@dataclass(slots=True)
class SubmitMuseumQuestionOutput:
    email: str
    # None for the honeypot accept-and-drop path (nothing was persisted).
    question_id: str | None = None


class SubmitMuseumQuestion:
    def __init__(
        self,
        repository: MuseumQuestionRepository,
        captcha: CaptchaVerifier,
        rate_limiter: RateLimiter,
        clock: Clock,
    ) -> None:
        self._repo = repository
        self._captcha = captcha
        self._rate_limiter = rate_limiter
        self._clock = clock

    async def admit(
        self,
        *,
        remote_ip: str,
        requester_email: str,
        website: str,
        captcha_token: str,
    ) -> bool:
        """Run the server-side gates. Returns ``True`` for the honeypot
        accept-and-drop path; otherwise raises ``RateLimitExceeded`` /
        ``CaptchaFailed`` / ``CaptchaUnavailable``."""
        # 1) Honeypot: accept-and-drop. Same 202 shape so a bot learns nothing.
        if website:
            return True

        # 2) Rate limits (IP, e-mail, global).
        email_key = requester_email.strip().lower()
        if (
            self._rate_limiter.too_many(f"ip:{remote_ip}", *RATE_LIMIT_PER_IP)
            or self._rate_limiter.too_many(f"email:{email_key}", *RATE_LIMIT_PER_EMAIL)
            or self._rate_limiter.too_many("global", *RATE_LIMIT_GLOBAL)
        ):
            raise RateLimitExceeded()

        # 3) Verify the captcha token server-side.
        try:
            ok = await self._captcha.verify(captcha_token, remote_ip)
        except Exception as exc:  # provider unreachable → 503
            raise CaptchaUnavailable(str(exc)) from exc
        if not ok:
            raise CaptchaFailed("Captcha verification failed.")
        return False

    async def persist(
        self, data: SubmitMuseumQuestionInput
    ) -> SubmitMuseumQuestionOutput:
        """Assumes :meth:`admit` has already granted admission for ``data``."""
        question = MuseumQuestion(
            id=str(uuid.uuid4()),
            requester_name=data.requester_name,
            requester_email=data.requester_email,
            subject=data.subject,
            message=data.message,
            created_at=self._clock.now(),
        )
        await self._repo.add(question)
        return SubmitMuseumQuestionOutput(
            email=data.requester_email, question_id=question.id
        )

    async def execute(
        self, data: SubmitMuseumQuestionInput
    ) -> SubmitMuseumQuestionOutput:
        """Single-shot flow (admission then persistence)."""
        if await self.admit(
            remote_ip=data.remote_ip,
            requester_email=data.requester_email,
            website=data.website,
            captcha_token=data.captcha_token,
        ):
            return SubmitMuseumQuestionOutput(email=data.requester_email)
        return await self.persist(data)
