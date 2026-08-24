from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.scientific_return.application.ports import (
    BibliographicRecord,
    BibliographicSource,
)


class PostgresBibliographicSourceRateLimiter:
    """Reserves a global time slot without holding a connection while waiting."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def acquire(self, source: str, interval_seconds: float) -> None:
        interval = timedelta(seconds=max(0.0, interval_seconds))
        now = datetime.now(tz=UTC)
        async with self._sessions() as session:
            result = await session.execute(
                text(
                    "INSERT INTO sr_source_throttles(source, next_allowed_at) "
                    "VALUES (:source, :now + :interval) "
                    "ON CONFLICT (source) DO UPDATE SET next_allowed_at = "
                    "GREATEST(sr_source_throttles.next_allowed_at, :now) + :interval "
                    "RETURNING next_allowed_at - :interval AS reserved_at"
                ),
                {"source": source.upper(), "now": now, "interval": interval},
            )
            reserved_at = result.scalar_one()
            await session.commit()
        delay = (reserved_at - datetime.now(tz=UTC)).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)


class RateLimitedBibliographicSource:
    def __init__(
        self,
        source: BibliographicSource,
        limiter: PostgresBibliographicSourceRateLimiter,
        interval_seconds: float,
    ) -> None:
        self._source = source
        self._limiter = limiter
        self._interval = interval_seconds
        self.name = source.name

    async def search(
        self, query: str, limit: int, *, author: str | None = None
    ) -> list[BibliographicRecord]:
        await self._limiter.acquire(self.name, self._interval)
        return await self._source.search(query, limit, author=author)
