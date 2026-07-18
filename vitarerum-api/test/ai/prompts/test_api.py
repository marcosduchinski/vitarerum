from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

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
from app.database import Base, get_async_session
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission

_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="s@museum.pt"
)
_EXTERNAL = Actor(
    id=PermissionId("perm-ext"), group=GroupName.EXTERNAL, email="r@uni.pt"
)


@asynccontextmanager
async def _client(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    caller: Actor = _STAFF,
) -> AsyncIterator[AsyncClient]:
    async def session_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_async_session] = session_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def _session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return session_factory


async def _seed_template(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[PromptTemplate, PromptTemplateVersion]:
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
            content="Original frozen prompt.",
            default_temperature=0.3,
            created_by="system",
        ).publish(published_by="system")
        await repo.add_version(version)
        await repo.save_template(template.activate(version.id))
        await session.commit()
        return template, version


async def test_staff_can_list_ai_prompt_templates() -> None:
    session_factory = await _session_factory()
    await _seed_template(session_factory)

    async with _client(session_factory) as client:
        resp = await client.get("/api/v1/ai/prompts")

    assert resp.status_code == 200
    body = resp.json()
    assert [template["key"] for template in body] == ["system_institutional"]
    assert body[0]["purpose"] == "in_situ_narrative"
    assert body[0]["activeVersionId"] is not None


async def test_external_user_cannot_read_publish_or_archive_ai_prompts() -> None:
    session_factory = await _session_factory()
    _template, version = await _seed_template(session_factory)

    async with _client(session_factory, caller=_EXTERNAL) as client:
        list_resp = await client.get("/api/v1/ai/prompts")
        publish_resp = await client.post(
            f"/api/v1/ai/prompts/versions/{version.id}/publish"
        )
        archive_resp = await client.post(
            f"/api/v1/ai/prompts/versions/{version.id}/archive"
        )

    assert list_resp.status_code == 403
    assert publish_resp.status_code == 403
    assert archive_resp.status_code == 403


async def test_prompt_version_endpoint_returns_frozen_content_after_republish() -> None:
    session_factory = await _session_factory()
    template, first = await _seed_template(session_factory)

    async with _client(session_factory) as client:
        draft_resp = await client.post(
            f"/api/v1/ai/prompts/{template.id}/versions",
            json={
                "version_label": "museum-narrative-institutional-v2",
                "content": "Replacement prompt.",
                "default_temperature": 0.3,
            },
        )
        assert draft_resp.status_code == 201
        second_id = draft_resp.json()["id"]
        publish_resp = await client.post(
            f"/api/v1/ai/prompts/versions/{second_id}/publish"
        )
        first_resp = await client.get(f"/api/v1/ai/prompts/versions/{first.id}")

    assert publish_resp.status_code == 200
    assert publish_resp.json()["content"] == "Replacement prompt."
    assert first_resp.status_code == 200
    assert first_resp.json()["id"] == first.id
    assert first_resp.json()["content"] == "Original frozen prompt."
    assert first_resp.json()["status"] == "archived"


async def test_create_draft_rejects_blank_content_without_500() -> None:
    session_factory = await _session_factory()
    template, _version = await _seed_template(session_factory)

    async with _client(session_factory) as client:
        resp = await client.post(
            f"/api/v1/ai/prompts/{template.id}/versions",
            json={
                "version_label": "museum-narrative-institutional-v2",
                "content": "   ",
                "default_temperature": 0.3,
            },
        )

    assert resp.status_code == 422
    assert resp.json()["message"] == "Validation failed"


async def test_create_draft_rejects_blank_version_label_without_persisting() -> None:
    session_factory = await _session_factory()
    template, _version = await _seed_template(session_factory)

    async with _client(session_factory) as client:
        resp = await client.post(
            f"/api/v1/ai/prompts/{template.id}/versions",
            json={
                "version_label": "   ",
                "content": "Real content.",
                "default_temperature": 0.3,
            },
        )
        versions_resp = await client.get(f"/api/v1/ai/prompts/{template.id}/versions")

    assert resp.status_code == 422
    assert resp.json()["message"] == "Validation failed"
    assert [version["versionLabel"] for version in versions_resp.json()] == [
        "museum-narrative-institutional-v1"
    ]
