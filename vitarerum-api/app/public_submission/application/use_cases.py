"""Use cases for the public, unauthenticated proposal submission flow.

``SubmitPublicProposal`` (step 1) enforces the server-side defences — honeypot,
rate limits, captcha verification — and stores a pending record, e-mailing a
single-use confirmation token. ``ConfirmPublicProposal`` (step 2) consumes the
token and materialises the real proposal through ``SubmitProposal`` (Use of
Collections), carrying the citizen as requester contact until approval provisions
an Identity user/permission.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from app.public_submission.application.ports import (
    CaptchaVerifier,
    Clock,
    FileStorage,
    PendingSubmissionRepository,
    RateLimiter,
    UniqueRetryRunner,
)
from app.public_submission.domain.models import (
    PendingPublicSubmission,
    PublicDocumentSubmission,
)
from app.shared.kernel import UseType
from app.use_of_collections.application.use_cases import (
    SubmitProposal,
    SubmitProposalInput,
)
from app.use_of_collections.domain.enums import SubmissionChannel
from app.use_of_collections.domain.models import (
    Document,
    DocumentId,
    DocumentType,
    EmailAddress,
    Proposal,
    RequesterContact,
)

# Rate limits as (max_requests, window_seconds), mirroring the reference impl.
RATE_LIMIT_PER_IP = (50, 60 * 60)
RATE_LIMIT_PER_EMAIL = (50, 24 * 60 * 60)
RATE_LIMIT_GLOBAL = (500, 60 * 60)
RETRY_AFTER_SECONDS = 60
PUBLIC_DOCUMENT_TYPE = "PUBLIC_SUBMISSION"


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int = RETRY_AFTER_SECONDS) -> None:
        super().__init__("Too many requests. Please try again later.")
        self.retry_after = retry_after


class CaptchaFailed(Exception):
    """The captcha token was missing, invalid, or expired."""


class CaptchaUnavailable(Exception):
    """The captcha provider could not be reached to verify the token."""


def _safe_name(file_name: str) -> str:
    base = file_name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(c if (c.isalnum() or c in "._- ") else "_" for c in base)
    cleaned = cleaned.strip(". ") or "file"
    return cleaned[:120]


def _file_reference(subdir: str, owner_id: str, file_name: str) -> str:
    return f"{subdir}/{owner_id}/{uuid.uuid4()}_{_safe_name(file_name)}"


# ── Step 1: submit ─────────────────────────────────────────────────────────────


@dataclass(slots=True)
class UploadedDocument:
    file_name: str
    content: bytes


@dataclass(slots=True)
class SubmitPublicProposalInput:
    citizen_name: str
    citizen_email: str
    subject: str
    body: str
    use_type: UseType
    consent: bool
    captcha_token: str
    website: str
    remote_ip: str
    proposed_begin_date: date
    proposed_end_date: date
    documents: list[UploadedDocument]


@dataclass(slots=True)
class SubmitPublicProposalOutput:
    email: str
    # The confirmation e-mail is dispatched by the route AFTER commit, so the
    # token is only ever e-mailed once it is durably persisted. ``token`` is
    # ``None`` for the honeypot accept-and-drop path (nothing to send).
    name: str = ""
    token: str | None = None
    file_references: list[str] = field(default_factory=list)


class SubmitPublicProposal:
    def __init__(
        self,
        repository: PendingSubmissionRepository,
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
        citizen_email: str,
        website: str,
        captcha_token: str,
    ) -> bool:
        """Run the server-side gates that must pass *before* any upload is read.

        Returns ``True`` for the honeypot accept-and-drop path (the caller should
        respond 202 without buffering files); otherwise raises ``RateLimitExceeded``
        / ``CaptchaFailed`` / ``CaptchaUnavailable``. The public route calls this
        ahead of reading the multipart bodies so abusive traffic is shed by the
        rate limiter before the server buffers up to 5×10 MB in memory.
        """
        # 1) Honeypot: accept-and-drop. Same 202 shape so a bot learns nothing.
        if website:
            return True

        # 2) Rate limits (IP, e-mail, global).
        email_key = citizen_email.strip().lower()
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
        self, data: SubmitPublicProposalInput
    ) -> SubmitPublicProposalOutput:
        """Save the uploaded files and stash the pending record.

        Assumes :meth:`admit` has already granted admission for ``data``. Any
        failure (storage, domain invariant, or persistence) rolls back the files
        already written so a rejected submission leaves nothing behind."""
        submission_id = str(uuid.uuid4())
        now = self._clock.now()
        saved_references: list[str] = []
        documents: list[PublicDocumentSubmission] = []
        try:
            for document in data.documents:
                reference = _file_reference(
                    "public-submissions", submission_id, document.file_name
                )
                file_reference = await self._storage.save(document.content, reference)
                saved_references.append(file_reference)
                documents.append(
                    PublicDocumentSubmission(
                        id=str(uuid.uuid4()),
                        file_name=document.file_name,
                        file_reference=file_reference,
                        submitted_at=now,
                    )
                )
            # Double opt-in: stash a pending record keyed by a single-use token.
            submission = PendingPublicSubmission(
                id=submission_id,
                token=secrets.token_urlsafe(32),
                citizen_name=data.citizen_name,
                citizen_email=data.citizen_email,
                subject=data.subject,
                body=data.body,
                use_type=data.use_type,
                consent=data.consent,
                created_at=now,
                proposed_begin_date=data.proposed_begin_date,
                proposed_end_date=data.proposed_end_date,
                documents=documents,
            )
            await self._repo.add(submission)
        except Exception:
            await self.discard_uploaded_files(saved_references)
            raise
        # The route sends the confirmation e-mail only after it commits, so the
        # citizen never receives a link whose token failed to persist.
        return SubmitPublicProposalOutput(
            email=data.citizen_email,
            name=data.citizen_name,
            token=submission.token,
            file_references=saved_references,
        )

    async def execute(
        self, data: SubmitPublicProposalInput
    ) -> SubmitPublicProposalOutput:
        """Single-shot flow (admission then persistence).

        The public route drives :meth:`admit` and :meth:`persist` separately so it
        can shed abusive traffic before buffering uploads; this convenience path
        keeps direct callers simple."""
        if await self.admit(
            remote_ip=data.remote_ip,
            citizen_email=data.citizen_email,
            website=data.website,
            captcha_token=data.captcha_token,
        ):
            return SubmitPublicProposalOutput(email=data.citizen_email, token=None)
        return await self.persist(data)

    async def discard_uploaded_files(self, file_references: list[str]) -> None:
        for file_reference in file_references:
            await self._storage.delete(file_reference)


# ── Step 2: confirm ────────────────────────────────────────────────────────────

ConfirmStatus = Literal["CONFIRMED", "ALREADY_CONFIRMED", "EXPIRED", "INVALID"]


@dataclass(slots=True)
class ConfirmPublicProposalOutput:
    status: ConfirmStatus
    reference_number: str | None = None
    proposal_id: str | None = None
    submitted_by_name: str | None = None


class ConfirmPublicProposal:
    def __init__(
        self,
        repository: PendingSubmissionRepository,
        submit_proposal: SubmitProposal,
        rate_limiter: RateLimiter,
        clock: Clock,
        token_ttl: timedelta,
        retry_runner: UniqueRetryRunner,
        file_storage: FileStorage,
    ) -> None:
        self._repo = repository
        self._submit = submit_proposal
        self._rate_limiter = rate_limiter
        self._clock = clock
        self._ttl = token_ttl
        self._retry_runner = retry_runner
        self._storage = file_storage

    async def execute(self, token: str, remote_ip: str) -> ConfirmPublicProposalOutput:
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
            # The link is dead. Reclaim its uploaded files (and the row) now rather
            # than leaving them to linger — this is the only point the live system
            # sees an expired submission. Bulk purge of submissions whose owners
            # never click at all still needs a scheduled job (see the contract).
            for document in submission.documents:
                await self._storage.delete(document.file_reference)
            await self._repo.delete(submission)
            return ConfirmPublicProposalOutput(status="EXPIRED")

        # Keep the existing retry boundary around proposal materialisation; the
        # reference allocator is now transactional, but insert uniqueness remains
        # the final persistence backstop.
        proposal = await self._retry_runner(lambda: self._materialise(submission))
        reference = proposal.reference_number.value
        submission.confirm(proposal_reference=reference, occurred_at=now)
        await self._repo.save(submission)
        return ConfirmPublicProposalOutput(
            status="CONFIRMED",
            reference_number=reference,
            proposal_id=str(proposal.id),
            submitted_by_name=submission.citizen_name,
        )

    async def _materialise(self, submission: PendingPublicSubmission) -> Proposal:
        output = await self._submit.execute(
            SubmitProposalInput(
                title=None,
                intended_use=submission.use_type,
                purpose=None,
                begin_date=submission.proposed_begin_date,
                end_date=submission.proposed_end_date,
                requested_by=None,
                submission_channel=SubmissionChannel.PUBLIC,
                requester_contact=RequesterContact(
                    name=submission.citizen_name,
                    email=EmailAddress(submission.citizen_email),
                ),
                initial_message_sender=submission.citizen_email,
                initial_message_subject=submission.subject,
                initial_message_body=submission.body,
                documents=[
                    Document(
                        id=DocumentId(str(uuid.uuid4())),
                        type=DocumentType(PUBLIC_DOCUMENT_TYPE),
                        file_name=document.file_name,
                        file_reference=document.file_reference,
                        submitted_at=document.submitted_at,
                        submitted_by=None,
                    )
                    for document in submission.documents
                ],
            )
        )
        return output.proposal
