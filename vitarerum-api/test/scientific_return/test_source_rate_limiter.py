"""Integration tests for the global source throttle, against real PostgreSQL.

These must not run on SQLite. The reservation statement uses ``GREATEST`` and
PostgreSQL's operator resolution, and the failure that reached a curator --
``operator is not unique: unknown + unknown`` -- is a PostgreSQL parse-time
error that no other backend can raise. asyncpg does not declare parameter types
in its Parse message, so every bind parameter arrives as ``unknown`` and the
timestamp/interval arithmetic has to be pinned by an explicit cast in the SQL.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.scientific_return.infrastructure.source_rate_limiter import (
    PostgresBibliographicSourceRateLimiter,
    RateLimitedBibliographicSource,
)

_SOURCE = "TEST_THROTTLE_SOURCE"


@pytest.fixture
async def sessions() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment guard
        await engine.dispose()
        pytest.skip(f"PostgreSQL is not reachable at settings.database_url: {exc}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(
            text("DELETE FROM sr_source_throttles WHERE source = :s"),
            {"s": _SOURCE},
        )
        await session.commit()
    try:
        yield factory
    finally:
        async with factory() as session:
            await session.execute(
                text("DELETE FROM sr_source_throttles WHERE source = :s"),
                {"s": _SOURCE},
            )
            await session.commit()
        await engine.dispose()


async def test_acquire_reserves_a_slot_on_a_fresh_source(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The first acquire must execute, not raise AmbiguousFunctionError."""
    limiter = PostgresBibliographicSourceRateLimiter(sessions)

    await limiter.acquire(_SOURCE, 0.0)

    async with sessions() as session:
        stored = (
            await session.execute(
                text("SELECT next_allowed_at FROM sr_source_throttles WHERE source=:s"),
                {"s": _SOURCE},
            )
        ).scalar_one()
    assert stored is not None


async def test_acquire_advances_the_window_on_conflict(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The ON CONFLICT branch has its own timestamp/interval arithmetic."""
    limiter = PostgresBibliographicSourceRateLimiter(sessions)

    await limiter.acquire(_SOURCE, 0.0)
    async with sessions() as session:
        first = (
            await session.execute(
                text("SELECT next_allowed_at FROM sr_source_throttles WHERE source=:s"),
                {"s": _SOURCE},
            )
        ).scalar_one()

    await limiter.acquire(_SOURCE, 0.5)
    async with sessions() as session:
        second = (
            await session.execute(
                text("SELECT next_allowed_at FROM sr_source_throttles WHERE source=:s"),
                {"s": _SOURCE},
            )
        ).scalar_one()

    assert second > first


async def test_second_caller_waits_for_the_reserved_interval(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The interval is honoured as a real delay, not silently dropped."""
    limiter = PostgresBibliographicSourceRateLimiter(sessions)
    interval = 0.4

    await limiter.acquire(_SOURCE, interval)
    started = time.monotonic()
    await limiter.acquire(_SOURCE, interval)
    waited = time.monotonic() - started

    assert waited >= interval * 0.8


async def test_source_name_is_normalised_to_upper_case(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    limiter = PostgresBibliographicSourceRateLimiter(sessions)

    await limiter.acquire(_SOURCE.lower(), 0.0)

    async with sessions() as session:
        count = (
            await session.execute(
                text("SELECT count(*) FROM sr_source_throttles WHERE source=:s"),
                {"s": _SOURCE},
            )
        ).scalar_one()
    assert count == 1


async def test_reserved_slot_is_never_in_the_future_of_its_own_window(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """RETURNING subtracts the interval; that expression is ambiguous too."""
    limiter = PostgresBibliographicSourceRateLimiter(sessions)

    before = datetime.now(tz=UTC)
    await limiter.acquire(_SOURCE, 0.0)

    async with sessions() as session:
        stored = (
            await session.execute(
                text("SELECT next_allowed_at FROM sr_source_throttles WHERE source=:s"),
                {"s": _SOURCE},
            )
        ).scalar_one()
    assert stored >= before


async def test_wrapped_source_throttles_before_delegating(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The wrapper is what both flows actually call through."""
    calls: list[str] = []

    class _FakeSource:
        name = _SOURCE

        async def search(
            self, query: str, limit: int, *, author: str | None = None
        ) -> list[object]:
            calls.append(query)
            return []

    wrapped = RateLimitedBibliographicSource(
        _FakeSource(),  # type: ignore[arg-type]
        PostgresBibliographicSourceRateLimiter(sessions),
        0.0,
    )

    assert await wrapped.search("any query", 5) == []
    assert calls == ["any query"]
