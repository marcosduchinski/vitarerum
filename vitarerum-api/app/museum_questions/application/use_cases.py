"""Use cases for the public, unauthenticated "Pergunte ao Museu" intake.

``SubmitMuseumQuestion`` enforces the server-side defences — honeypot, rate
limits, captcha verification — then persists the question as ``SUBMITTED``.
Unlike ``public_submission``'s proposal flow, there is no double opt-in and no
file upload: a single call after admission is enough.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.identity.public import Actor
from app.museum_questions.application.ports import (
    CaptchaVerifier,
    Clock,
    MuseumQuestionRepository,
    RateLimiter,
)
from app.museum_questions.domain.models import (
    InvalidMuseumQuestionTransition,
    MuseumQuestion,
    MuseumQuestionNotFound,
    MuseumQuestionStatus,
)
from app.shared.authorization import require_staff

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


@dataclass(frozen=True, slots=True)
class MuseumQuestionPage:
    content: list[MuseumQuestion]
    page: int
    size: int
    total: int


@dataclass(frozen=True, slots=True)
class AnswerMuseumQuestionInput:
    caller: Actor
    question_id: str
    answer_body: str


@dataclass(frozen=True, slots=True)
class MarkMuseumQuestionOutOfScopeInput:
    caller: Actor
    question_id: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CloseMuseumQuestionInput:
    caller: Actor
    question_id: str


class ListMuseumQuestions:
    def __init__(self, repository: MuseumQuestionRepository) -> None:
        self._repo = repository

    async def execute(
        self,
        caller: Actor,
        *,
        status: MuseumQuestionStatus | None,
        requester_email: str | None = None,
        page: int,
        size: int,
    ) -> MuseumQuestionPage:
        require_staff(caller)
        normalized_requester_email = (
            requester_email.strip().lower() if requester_email else None
        )
        content, total = await self._repo.list(
            status=status,
            requester_email=normalized_requester_email,
            page=page,
            size=size,
        )
        return MuseumQuestionPage(content=content, page=page, size=size, total=total)


class GetMuseumQuestion:
    def __init__(self, repository: MuseumQuestionRepository) -> None:
        self._repo = repository

    async def execute(self, caller: Actor, question_id: str) -> MuseumQuestion:
        require_staff(caller)
        question = await self._repo.get_by_id(question_id)
        if question is None:
            raise MuseumQuestionNotFound(question_id)
        return question


class AnswerMuseumQuestion:
    """Persists the answer only. The e-mail is sent by the route, after the
    status change is durably committed — see ``presentation/routes.py``; a
    citizen must never receive a reply for an update that rolled back."""

    def __init__(self, repository: MuseumQuestionRepository, clock: Clock) -> None:
        self._repo = repository
        self._clock = clock

    async def execute(self, data: AnswerMuseumQuestionInput) -> MuseumQuestion:
        require_staff(data.caller)
        question = await self._repo.get_by_id(data.question_id)
        if question is None:
            raise MuseumQuestionNotFound(data.question_id)
        if question.status != MuseumQuestionStatus.SUBMITTED:
            raise InvalidMuseumQuestionTransition(
                "Only submitted questions can be answered."
            )
        answer_body = data.answer_body.strip()
        if not answer_body:
            raise ValueError("Answer body is required.")
        now = self._clock.now()
        question.answer(
            body=answer_body,
            answered_by=str(data.caller.id),
            answered_at=now,
            sent_at=now,
        )
        await self._repo.save(question)
        return question


class MarkMuseumQuestionOutOfScope:
    """Persists the out-of-scope status only. The e-mail is sent by the
    route, after commit — see :class:`AnswerMuseumQuestion`."""

    def __init__(self, repository: MuseumQuestionRepository, clock: Clock) -> None:
        self._repo = repository
        self._clock = clock

    async def execute(self, data: MarkMuseumQuestionOutOfScopeInput) -> MuseumQuestion:
        require_staff(data.caller)
        question = await self._repo.get_by_id(data.question_id)
        if question is None:
            raise MuseumQuestionNotFound(data.question_id)
        if question.status != MuseumQuestionStatus.SUBMITTED:
            raise InvalidMuseumQuestionTransition(
                "Only submitted questions can be marked out of scope."
            )
        now = self._clock.now()
        question.mark_out_of_scope(
            reason=data.reason,
            by=str(data.caller.id),
            occurred_at=now,
            email_sent_at=now,
        )
        await self._repo.save(question)
        return question


class CloseMuseumQuestion:
    def __init__(self, repository: MuseumQuestionRepository, clock: Clock) -> None:
        self._repo = repository
        self._clock = clock

    async def execute(self, data: CloseMuseumQuestionInput) -> MuseumQuestion:
        require_staff(data.caller)
        question = await self._repo.get_by_id(data.question_id)
        if question is None:
            raise MuseumQuestionNotFound(data.question_id)
        question.close(by=str(data.caller.id), closed_at=self._clock.now())
        await self._repo.save(question)
        return question
