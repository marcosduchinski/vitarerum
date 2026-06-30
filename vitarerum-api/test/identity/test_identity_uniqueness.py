"""Integration tests for the identity uniqueness invariants (#2): case-insensitive
unique email and one permission per (user_id, group_id)."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.identity.application.use_cases import CreateUser
from app.identity.domain.enums import GroupName
from app.identity.domain.models import GroupId, Permission, PermissionId, UserId
from app.identity.infrastructure.models import GroupRecord, InstitutionRecord
from app.identity.infrastructure.repositories import (
    SqlAlchemyPermissionRepository,
    SqlAlchemyUserRepository,
)


async def _session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def test_duplicate_email_is_rejected_case_insensitively() -> None:
    factory = await _session()
    async with factory() as session:
        repo = SqlAlchemyUserRepository(session)
        await CreateUser(repo).execute(name="Alice", email="Alice@Example.ORG")
        # Same address, different casing/whitespace → normalized to the same key.
        with pytest.raises(IntegrityError):
            await CreateUser(repo).execute(name="Alice 2", email="  alice@example.org ")


async def test_duplicate_permission_is_rejected() -> None:
    factory = await _session()
    async with factory() as session:
        session.add(
            InstitutionRecord(id="i1", name="MUHNAC", email="", address="", phone="")
        )
        session.add(
            GroupRecord(id="g1", name=GroupName.CURATORIAL, institution_id="i1")
        )
        user_repo = SqlAlchemyUserRepository(session)
        await CreateUser(user_repo).execute(name="Bob", email="bob@example.org")
        user = await user_repo.get_by_email("bob@example.org")
        assert user is not None

        perm_repo = SqlAlchemyPermissionRepository(session)
        await perm_repo.add(
            Permission(
                id=PermissionId("p1"),
                user_id=UserId(user.id),
                group_id=GroupId("g1"),
            )
        )
        with pytest.raises(IntegrityError):
            await perm_repo.add(
                Permission(
                    id=PermissionId("p2"),
                    user_id=UserId(user.id),
                    group_id=GroupId("g1"),
                )
            )
