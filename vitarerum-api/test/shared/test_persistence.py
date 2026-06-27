"""Tests for the unique-conflict retry helper (#3)."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.shared.persistence import run_with_unique_retry


async def _session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


def _conflict() -> IntegrityError:
    return IntegrityError("INSERT ...", {}, Exception("UNIQUE constraint failed"))


async def test_retries_until_success() -> None:
    factory = await _session()
    calls = {"n": 0}

    async def operation() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _conflict()
        return "ok"

    async with factory() as session:
        result = await run_with_unique_retry(session, operation, attempts=5)

    assert result == "ok"
    assert calls["n"] == 3


async def test_reraises_after_exhausting_attempts() -> None:
    factory = await _session()
    calls = {"n": 0}

    async def operation() -> str:
        calls["n"] += 1
        raise _conflict()

    async with factory() as session:
        with pytest.raises(IntegrityError):
            await run_with_unique_retry(session, operation, attempts=3)

    assert calls["n"] == 3
