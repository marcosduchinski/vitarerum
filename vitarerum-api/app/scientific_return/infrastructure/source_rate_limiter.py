from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.scientific_return.application.ports import (
    BibliographicRecord,
    BibliographicSource,
    BibliographicSourceCapabilities,
    SourceDeadlineExceeded,
    SourceRateLimitWaitExceeded,
)


class PostgresBibliographicSourceRateLimiter:
    """Reserves a global time slot without holding a connection while waiting."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        max_wait_seconds: float = 120.0,
    ) -> None:
        self._sessions = sessions
        self._max_wait_seconds = max(0.0, max_wait_seconds)

    async def acquire(self, source: str, interval_seconds: float) -> None:
        interval = timedelta(seconds=max(0.0, interval_seconds))
        now = datetime.now(tz=UTC)
        async with self._sessions() as session:
            result = await session.execute(
                # Every parameter is cast explicitly. asyncpg does not declare
                # parameter types in its Parse message, so PostgreSQL sees
                # ``unknown + unknown`` and cannot choose among the candidate
                # ``+`` operators. The casts pin the types at parse time; a
                # client-side ``bindparams(type_=...)`` would not, because the
                # ambiguity is resolved by the server from the SQL text alone.
                text(
                    "INSERT INTO sr_source_throttles(source, next_allowed_at) "
                    "VALUES (:source, CAST(:now AS timestamptz)"
                    " + CAST(:interval AS interval)) "
                    "ON CONFLICT (source) DO UPDATE SET next_allowed_at = "
                    "GREATEST(sr_source_throttles.next_allowed_at,"
                    " CAST(:now AS timestamptz))"
                    " + CAST(:interval AS interval) "
                    "RETURNING next_allowed_at"
                    " - CAST(:interval AS interval) AS reserved_at"
                ),
                {"source": source.upper(), "now": now, "interval": interval},
            )
            reserved_at = result.scalar_one()
            delay = (reserved_at - datetime.now(tz=UTC)).total_seconds()
            if delay > self._max_wait_seconds:
                # The slot is judged before it is confirmed. Committing and then
                # refusing to wait would consume a reservation nobody uses and
                # push every later caller further out, so the backlog would be
                # made worse by the very check meant to protect against it.
                await session.rollback()
                raise SourceRateLimitWaitExceeded(
                    f"{source.upper()} throttle queue is {delay:.0f}s long, above "
                    f"the {self._max_wait_seconds:.0f}s ceiling"
                )
            await session.commit()
        if delay > 0:
            await asyncio.sleep(delay)


class RateLimitedBibliographicSource:
    """Throttling and the source's own budget, under one enforced ceiling.

    The inner budget only gates what a source is allowed to *begin*, which
    leaves a slow request or a queued throttle slot free to run past it — and
    the throttle wait happened before the source's budget even started, so it
    was outside it entirely. The worker plans its slice from this number, so it
    has to be a ceiling rather than an estimate.
    """

    def __init__(
        self,
        source: BibliographicSource,
        limiter: PostgresBibliographicSourceRateLimiter,
        interval_seconds: float,
        total_timeout_seconds: float | None = None,
    ) -> None:
        self._source = source
        self._limiter = limiter
        self._interval = interval_seconds
        self._total_timeout = total_timeout_seconds
        self.name = source.name

    @property
    def capabilities(self) -> BibliographicSourceCapabilities:
        return self._source.capabilities

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        if self._total_timeout is None:
            await self._limiter.acquire(self.name, self._interval)
            return await self._source.search(query, limit, author=author)
        try:
            async with asyncio.timeout(self._total_timeout):
                await self._limiter.acquire(self.name, self._interval)
                return await self._source.search(query, limit, author=author)
        except TimeoutError as exc:
            raise SourceDeadlineExceeded(
                f"{self.name} exceeded its {self._total_timeout:.0f}s call budget"
            ) from exc
