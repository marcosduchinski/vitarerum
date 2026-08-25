from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.scientific_return.domain.bench_models import (
    TestSourceKind as SourceKind,
)
from app.scientific_return.domain.bench_models import (
    TestSubject as Subject,
)
from app.scientific_return.infrastructure.bench_repository import (
    SqlAlchemyBenchRepository,
)
from app.shared.field_encryption import FieldEncryptor

pytestmark = [pytest.mark.postgres, pytest.mark.asyncio]

_PRODUCTION_TABLES = (
    "scientific_return_runs",
    "scientific_return_candidates",
    "scientific_return_agent_analyses",
    "sr_full_agentic_investigations",
)


async def _production_counts(session: AsyncSession) -> tuple[int, ...]:
    counts: list[int] = []
    for table in _PRODUCTION_TABLES:
        result = await session.execute(text(f"SELECT count(*) FROM {table}"))
        counts.append(int(result.scalar_one()))
    return tuple(counts)


async def test_postgres_round_trip_claim_constraints_and_decimal() -> None:
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL DATABASE_URL is required")
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"PostgreSQL is not reachable: {exc}")
        async with factory() as session:
            repository = SqlAlchemyBenchRepository(
                session, FieldEncryptor.from_base64(settings.db_field_encryption_key)
            )
            production_before = await _production_counts(session)
            suffix = uuid4().hex
            source = await repository.create_source(
                institution_id=str(uuid4()),
                actor_id=str(uuid4()),
                name=f"Test source {suffix}",
                kind=SourceKind.TEXT_DOCUMENT,
                content="Maria Silva studied Acontias mukwando MUHNAC/MB03-001524.",
                locator="doi:10.0000/test",
                authors=["Maria Silva"],
            )
            batch = await repository.create_batch(
                source.institution_id, str(uuid4()), f"Batch {suffix}", None
            )
            items = await repository.add_items(
                batch.id,
                batch.institution_id,
                [Subject("Maria Silva", "Acontias mukwando", "MUHNAC/MB03-001524")],
            )
            await repository.select_sources(batch.id, batch.institution_id, [source.id])
            _, pending = await repository.start_batch(
                batch.id, batch.institution_id, f"bench-{suffix}"
            )
            assert pending == [items[0].id]
            assert await repository.claim_and_execute(items[0].id, "postgres-test")
            rows = await repository.candidates(batch.id, batch.institution_id)
            assert len(rows) == 1
            assert rows[0]["score"] == Decimal("1.00000")
            assert str(rows[0]["evidence"]) in (
                "Maria Silva studied Acontias mukwando MUHNAC/MB03-001524."
            )
            production_after = await _production_counts(session)
            assert production_after == production_before
            await session.rollback()
    finally:
        await engine.dispose()


async def test_a_resumed_item_replays_its_attempt_instead_of_duplicating_it() -> None:
    """A worker that dies mid-item leaves RUNNING with an expired lease.

    The attempt fingerprint is unique, so re-executing the same attempt number
    must reuse the row: inserting a second one poisons the item and the
    recovery worker then burns every pass on it without making progress.
    """
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL DATABASE_URL is required")
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"PostgreSQL is not reachable: {exc}")
        async with factory() as session:
            repository = SqlAlchemyBenchRepository(
                session, FieldEncryptor.from_base64(settings.db_field_encryption_key)
            )
            suffix = uuid4().hex
            source = await repository.create_source(
                institution_id=str(uuid4()),
                actor_id=str(uuid4()),
                name=f"Resumed source {suffix}",
                kind=SourceKind.TEXT_DOCUMENT,
                content="Maria Silva studied Acontias mukwando MUHNAC/MB03-001524.",
                locator=None,
                authors=["Maria Silva"],
            )
            batch = await repository.create_batch(
                source.institution_id, str(uuid4()), f"Resumed batch {suffix}", None
            )
            items = await repository.add_items(
                batch.id,
                batch.institution_id,
                [Subject("Maria Silva", "Acontias mukwando", "MUHNAC/MB03-001524")],
            )
            await repository.select_sources(batch.id, batch.institution_id, [source.id])
            await repository.start_batch(
                batch.id, batch.institution_id, f"resumed-{suffix}"
            )
            item_id = items[0].id
            assert await repository.claim_and_execute(item_id, "worker-1")
            attempts_before = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM sr_test_search_attempts WHERE item_id=:i"
                    ),
                    {"i": item_id},
                )
            ).scalar_one()

            await session.execute(
                text(
                    "UPDATE sr_test_items SET status='RUNNING', "
                    "lease_expires_at = now() - interval '10 minutes' "
                    "WHERE id = :id"
                ),
                {"id": item_id},
            )
            assert await repository.claim_and_execute(item_id, "worker-2")

            attempts = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM sr_test_search_attempts WHERE item_id=:i"
                    ),
                    {"i": item_id},
                )
            ).scalar_one()
            status_after = (
                await session.execute(
                    text("SELECT status FROM sr_test_items WHERE id=:i"),
                    {"i": item_id},
                )
            ).scalar_one()
            rows = await repository.candidates(batch.id, batch.institution_id)

            # The replay reuses the rows of the interrupted run instead of
            # inserting a second attempt per floor search.
            assert attempts_before >= 1
            assert attempts == attempts_before
            assert status_after == "COMPLETED"
            assert len(rows) == 1
            await session.rollback()
    finally:
        await engine.dispose()


async def test_a_database_failure_marks_the_item_error_instead_of_escaping() -> None:
    """The handler must not write onto a transaction PostgreSQL has aborted."""
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL DATABASE_URL is required")
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"PostgreSQL is not reachable: {exc}")
        async with factory() as session:
            repository = SqlAlchemyBenchRepository(
                session, FieldEncryptor.from_base64(settings.db_field_encryption_key)
            )
            suffix = uuid4().hex
            source = await repository.create_source(
                institution_id=str(uuid4()),
                actor_id=str(uuid4()),
                name=f"Failing source {suffix}",
                kind=SourceKind.TEXT_DOCUMENT,
                content="Maria Silva studied Acontias mukwando MUHNAC/MB03-001524.",
                locator=None,
                authors=["Maria Silva"],
            )
            batch = await repository.create_batch(
                source.institution_id, str(uuid4()), f"Failing batch {suffix}", None
            )
            items = await repository.add_items(
                batch.id,
                batch.institution_id,
                [Subject("Maria Silva", "Acontias mukwando", "MUHNAC/MB03-001524")],
            )
            await repository.select_sources(batch.id, batch.institution_id, [source.id])
            await repository.start_batch(
                batch.id, batch.institution_id, f"failing-{suffix}"
            )
            await session.commit()

            async def broken(item, batch_record):  # type: ignore[no-untyped-def]
                await session.execute(text("SELECT 1 FROM does_not_exist"))

            repository._execute_claimed = broken  # type: ignore[method-assign]
            assert await repository.claim_and_execute(items[0].id, "worker-1")
            await session.commit()

            status_after, code = (
                await session.execute(
                    text("SELECT status, error_code FROM sr_test_items WHERE id=:i"),
                    {"i": items[0].id},
                )
            ).one()
            batch_after = (
                await session.execute(
                    text("SELECT status FROM sr_test_batches WHERE id=:i"),
                    {"i": batch.id},
                )
            ).scalar_one()

            assert status_after == "ERROR"
            assert code == "TEST_ITEM_EXECUTION_FAILED"
            assert batch_after == "FAILED"
    finally:
        await engine.dispose()
