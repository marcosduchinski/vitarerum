"""Unit tests for Identity's published PermissionReader.list_by_group.

Backs the Collection Object Index curator-candidates endpoint: it must return
only permissions in the requested group, hydrated with user name/email."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.identity.application.use_cases import CreateUser
from app.identity.domain.enums import GroupName
from app.identity.domain.models import GroupId, Permission, PermissionId, UserId
from app.identity.infrastructure.models import GroupRecord, InstitutionRecord
from app.identity.infrastructure.repositories import (
    SqlAlchemyPermissionReader,
    SqlAlchemyPermissionRepository,
    SqlAlchemyUserRepository,
)


async def _session() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def test_list_by_group_returns_only_that_group_sorted_by_name() -> None:
    factory = await _session()
    async with factory() as session:
        session.add(
            InstitutionRecord(id="i1", name="MUHNAC", email="", address="", phone="")
        )
        session.add_all(
            [
                GroupRecord(id="g-cur", name=GroupName.CURATORIAL, institution_id="i1"),
                GroupRecord(id="g-adm", name=GroupName.SYS_ADMIN, institution_id="i1"),
            ]
        )
        user_repo = SqlAlchemyUserRepository(session)
        await CreateUser(user_repo).execute(name="Bea", email="bea@example.org")
        await CreateUser(user_repo).execute(name="Ana", email="ana@example.org")
        await CreateUser(user_repo).execute(name="Carl", email="carl@example.org")
        bea = await user_repo.get_by_email("bea@example.org")
        ana = await user_repo.get_by_email("ana@example.org")
        carl = await user_repo.get_by_email("carl@example.org")
        assert bea is not None and ana is not None and carl is not None

        perm_repo = SqlAlchemyPermissionRepository(session)
        await perm_repo.add(
            Permission(
                id=PermissionId("p-bea"),
                user_id=UserId(bea.id),
                group_id=GroupId("g-cur"),
            )
        )
        await perm_repo.add(
            Permission(
                id=PermissionId("p-ana"),
                user_id=UserId(ana.id),
                group_id=GroupId("g-cur"),
            )
        )
        await perm_repo.add(
            Permission(
                id=PermissionId("p-carl"),
                user_id=UserId(carl.id),
                group_id=GroupId("g-adm"),
            )
        )

        reader = SqlAlchemyPermissionReader(session)
        candidates = await reader.list_by_group(GroupName.CURATORIAL)

    assert [c.user.name for c in candidates] == ["Ana", "Bea"]
    assert all(c.group == GroupName.CURATORIAL for c in candidates)
    assert {c.user.email for c in candidates} == {"ana@example.org", "bea@example.org"}
