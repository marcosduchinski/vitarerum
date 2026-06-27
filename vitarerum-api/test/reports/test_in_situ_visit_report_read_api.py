"""Integration tests for the in-situ visit report read endpoints.

Unlike the write test (which fakes the two composed contexts), these run against
a real in-memory SQLite database so the repository SQL — project filtering,
newest-first ordering, and get-by-id ownership — is actually exercised.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.cidoc_crm.in_situ_visit_mapping.domain.models import InSituVisitRecord
from app.cidoc_crm.in_situ_visit_mapping.infrastructure.repositories import (
    SqlAlchemyInSituVisitRecordRepository,
)
from app.database import Base, get_async_session
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.reports.in_situ_visit.domain.models import InSituVisitReport
from app.reports.in_situ_visit.infrastructure.repositories import (
    SqlAlchemyInSituVisitReportRepository,
)
from app.shared.dependencies import get_caller_permission

_STAFF = Actor(
    id=PermissionId("perm-staff"), group=GroupName.CURATORIAL, email="s@museum.pt"
)
_EXTERNAL = Actor(
    id=PermissionId("perm-ext"), group=GroupName.EXTERNAL, email="r@uni.pt"
)


def _report(project_id: str, *, at: datetime) -> InSituVisitReport:
    report = InSituVisitReport.create(
        created_by=PermissionId("perm-staff"),
        project_id=project_id,
        narrative_id=f"nar-{project_id}-{at.isoformat()}",
        in_situ_visit_record_id=f"rec-{project_id}-{at.isoformat()}",
    )
    report.created_at = at
    return report


@asynccontextmanager
async def _client(
    *, caller: Actor = _STAFF
) -> AsyncIterator[tuple[AsyncClient, list[InSituVisitReport]]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    now = datetime.now(UTC)
    # Two reports for p1 (older + newer) and one for p2.
    older = _report("p1", at=now - timedelta(hours=1))
    newer = _report("p1", at=now)
    other = _report("p2", at=now)
    async with session_factory() as session:
        repo = SqlAlchemyInSituVisitReportRepository(session)
        for report in (older, newer, other):
            await repo.add(report)
        await session.commit()

    async def _override_session() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _override_session
    app.dependency_overrides[get_caller_permission] = lambda: caller
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, [older, newer, other]
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_list_returns_project_reports_newest_first() -> None:
    async with _client() as (client, (older, newer, _other)):
        resp = await client.get("/api/v1/reports/collection-use/p1/in_situ_visit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalElements"] == 2
    assert body["totalPages"] == 1
    ids = [item["id"] for item in body["content"]]
    assert ids == [newer.id, older.id]


async def test_list_isolated_per_project() -> None:
    async with _client() as (client, (_older, _newer, other)):
        resp = await client.get("/api/v1/reports/collection-use/p2/in_situ_visit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalElements"] == 1
    assert body["content"][0]["id"] == other.id


async def test_list_unknown_project_is_empty_page() -> None:
    async with _client() as (client, _seed):
        resp = await client.get("/api/v1/reports/collection-use/nope/in_situ_visit")
    assert resp.status_code == 200
    assert resp.json()["totalElements"] == 0


async def test_list_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as (client, _seed):
        resp = await client.get("/api/v1/reports/collection-use/p1/in_situ_visit")
    assert resp.status_code == 403


async def test_get_by_id_returns_report() -> None:
    async with _client() as (client, (_older, newer, _other)):
        resp = await client.get(
            f"/api/v1/reports/collection-use/p1/in_situ_visit/{newer.id}"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == newer.id
    assert body["projectId"] == "p1"
    assert body["narrativeId"] == newer.narrative_id


async def test_get_by_id_unknown_is_404() -> None:
    async with _client() as (client, _seed):
        resp = await client.get(
            "/api/v1/reports/collection-use/p1/in_situ_visit/missing"
        )
    assert resp.status_code == 404
    assert resp.json()["error"] == "REPORT_NOT_FOUND"


async def test_get_by_id_wrong_project_is_404() -> None:
    # The report exists but under p2, so fetching it under p1 must 404.
    async with _client() as (client, (_older, _newer, other)):
        resp = await client.get(
            f"/api/v1/reports/collection-use/p1/in_situ_visit/{other.id}"
        )
    assert resp.status_code == 404
    assert resp.json()["error"] == "REPORT_NOT_FOUND"


async def test_list_all_spans_every_project_newest_first() -> None:
    async with _client() as (client, (older, newer, other)):
        resp = await client.get("/api/v1/reports/collection-use/in_situ_visit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalElements"] == 3
    ids = [item["id"] for item in body["content"]]
    # All three projects' reports are present...
    assert set(ids) == {older.id, newer.id, other.id}
    # ...newest first: the two now-stamped reports (p1 + p2) precede the older one.
    assert set(ids[:2]) == {newer.id, other.id}
    assert ids[2] == older.id


async def test_list_all_paginates() -> None:
    async with _client() as (client, (older, _newer, _other)):
        first = await client.get(
            "/api/v1/reports/collection-use/in_situ_visit?page=0&size=2"
        )
        second = await client.get(
            "/api/v1/reports/collection-use/in_situ_visit?page=1&size=2"
        )
    assert first.status_code == second.status_code == 200
    first_body = first.json()
    assert first_body["totalElements"] == 3
    assert first_body["totalPages"] == 2
    assert len(first_body["content"]) == 2
    second_content = second.json()["content"]
    assert len(second_content) == 1
    assert second_content[0]["id"] == older.id


async def test_list_all_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as (client, _seed):
        resp = await client.get("/api/v1/reports/collection-use/in_situ_visit")
    assert resp.status_code == 403


async def test_get_by_id_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as (client, (_older, newer, _other)):
        resp = await client.get(
            f"/api/v1/reports/collection-use/p1/in_situ_visit/{newer.id}"
        )
    assert resp.status_code == 403


async def test_list_all_rows_carry_record_display_fields() -> None:
    """The global list reads each row's record (via the OHS) so the response
    carries the visit's display fields — no DB change to the report row."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    record = InSituVisitRecord.create(
        code="CUP-9",
        visit_begin_date=date(2026, 6, 1),
        visit_end_date=date(2026, 6, 3),
        visitor_name="Maria do Rosário",
        place_name="Museum",
        requested_objects=[],
        in_situ_occurrences=[],
        in_situ_logs=[],
        in_situ_publications=[],
    )
    report = InSituVisitReport.create(
        created_by=PermissionId("perm-staff"),
        project_id="p1",
        narrative_id="nar-1",
        in_situ_visit_record_id=record.id,
    )
    async with session_factory() as session:
        await SqlAlchemyInSituVisitRecordRepository(session).add(record)
        await SqlAlchemyInSituVisitReportRepository(session).add(report)
        await session.commit()

    async def _override_session() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _override_session
    app.dependency_overrides[get_caller_permission] = lambda: _STAFF
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/reports/collection-use/in_situ_visit")
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    assert resp.status_code == 200
    item = resp.json()["content"][0]
    assert item["id"] == report.id
    assert item["inSituVisitRecordId"] == record.id
    assert item["code"] == "CUP-9"
    assert item["visitorName"] == "Maria do Rosário"
    assert item["placeName"] == "Museum"
    assert item["visitBeginDate"] == "2026-06-01"
    assert item["visitEndDate"] == "2026-06-03"
