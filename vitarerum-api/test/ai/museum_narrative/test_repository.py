from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.museum_narrative.domain.models import (
    GeneratedNarrative,
    NarrativeType,
    ResolutionSource,
)
from app.ai.museum_narrative.infrastructure.repositories import (
    SqlAlchemyNarrativeRepository,
)
from app.database import Base
from app.shared.kernel import PermissionId


async def test_repository_lists_revisions_oldest_first_with_editor() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as session:
            repo = SqlAlchemyNarrativeRepository(session)
            narrative = GeneratedNarrative.create(
                record_id="record-1",
                narrative="Original text.",
                resolved_narrative_type=NarrativeType.INSTITUTIONAL,
                resolution_source=ResolutionSource.DEFAULT,
                target_language="pt",
                creativity_temperature=0.3,
                llm_model="llama3.1:8b",
            )
            await repo.add(narrative)
            first = narrative.edit_narrative(
                "First edit.", edited_by=PermissionId("perm-a")
            )
            await repo.add_revision(first)
            await repo.save(narrative)
            second = narrative.edit_narrative(
                "Second edit.", edited_by=PermissionId("perm-b")
            )
            await repo.add_revision(second)
            await repo.save(narrative)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyNarrativeRepository(session)
            result = await repo.list_revisions(
                "record-1", narrative.id, page=0, size=20
            )

        assert result is not None
        revisions, total = result
        assert total == 2
        assert [revision.previous_narrative for revision in revisions] == [
            "Original text.",
            "First edit.",
        ]
        assert [revision.revised_narrative for revision in revisions] == [
            "First edit.",
            "Second edit.",
        ]
        assert [revision.edited_by for revision in revisions] == [
            "perm-a",
            "perm-b",
        ]
    finally:
        await engine.dispose()
