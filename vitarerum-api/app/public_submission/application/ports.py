"""Ports (driven interfaces) for the public submission context.

The use cases depend only on these structural protocols; concrete adapters
(SQLAlchemy repo, Cloudflare verifier, SMTP/logging mailer, in-memory limiter,
system clock) are wired in the presentation composition root.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Protocol

from app.public_submission.domain.models import PendingPublicSubmission


class PendingSubmissionRepository(Protocol):
    async def add(self, submission: PendingPublicSubmission) -> None: ...

    async def get_by_token(self, token: str) -> PendingPublicSubmission | None: ...

    async def get_by_token_for_update(
        self, token: str
    ) -> PendingPublicSubmission | None:
        """Load the pending row and lock it for the rest of the transaction.

        Serialises concurrent confirmations of the same token: the loser blocks
        until the winner commits, then re-reads the row as ``CONFIRMED``."""
        ...

    async def save(self, submission: PendingPublicSubmission) -> None: ...

    async def delete(self, submission: PendingPublicSubmission) -> None:
        """Remove the pending row (and its document rows) — used to reclaim an
        expired, never-confirmed submission on the confirm attempt that finds it."""
        ...


class UniqueRetryRunner(Protocol):
    """Runs an operation that allocates a unique value (e.g. a sequential
    reference number), retrying on a unique-constraint conflict. Implemented in
    the composition root over the infrastructure transaction helper so the
    application stays framework-free."""

    async def __call__[T](self, operation: Callable[[], Awaitable[T]]) -> T: ...


class CaptchaVerifier(Protocol):
    async def verify(self, token: str, remote_ip: str) -> bool:
        """Return True iff the captcha token is valid.

        Raise to signal the provider was unreachable (mapped to ``503``)."""
        ...


class ConfirmationEmailSender(Protocol):
    async def send(self, to_email: str, citizen_name: str, token: str) -> None:
        """Deliver the confirmation link (built from ``token``) to the citizen."""
        ...


class FileStorage(Protocol):
    async def save(self, content: bytes, file_reference: str) -> str:
        """Persist bytes and return the durable file reference."""
        ...

    async def delete(self, file_reference: str) -> None:
        """Delete a previously persisted file reference if it exists."""
        ...


class RateLimiter(Protocol):
    def too_many(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Record a hit for ``key`` and report whether the limit is now exceeded."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...
