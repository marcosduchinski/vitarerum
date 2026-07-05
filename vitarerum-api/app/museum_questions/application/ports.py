"""Ports (driven interfaces) for the Museum Questions context.

``CaptchaVerifier``/``RateLimiter``/``Clock`` are structural twins of the
``public_submission`` ports of the same name (see the plan's "Decisões de
arquitetura"): that context is not a published language another context may
import, and the import-linter forbids cross-context imports, so the shapes
are duplicated here rather than shared.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.museum_questions.domain.models import MuseumQuestion


class CaptchaVerifier(Protocol):
    async def verify(self, token: str, remote_ip: str) -> bool:
        """Return True iff the captcha token is valid.

        Raise to signal the provider was unreachable (mapped to ``503``)."""
        ...


class RateLimiter(Protocol):
    def too_many(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Record a hit for ``key`` and report whether the limit is now exceeded."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class MuseumQuestionRepository(Protocol):
    async def add(self, question: MuseumQuestion) -> None: ...
