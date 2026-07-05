"""Composition root for the Museum Questions inbound adapter.

Wires the SQLAlchemy repository with the captcha verifier, rate limiter and
clock — selecting the local/dev stand-in (always-pass captcha) when
``app_env`` is local, matching ``public_submission``'s composition root.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_session
from app.museum_questions.application.ports import (
    CaptchaVerifier,
    MuseumQuestionRepository,
)
from app.museum_questions.application.use_cases import SubmitMuseumQuestion
from app.museum_questions.infrastructure.captcha import (
    AlwaysPassVerifier,
    CloudflareTurnstileVerifier,
)
from app.museum_questions.infrastructure.clock import SystemClock
from app.museum_questions.infrastructure.rate_limiter import (
    InMemorySlidingWindowRateLimiter,
)
from app.museum_questions.infrastructure.repositories import (
    SqlAlchemyMuseumQuestionRepository,
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


def get_submit_use_case(session: DBSession) -> SubmitMuseumQuestion:
    repository: MuseumQuestionRepository = SqlAlchemyMuseumQuestionRepository(session)
    return SubmitMuseumQuestion(
        repository=repository,
        captcha=_captcha_verifier(),
        rate_limiter=_rate_limiter,
        clock=_clock,
    )


SubmitUseCase = Annotated[SubmitMuseumQuestion, Depends(get_submit_use_case)]
