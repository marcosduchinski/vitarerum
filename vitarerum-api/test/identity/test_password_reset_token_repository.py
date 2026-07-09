"""Unit tests for SqlAlchemyPasswordResetTokenRepository against a real
(in-memory sqlite) session — the invalidate_active_for_user bulk update in
particular is worth verifying against real SQL semantics, not a fake."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.identity.domain.models import PasswordResetToken, UserId
from app.identity.infrastructure.repositories import (
    SqlAlchemyPasswordResetTokenRepository,
)


async def _session() -> async_sessionmaker:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


def _token(
    id_: str, user_id: str, *, now: datetime, used_at: datetime | None = None
) -> PasswordResetToken:
    return PasswordResetToken(
        id=id_,
        user_id=UserId(user_id),
        token_hash=f"hash-{id_}",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        used_at=used_at,
    )


async def test_add_and_get_by_hash_roundtrip() -> None:
    factory = await _session()
    async with factory() as session:
        repo = SqlAlchemyPasswordResetTokenRepository(session)
        now = datetime.now(UTC)
        token = _token("t1", "u1", now=now)
        await repo.add(token)

        found = await repo.get_by_hash("hash-t1")
        assert found is not None
        assert found.id == "t1"
        assert found.user_id == "u1"
        assert not found.is_used


async def test_get_by_hash_unknown_returns_none() -> None:
    factory = await _session()
    async with factory() as session:
        repo = SqlAlchemyPasswordResetTokenRepository(session)
        assert await repo.get_by_hash("does-not-exist") is None


async def test_save_marks_token_used() -> None:
    factory = await _session()
    async with factory() as session:
        repo = SqlAlchemyPasswordResetTokenRepository(session)
        now = datetime.now(UTC)
        token = _token("t1", "u1", now=now)
        await repo.add(token)

        token.used_at = now
        await repo.save(token)

        found = await repo.get_by_hash("hash-t1")
        assert found is not None
        assert found.is_used


async def test_invalidate_active_for_user_marks_only_that_users_unused_tokens() -> None:
    factory = await _session()
    async with factory() as session:
        repo = SqlAlchemyPasswordResetTokenRepository(session)
        now = datetime.now(UTC)
        await repo.add(_token("t1", "u1", now=now))
        await repo.add(_token("t2", "u1", now=now, used_at=now))
        await repo.add(_token("t3", "u2", now=now))

        later = now + timedelta(minutes=5)
        await repo.invalidate_active_for_user(UserId("u1"), later)

        t1 = await repo.get_by_hash("hash-t1")
        t2 = await repo.get_by_hash("hash-t2")
        t3 = await repo.get_by_hash("hash-t3")
        # sqlite/aiosqlite round-trips datetimes as naive, dropping tzinfo — compare
        # timestamps rather than full datetime equality to sidestep that quirk.
        assert t1 is not None and t1.used_at is not None
        assert t1.used_at.replace(tzinfo=UTC).timestamp() == later.timestamp()
        assert t2 is not None and t2.used_at is not None  # already-used, stays used
        assert t3 is not None and t3.used_at is None  # other user's token untouched
