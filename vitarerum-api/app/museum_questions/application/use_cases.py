"""Use cases for the public, unauthenticated "Pergunte ao Museu" intake.

``SubmitMuseumQuestion`` enforces the server-side defences — honeypot, rate
limits, captcha verification — then persists the question as ``SUBMITTED``.
Unlike ``public_submission``'s proposal flow, there is no double opt-in: a
single call after admission is enough.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.identity.public import Actor, GroupName, PermissionId, PermissionReader
from app.museum_questions.application.ports import (
    CaptchaVerifier,
    Clock,
    FileStorage,
    MuseumQuestionRepository,
    RateLimiter,
)
from app.museum_questions.application.read_models import MuseumQuestionListItem
from app.museum_questions.domain.models import (
    InvalidMuseumQuestionTransition,
    MuseumQuestion,
    MuseumQuestionAttachment,
    MuseumQuestionNotFound,
    MuseumQuestionStatus,
)
from app.shared.authorization import require_group

# Rate limits as (max_requests, window_seconds), mirroring public_submission's
# reference implementation (same policy, duplicated code — see the plan).
RATE_LIMIT_PER_IP = (5, 60 * 60)
RATE_LIMIT_PER_EMAIL = (3, 24 * 60 * 60)
RATE_LIMIT_GLOBAL = (500, 60 * 60)
RETRY_AFTER_SECONDS = 60
MUSEUM_QUESTION_ACCESS_GROUPS = (
    GroupName.CURATORIAL,
    GroupName.COLLECTIONS_MANAGEMENT,
)


def require_museum_question_access(caller: Actor) -> None:
    require_group(caller, *MUSEUM_QUESTION_ACCESS_GROUPS)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int = RETRY_AFTER_SECONDS) -> None:
        super().__init__("Too many requests. Please try again later.")
        self.retry_after = retry_after


class CaptchaFailed(Exception):
    """The captcha token was missing, invalid, or expired."""


class CaptchaUnavailable(Exception):
    """The captcha provider could not be reached to verify the token."""


@dataclass(slots=True)
class UploadedMuseumQuestionImage:
    file_name: str
    content: bytes
    content_type: str
    extension: str


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
    attachments: list[UploadedMuseumQuestionImage] = field(default_factory=list)


@dataclass(slots=True)
class SubmitMuseumQuestionOutput:
    email: str
    # None for the honeypot accept-and-drop path (nothing was persisted).
    question_id: str | None = None
    file_references: list[str] = field(default_factory=list)


class SubmitMuseumQuestion:
    def __init__(
        self,
        repository: MuseumQuestionRepository,
        captcha: CaptchaVerifier,
        rate_limiter: RateLimiter,
        clock: Clock,
        file_storage: FileStorage,
    ) -> None:
        self._repo = repository
        self._captcha = captcha
        self._rate_limiter = rate_limiter
        self._clock = clock
        self._storage = file_storage

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
        question_id = str(uuid.uuid4())
        now = self._clock.now()
        saved_references: list[str] = []
        attachments: list[MuseumQuestionAttachment] = []
        try:
            for sort_order, image in enumerate(data.attachments):
                attachment_id = str(uuid.uuid4())
                reference = (
                    f"museum-questions/{question_id}/{attachment_id}{image.extension}"
                )
                file_reference = await self._storage.save(image.content, reference)
                saved_references.append(file_reference)
                attachments.append(
                    MuseumQuestionAttachment(
                        id=attachment_id,
                        question_id=question_id,
                        file_name=image.file_name,
                        file_reference=file_reference,
                        content_type=image.content_type,
                        size_bytes=len(image.content),
                        created_at=now,
                        sort_order=sort_order,
                    )
                )
            question = MuseumQuestion(
                id=question_id,
                requester_name=data.requester_name,
                requester_email=data.requester_email,
                subject=data.subject,
                message=data.message,
                created_at=now,
                attachments=attachments,
            )
            await self._repo.add(question)
        except Exception:
            await self.discard_uploaded_files(saved_references)
            raise
        return SubmitMuseumQuestionOutput(
            email=data.requester_email,
            question_id=question.id,
            file_references=saved_references,
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

    async def discard_uploaded_files(self, file_references: list[str]) -> None:
        for file_reference in file_references:
            await self._storage.delete(file_reference)


@dataclass(frozen=True, slots=True)
class MuseumQuestionPage:
    content: list[MuseumQuestionListItem]
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


@dataclass(frozen=True, slots=True)
class ForwardMuseumQuestionInput:
    caller: Actor
    question_id: str
    target_permission_id: str


class ListMuseumQuestions:
    def __init__(
        self,
        repository: MuseumQuestionRepository,
        permission_reader: PermissionReader | None = None,
    ) -> None:
        self._repo = repository
        self._permission_reader = permission_reader

    async def execute(
        self,
        caller: Actor,
        *,
        status: MuseumQuestionStatus | None,
        requester_email: str | None = None,
        assigned_to: str | None = None,
        unassigned_only: bool = False,
        page: int,
        size: int,
    ) -> MuseumQuestionPage:
        require_museum_question_access(caller)
        normalized_requester_email = (
            requester_email.strip().lower() if requester_email else None
        )
        content, total = await self._repo.list(
            status=status,
            requester_email=normalized_requester_email,
            assigned_to=assigned_to,
            unassigned_only=unassigned_only,
            page=page,
            size=size,
        )
        if self._permission_reader is not None:
            hydrated: list[MuseumQuestionListItem] = []
            for item in content:
                hydrated.append(
                    MuseumQuestionListItem(
                        question=item.question,
                        attachment_count=item.attachment_count,
                        assigned_to=(
                            await self._permission_reader.get_detail(
                                PermissionId(item.question.assigned_to)
                            )
                            if item.question.assigned_to
                            else None
                        ),
                    )
                )
            content = hydrated
        return MuseumQuestionPage(content=content, page=page, size=size, total=total)


class GetMuseumQuestion:
    def __init__(self, repository: MuseumQuestionRepository) -> None:
        self._repo = repository

    async def execute(self, caller: Actor, question_id: str) -> MuseumQuestion:
        require_museum_question_access(caller)
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
        require_museum_question_access(data.caller)
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
        require_museum_question_access(data.caller)
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
        require_museum_question_access(data.caller)
        question = await self._repo.get_by_id(data.question_id)
        if question is None:
            raise MuseumQuestionNotFound(data.question_id)
        question.close(by=str(data.caller.id), closed_at=self._clock.now())
        await self._repo.save(question)
        return question


class ForwardMuseumQuestion:
    def __init__(self, repository: MuseumQuestionRepository) -> None:
        self._repo = repository

    async def execute(self, data: ForwardMuseumQuestionInput) -> MuseumQuestion:
        require_museum_question_access(data.caller)
        question = await self._repo.get_by_id(data.question_id)
        if question is None:
            raise MuseumQuestionNotFound(data.question_id)
        question.forward(target_permission_id=data.target_permission_id)
        await self._repo.save(question)
        return question
