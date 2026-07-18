from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.prompts.domain.models import (
    PromptPurpose,
    PromptStatus,
    PromptTemplate,
    PromptTemplateVersion,
)
from app.ai.prompts.infrastructure.models import (  # noqa: F401
    PromptTemplateOrm,
    PromptTemplateVersionOrm,
)
from app.ai.prompts.infrastructure.repositories import (
    SqlAlchemyPromptTemplateRepository,
)
from app.database import Base


async def test_repository_resolves_published_prompt_by_purpose_and_key() -> None:
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
            repo = SqlAlchemyPromptTemplateRepository(session)
            template = PromptTemplate.create(
                purpose=PromptPurpose.IN_SITU_NARRATIVE,
                key="system_institutional",
                name="Institutional narrative",
                description="Prompt for institutional narratives.",
                variables_schema_json='{"type":"object"}',
            )
            await repo.add_template(template)
            version = PromptTemplateVersion.create_draft(
                template_id=template.id,
                version=1,
                version_label="museum-narrative-institutional-v1",
                content="Prompt text.",
                default_temperature=0.3,
                created_by="system",
            ).publish(published_by="system")
            await repo.add_version(version)
            await repo.save_template(template.activate(version.id))
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyPromptTemplateRepository(session)
            resolved = await repo.get_published_version(
                PromptPurpose.IN_SITU_NARRATIVE,
                "system_institutional",
            )
            templates = await repo.list_templates(status=PromptStatus.PUBLISHED)

        assert resolved is not None
        assert resolved.version_label == "museum-narrative-institutional-v1"
        assert resolved.content == "Prompt text."
        assert [template.key for template in templates] == ["system_institutional"]
    finally:
        await engine.dispose()


async def test_published_version_uniqueness_is_scoped_to_status() -> None:
    """The one-published-per-template index must not block coexisting draft
    and published versions for the same template — only two PUBLISHED rows
    for the same template should be rejected."""
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
            repo = SqlAlchemyPromptTemplateRepository(session)
            template = PromptTemplate.create(
                purpose=PromptPurpose.IN_SITU_NARRATIVE,
                key="system_institutional",
                name="Institutional narrative",
                description="Prompt for institutional narratives.",
                variables_schema_json='{"type":"object"}',
            )
            await repo.add_template(template)
            published = PromptTemplateVersion.create_draft(
                template_id=template.id,
                version=1,
                version_label="v1",
                content="Published content.",
                default_temperature=0.3,
                created_by="system",
            ).publish(published_by="system")
            await repo.add_version(published)
            draft = PromptTemplateVersion.create_draft(
                template_id=template.id,
                version=2,
                version_label="v2",
                content="Draft content.",
                default_temperature=0.3,
                created_by="staff-1",
            )
            await repo.add_version(draft)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyPromptTemplateRepository(session)
            versions = await repo.list_versions(template.id)

        assert {version.status for version in versions} == {
            PromptStatus.PUBLISHED,
            PromptStatus.DRAFT,
        }
    finally:
        await engine.dispose()


async def test_list_templates_filters_by_draft_status() -> None:
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
            repo = SqlAlchemyPromptTemplateRepository(session)
            template = PromptTemplate.create(
                purpose=PromptPurpose.IN_SITU_NARRATIVE,
                key="system_scientific",
                name="Scientific narrative",
                description="Prompt for scientific narratives.",
                variables_schema_json='{"type":"object"}',
            )
            await repo.add_template(template)
            draft = PromptTemplateVersion.create_draft(
                template_id=template.id,
                version=1,
                version_label="v1",
                content="Draft content awaiting review.",
                default_temperature=0.3,
                created_by="staff-1",
            )
            await repo.add_version(draft)
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyPromptTemplateRepository(session)
            draft_templates = await repo.list_templates(status=PromptStatus.DRAFT)
            published_templates = await repo.list_templates(
                status=PromptStatus.PUBLISHED
            )

        assert [t.key for t in draft_templates] == ["system_scientific"]
        assert published_templates == []
    finally:
        await engine.dispose()


async def test_list_templates_status_uses_current_state_not_archived_history() -> None:
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
            repo = SqlAlchemyPromptTemplateRepository(session)
            template = PromptTemplate.create(
                purpose=PromptPurpose.IN_SITU_NARRATIVE,
                key="system_institutional",
                name="Institutional narrative",
                description="Prompt for institutional narratives.",
                variables_schema_json='{"type":"object"}',
            )
            await repo.add_template(template)
            archived = (
                PromptTemplateVersion.create_draft(
                    template_id=template.id,
                    version=1,
                    version_label="v1",
                    content="Archived content.",
                    default_temperature=0.3,
                    created_by="system",
                )
                .publish(published_by="system")
                .archive_as_replaced()
            )
            published = PromptTemplateVersion.create_draft(
                template_id=template.id,
                version=2,
                version_label="v2",
                content="Published content.",
                default_temperature=0.3,
                created_by="staff-1",
            ).publish(published_by="staff-1")
            await repo.add_version(archived)
            await repo.add_version(published)
            await repo.save_template(template.activate(published.id))
            await session.commit()

        async with session_factory() as session:
            repo = SqlAlchemyPromptTemplateRepository(session)
            archived_templates = await repo.list_templates(status=PromptStatus.ARCHIVED)
            published_templates = await repo.list_templates(
                status=PromptStatus.PUBLISHED
            )

        assert archived_templates == []
        assert [template.key for template in published_templates] == [
            "system_institutional"
        ]
    finally:
        await engine.dispose()
