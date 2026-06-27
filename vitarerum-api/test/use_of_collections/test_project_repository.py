from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.use_of_collections.application.ports import ProjectFilters, ProposalFilters
from app.use_of_collections.domain.enums import ProposalStatus, UseStatus, UseType
from app.use_of_collections.domain.models import (
    CollectionUseProject,
    CollectionUseProjectId,
    IntendedUse,
    PermissionId,
    Proposal,
    ProposalId,
    ReferenceNumber,
)
from app.use_of_collections.infrastructure.repositories import (
    SqlAlchemyCollectionUseProjectRepository,
    SqlAlchemyProposalRepository,
)


async def test_project_list_filters_requested_by_before_pagination() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        project_repo = SqlAlchemyCollectionUseProjectRepository(session)
        proposal_repo = SqlAlchemyProposalRepository(session)

        foreign_project = CollectionUseProject(
            id=CollectionUseProjectId("project-foreign"),
            reference_number=ReferenceNumber("CUP-FOREIGN1"),
            title="Foreign project",
            purpose="Restricted",
            intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
            status=UseStatus.CREATED,
            begin_date=date(2026, 7, 1),
            end_date=date(2026, 7, 7),
            requested_by=PermissionId("permission-foreign"),
            proposal_id=ProposalId("proposal-foreign"),
        )
        own_project = CollectionUseProject(
            id=CollectionUseProjectId("project-own"),
            reference_number=ReferenceNumber("CUP-OWN00001"),
            title="Own project",
            purpose="Visible",
            intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
            status=UseStatus.CREATED,
            begin_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            requested_by=PermissionId("permission-own"),
            proposal_id=ProposalId("proposal-own"),
        )
        await project_repo.add(foreign_project)
        await project_repo.add(own_project)
        await proposal_repo.add(
            Proposal(
                id=ProposalId("proposal-foreign"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=foreign_project.id,
                intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.APPROVED,
                requested_by=PermissionId("permission-foreign"),
                submitted_at=datetime(2026, 6, 1, tzinfo=UTC),
            )
        )
        await proposal_repo.add(
            Proposal(
                id=ProposalId("proposal-own"),
                reference_number=ReferenceNumber("VRP-20260602-0001"),
                title="Proposal title",
                collection_use_project_id=own_project.id,
                intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.APPROVED,
                requested_by=PermissionId("permission-own"),
                submitted_at=datetime(2026, 6, 2, tzinfo=UTC),
            )
        )
        await session.commit()

        projects, total = await project_repo.list(
            ProjectFilters(requested_by="permission-own"),
            page=0,
            size=1,
        )

    await engine.dispose()

    assert total == 1
    assert [project.id for project in projects] == ["project-own"]


async def test_proposal_list_searches_proposal_title_without_project() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        proposal_repo = SqlAlchemyProposalRepository(session)
        await proposal_repo.add(
            Proposal(
                id=ProposalId("proposal-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Manuscript research request",
                collection_use_project_id=CollectionUseProjectId("project-1"),
                intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 1, tzinfo=UTC),
            )
        )
        await session.commit()

        proposals, total = await proposal_repo.list(
            ProposalFilters(search="manuscript"),
            page=0,
            size=10,
        )

    await engine.dispose()

    assert total == 1
    assert [proposal.id for proposal in proposals] == ["proposal-1"]


async def test_proposal_list_filters_by_multiple_statuses() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        proposal_repo = SqlAlchemyProposalRepository(session)
        for index, status in enumerate(
            (
                ProposalStatus.REJECTED,
                ProposalStatus.CANCELLED,
                ProposalStatus.PENDING,
            ),
            start=1,
        ):
            await proposal_repo.add(
                Proposal(
                    id=ProposalId(f"proposal-{index}"),
                    reference_number=ReferenceNumber(
                        f"VRP-20260601-{index:04d}"
                    ),
                    title=f"Proposal {index}",
                    collection_use_project_id=CollectionUseProjectId(
                        f"project-{index}"
                    ),
                    intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
                    begin_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 7),
                    status=status,
                    requested_by=PermissionId("permission-1"),
                    submitted_at=datetime(2026, 6, index, tzinfo=UTC),
                )
            )
        await session.commit()

        proposals, total = await proposal_repo.list(
            ProposalFilters(
                statuses=(ProposalStatus.REJECTED, ProposalStatus.CANCELLED)
            ),
            page=0,
            size=100,
        )

    await engine.dispose()

    assert total == 2
    assert {proposal.status for proposal in proposals} == {
        ProposalStatus.REJECTED,
        ProposalStatus.CANCELLED,
    }
