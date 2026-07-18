from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.museum_narrative.domain.models import NarrativeType
from app.ai.museum_narrative.domain.ports import NarrativePromptVersionMismatch
from app.ai.museum_narrative.infrastructure.prompt_acl import AiPromptRegistryAdapter
from app.ai.prompts.domain.models import (
    PromptPurpose,
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


async def test_prompt_acl_rejects_version_from_another_narrative_type() -> None:
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
            institutional = PromptTemplate.create(
                purpose=PromptPurpose.IN_SITU_NARRATIVE,
                key="system_institutional",
                name="Institutional narrative",
                description="Prompt for institutional narratives.",
                variables_schema_json='{"type":"object"}',
            )
            social = PromptTemplate.create(
                purpose=PromptPurpose.IN_SITU_NARRATIVE,
                key="system_social_media",
                name="Social media narrative",
                description="Prompt for social media narratives.",
                variables_schema_json='{"type":"object"}',
            )
            await repo.add_template(institutional)
            await repo.add_template(social)
            social_draft = PromptTemplateVersion.create_draft(
                template_id=social.id,
                version=1,
                version_label="museum-narrative-social-media-v1",
                content="Social media prompt.",
                default_temperature=0.3,
                created_by="staff-1",
            )
            await repo.add_version(social_draft)
            await session.commit()

        async with session_factory() as session:
            adapter = AiPromptRegistryAdapter(session)
            try:
                await adapter.get_version(social_draft.id, NarrativeType.INSTITUTIONAL)
            except NarrativePromptVersionMismatch as exc:
                assert "institutional" in str(exc)
            else:
                raise AssertionError("Expected NarrativePromptVersionMismatch")
    finally:
        await engine.dispose()
