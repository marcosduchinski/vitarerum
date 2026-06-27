"""Ports (driven interfaces) for the public submission context.

The use cases depend only on these structural protocols; concrete adapters
(SQLAlchemy repo, Cloudflare verifier, SMTP/logging mailer, in-memory limiter,
system clock) are wired in the presentation composition root.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.public_submission.domain.models import PendingPublicSubmission


class PendingSubmissionRepository(Protocol):
    async def add(self, submission: PendingPublicSubmission) -> None: ...

    async def get_by_token(self, token: str) -> PendingPublicSubmission | None: ...

    async def save(self, submission: PendingPublicSubmission) -> None: ...


class CaptchaVerifier(Protocol):
    async def verify(self, token: str, remote_ip: str) -> bool:
        """Return True iff the captcha token is valid.

        Raise to signal the provider was unreachable (mapped to ``503``)."""
        ...


class ConfirmationEmailSender(Protocol):
    async def send(self, to_email: str, citizen_name: str, token: str) -> None:
        """Deliver the confirmation link (built from ``token``) to the citizen."""
        ...


class RateLimiter(Protocol):
    def too_many(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Record a hit for ``key`` and report whether the limit is now exceeded."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...
