from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.identity.public import Actor, GroupName, PermissionId
from app.reference_numbers.application.use_cases import (
    ActivateReferencePolicy,
    CreateReferencePolicy,
    DeactivateReferencePolicy,
    PreviewReferencePolicy,
    ValidateReferenceNumber,
)
from app.reference_numbers.domain.models import ReferenceKind
from app.reference_numbers.infrastructure.repositories import (
    SqlAlchemyReferencePolicyRepository,
)
from app.shared.exceptions import InsufficientGroup

_SYS_ADMIN = Actor(
    id=PermissionId("perm-admin"), group=GroupName.SYS_ADMIN, email="admin@museum.pt"
)
_STAFF = Actor(
    id=PermissionId("perm-staff"),
    group=GroupName.CURATORIAL,
    email="staff@museum.pt",
)


@asynccontextmanager
async def _session(
    *, enforce_foreign_keys: bool = False
) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    if enforce_foreign_keys:
        # SQLite does not enforce FOREIGN KEY constraints unless this pragma is
        # set per-connection — without it, an insert-ordering bug between
        # unrelated mapped tables (no ORM relationship(), just a raw FK
        # column) silently "works" here while failing on real PostgreSQL.
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_foreign_keys(dbapi_connection: object, _record: object) -> None:
            dbapi_connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def test_validate_reference_number_ignores_never_activated_draft_policy() -> None:
    async with _session() as session:
        repository = SqlAlchemyReferencePolicyRepository(session)
        await CreateReferencePolicy(repository).execute(
            kind=ReferenceKind.COLLECTION_USE_PROJECT,
            mask="TEST-XXXX",
            caller=_SYS_ADMIN,
        )
        await session.commit()

        is_valid = await ValidateReferenceNumber(repository).execute(
            kind=ReferenceKind.COLLECTION_USE_PROJECT, value="TEST-0007"
        )

    assert is_valid is False


async def test_add_policy_does_not_violate_the_event_foreign_key() -> None:
    """Regression test for a real PostgreSQL failure: creating a policy adds
    both the policy row and its CREATED event in one call. There is no ORM
    relationship() wiring the two tables together (only a raw FK column), so
    without explicit ordering SQLAlchemy is free to emit the event insert
    before the policy insert — which is exactly what happened in production.
    SQLite ignores FK violations unless foreign_keys is explicitly turned on,
    which is why this needs its own enforcing session rather than the default
    one used by the other tests in this module."""
    async with _session(enforce_foreign_keys=True) as session:
        repository = SqlAlchemyReferencePolicyRepository(session)
        await CreateReferencePolicy(repository).execute(
            kind=ReferenceKind.PROPOSAL,
            mask="TEST-XXXX",
            caller=_SYS_ADMIN,
        )
        await session.commit()


async def test_activate_and_deactivate_do_not_violate_the_event_foreign_key() -> None:
    """Same class of bug as test_add_policy_does_not_violate_the_event_foreign_key,
    for the save() path used by activate/deactivate — covered as a safety net
    even though save()'s event always references an already-committed policy
    row, unlike add()'s."""
    async with _session(enforce_foreign_keys=True) as session:
        repository = SqlAlchemyReferencePolicyRepository(session)
        created = await CreateReferencePolicy(repository).execute(
            kind=ReferenceKind.PROPOSAL, mask="TEST-XXXX", caller=_SYS_ADMIN
        )
        await session.commit()

        activated = await ActivateReferencePolicy(repository).execute(
            policy_id=created.id, caller=_SYS_ADMIN
        )
        await session.commit()

        await DeactivateReferencePolicy(repository).execute(
            policy_id=activated.id, caller=_SYS_ADMIN
        )
        await session.commit()


async def test_preview_reference_policy_requires_sys_admin() -> None:
    with pytest.raises(InsufficientGroup):
        PreviewReferencePolicy().execute(
            kind=ReferenceKind.COLLECTION_USE_PROJECT,
            mask="MUHNAC/COL/YYYY/XXXX",
            sample_date=date(2026, 7, 23),
            caller=_STAFF,
        )
