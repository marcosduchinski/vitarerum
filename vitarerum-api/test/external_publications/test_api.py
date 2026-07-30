from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_async_session
from app.external_publications.application.ports import (
    PublishedObjectView,
    PublishedProposalView,
)
from app.external_publications.application.use_cases import (
    ResolveExternalPublicationOutput,
)
from app.external_publications.domain.models import (
    ExternalProposalStatus,
    ExternalPublication,
    ExternalPublicationAccessMode,
    ExternalPublicationId,
    ExternalPublicationProfile,
    ExternalPublicationResourceType,
    ExternalPublicationStatus,
)
from app.external_publications.presentation.dependencies import (
    get_json_ld_use_case,
    get_resolve_use_case,
)
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.shared.dependencies import get_caller_permission
from app.shared.kernel import UseType

_SYS_ADMIN = Actor(
    id=PermissionId("perm-admin"), group=GroupName.SYS_ADMIN, email="admin@museum.pt"
)
_STAFF = Actor(
    id=PermissionId("perm-staff"),
    group=GroupName.CURATORIAL,
    email="staff@museum.pt",
)
_NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


@asynccontextmanager
async def _client(caller: Actor) -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def session_override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_async_session] = session_override
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_staff_cannot_manage_external_publications() -> None:
    async with _client(_STAFF) as client:
        response = await client.get("/api/v1/external-publications")

    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"


async def test_sys_admin_can_list_external_publications() -> None:
    async with _client(_SYS_ADMIN) as client:
        response = await client.get("/api/v1/external-publications")

    assert response.status_code == 200
    assert response.json()["content"] == []


async def test_public_summary_response_omits_heavy_fields() -> None:
    class Resolver:
        async def execute(
            self,
            raw_token: str,
            *,
            remote_addr_hash: str | None = None,
            user_agent: str | None = None,
        ) -> ResolveExternalPublicationOutput:
            return ResolveExternalPublicationOutput(
                publication=ExternalPublication(
                    id=ExternalPublicationId("publication-1"),
                    resource_type=ExternalPublicationResourceType.PROPOSAL,
                    resource_id="proposal-1",
                    status=ExternalPublicationStatus.PUBLISHED,
                    access_mode=ExternalPublicationAccessMode.TOKEN,
                    profile=ExternalPublicationProfile.SUMMARY,
                    token_hash="token-hash",
                    integration_client_id=None,
                    expires_at=None,
                    created_by=PermissionId("perm-admin"),
                    created_at=_NOW,
                    published_at=_NOW,
                ),
                resource=PublishedProposalView(
                    id="proposal-1",
                    reference_number="CUP-1",
                    title="Proposal",
                    purpose="private purpose",
                    intended_use=UseType.IN_SITU_VISIT,
                    status=ExternalProposalStatus.APPROVED,
                    begin_date=None,
                    end_date=None,
                    submitted_at=_NOW,
                    requested_objects=[
                        PublishedObjectView(
                            id="object-1",
                            inventory_number="INV-1",
                            category="Specimen",
                            description="private object",
                        )
                    ],
                    project_id="project-1",
                ),
            )

    app.dependency_overrides[get_resolve_use_case] = lambda: Resolver()
    async with _client(_SYS_ADMIN) as client:
        response = await client.get("/api/v1/external/publications/raw-token")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "proposal"
    assert body["purpose"] is None
    assert body["requestedObjects"] == []


async def test_json_ld_route_uses_json_ld_content_type() -> None:
    class JsonLdUseCase:
        async def execute(
            self,
            raw_token: str,
            *,
            remote_addr_hash: str | None = None,
            user_agent: str | None = None,
        ) -> dict[str, object]:
            return {"@context": {}, "@graph": []}

    app.dependency_overrides[get_json_ld_use_case] = lambda: JsonLdUseCase()
    async with _client(_SYS_ADMIN) as client:
        response = await client.get("/api/v1/external/publications/raw-token/json-ld")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/ld+json")
    assert response.json() == {"@context": {}, "@graph": []}
