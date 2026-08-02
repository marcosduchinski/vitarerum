"""Integration tests for the report detail endpoint.

Runs against a real in-memory SQLite database: it seeds an InSituVisitRecord
(with an occurrence + attachment), a narrative for it, and a report linking
them, then asserts the ``/detail`` endpoint embeds both read back through the
two contexts' published languages.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.ai.museum_narrative.domain.models import (
    GeneratedNarrative,
    NarrativeFactSnapshot,
    NarrativeType,
    ResolutionSource,
)
from app.ai.museum_narrative.infrastructure.models import (
    GeneratedNarrativeOrm,
    GeneratedNarrativeRevisionOrm,
    NarrativeFactSnapshotOrm,
)
from app.ai.museum_narrative.infrastructure.repositories import (
    SqlAlchemyNarrativeRepository,
)
from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    AttachmentData,
    ChildData,
    InSituVisitRecord,
)
from app.cidoc_crm.in_situ_visit_mapping.infrastructure.models import (
    InSituVisitRecordOrm,
)
from app.cidoc_crm.in_situ_visit_mapping.infrastructure.repositories import (
    SqlAlchemyInSituVisitRecordRepository,
)
from app.database import Base, get_async_session
from app.external_publications.domain.models import (
    ExternalPublication,
    ExternalPublicationAccessMode,
    ExternalPublicationProfile,
    ExternalPublicationResourceType,
    ExternalPublicationStatus,
)
from app.external_publications.infrastructure.models import ExternalPublicationOrm
from app.external_publications.infrastructure.repositories import (
    SqlAlchemyExternalPublicationRepository,
)
from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.reports.in_situ_visit.domain.models import InSituVisitReport
from app.reports.in_situ_visit.infrastructure.models import InSituVisitReportOrm
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


def _record() -> InSituVisitRecord:
    return InSituVisitRecord.create(
        code="CUP-XYZ",
        visit_begin_date=date(2026, 6, 1),
        visit_end_date=date(2026, 6, 3),
        visitor_name="Maria",
        place_name="Museum",
        requested_objects=[
            ChildData(source_id="INV-1", description="vase", position=0)
        ],
        in_situ_occurrences=[
            ChildData(
                source_id="OCC-1",
                description="crack",
                position=0,
                attachments=[
                    AttachmentData(
                        source_id="ATT-1",
                        description="photo",
                        reference="https://files/img.jpg",
                        position=0,
                    )
                ],
            )
        ],
        in_situ_logs=[],
        in_situ_publications=[],
    )


@asynccontextmanager
async def _client(
    *, caller: Actor = _STAFF
) -> AsyncIterator[tuple[AsyncClient, InSituVisitReport]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    record = _record()
    narrative = GeneratedNarrative.create(
        record_id=record.id,
        narrative="A fine vase.",
        resolved_narrative_type=NarrativeType.INSTITUTIONAL,
        resolution_source=ResolutionSource.DEFAULT,
        target_language="pt",
        creativity_temperature=0.3,
        llm_model="llama3.1:8b",
        facts_snapshot_id=None,
        prompt_version_id="pver-insitu-institutional-v1",
        prompt_version="museum-narrative-institutional-v1",
        model_response_hash="sha256:narrative",
        validation_conforms=True,
    )
    snapshot = NarrativeFactSnapshot.create(
        record_id=record.id,
        payload_json='{"project_reference":"CUP-XYZ","evidence_gaps":[]}',
        payload_hash="sha256:facts",
        builder_version="canonical-visit-facts-v1",
        prompt_version="museum-narrative-institutional-v1",
        cidoc_document_json='{"@graph":[]}',
        cidoc_validation_report="Validation Report\nConforms: True",
        cidoc_conforms=True,
    )
    narrative.facts_snapshot_id = snapshot.id
    revision = narrative.edit_narrative(
        "A fine vase, edited.", edited_by=PermissionId("perm-staff")
    )
    report = InSituVisitReport.create(
        created_by=PermissionId("perm-staff"),
        project_id="p1",
        narrative_id=narrative.id,
        in_situ_visit_record_id=record.id,
    )
    async with session_factory() as session:
        narrative_repo = SqlAlchemyNarrativeRepository(session)
        await SqlAlchemyInSituVisitRecordRepository(session).add(record)
        await narrative_repo.add_facts_snapshot(snapshot)
        await narrative_repo.add(narrative)
        await narrative_repo.add_revision(revision)
        await SqlAlchemyInSituVisitReportRepository(session).add(report)
        await session.commit()

    async def _override_session() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _override_session
    app.dependency_overrides[get_caller_permission] = lambda: caller
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, report
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_detail_embeds_narrative_and_record_with_attachment() -> None:
    async with _client() as (client, report):
        resp = await client.get(
            f"/api/v1/reports/collection-use/p1/in_situ_visit/{report.id}/detail"
        )
    assert resp.status_code == 200
    body = resp.json()
    # Linkage ids.
    assert body["id"] == report.id
    assert body["narrativeId"] == report.narrative_id
    assert body["inSituVisitRecordId"] == report.in_situ_visit_record_id
    # Embedded narrative.
    assert body["narrative"]["data"]["narrative"] == "A fine vase, edited."
    assert body["narrative"]["meta"]["resolved_narrative_type"] == "institutional"
    # Embedded record + nested attachment.
    assert body["record"]["code"] == "CUP-XYZ"
    assert body["record"]["requestedObjects"][0]["sourceId"] == "INV-1"
    attachment = body["record"]["inSituOccurrences"][0]["attachments"][0]
    assert attachment["reference"] == "https://files/img.jpg"


async def test_audit_trail_embeds_six_stage_inputs_without_recomputing_cidoc() -> None:
    async with _client() as (client, report):
        resp = await client.get(
            f"/api/v1/reports/collection-use/p1/in_situ_visit/{report.id}/audit-trail"
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == report.id
    assert body["record"]["code"] == "CUP-XYZ"
    assert body["narrative"]["data"]["narrative"] == "A fine vase, edited."
    assert body["evidence"]["recordId"] == report.in_situ_visit_record_id
    assert body["evidence"]["projectId"] == "p1"
    assert body["cidoc"]["documentJson"] == '{"@graph":[]}'
    assert body["cidoc"]["validationReport"] == "Validation Report\nConforms: True"
    assert body["cidoc"]["conforms"] is True
    assert body["facts"]["payloadJson"] == (
        '{"project_reference":"CUP-XYZ","evidence_gaps":[]}'
    )
    assert body["generation"]["promptVersionId"] == "pver-insitu-institutional-v1"
    assert body["generation"]["promptVersion"] == "museum-narrative-institutional-v1"
    assert body["generation"]["responseHash"] == "sha256:narrative"
    assert body["validation"]["conforms"] is True
    assert body["revisions"]["total_elements"] == 1
    assert body["revisions"]["content"][0]["previous_narrative"] == "A fine vase."
    assert body["revisions"]["content"][0]["revised_narrative"] == (
        "A fine vase, edited."
    )
    assert body["revisions"]["content"][0]["edited_by"] == "perm-staff"


async def test_audit_trail_wrong_project_is_404() -> None:
    async with _client() as (client, report):
        resp = await client.get(
            f"/api/v1/reports/collection-use/p2/in_situ_visit/{report.id}/audit-trail"
        )
    assert resp.status_code == 404
    assert resp.json()["error"] == "REPORT_NOT_FOUND"


async def test_audit_trail_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as (client, report):
        resp = await client.get(
            f"/api/v1/reports/collection-use/p1/in_situ_visit/{report.id}/audit-trail"
        )
    assert resp.status_code == 403


async def test_detail_unknown_report_is_404() -> None:
    async with _client() as (client, _report):
        resp = await client.get(
            "/api/v1/reports/collection-use/p1/in_situ_visit/missing/detail"
        )
    assert resp.status_code == 404
    assert resp.json()["error"] == "REPORT_NOT_FOUND"


async def test_detail_wrong_project_is_404() -> None:
    async with _client() as (client, report):
        resp = await client.get(
            f"/api/v1/reports/collection-use/p2/in_situ_visit/{report.id}/detail"
        )
    assert resp.status_code == 404
    assert resp.json()["error"] == "REPORT_NOT_FOUND"


async def test_detail_forbidden_for_external() -> None:
    async with _client(caller=_EXTERNAL) as (client, report):
        resp = await client.get(
            f"/api/v1/reports/collection-use/p1/in_situ_visit/{report.id}/detail"
        )
    assert resp.status_code == 403


async def test_delete_removes_report_and_generated_narrative_artifacts_only() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    record = _record()
    narrative = GeneratedNarrative.create(
        record_id=record.id,
        narrative="A fine vase.",
        resolved_narrative_type=NarrativeType.INSTITUTIONAL,
        resolution_source=ResolutionSource.DEFAULT,
        target_language="pt",
        creativity_temperature=0.3,
        llm_model="llama3.1:8b",
        facts_snapshot_id=None,
    )
    snapshot = NarrativeFactSnapshot.create(
        record_id=record.id,
        payload_json='{"project_reference":"CUP-XYZ","evidence_gaps":[]}',
        payload_hash="sha256:facts",
        builder_version="canonical-visit-facts-v1",
        prompt_version="museum-narrative-institutional-v1",
    )
    narrative.facts_snapshot_id = snapshot.id
    revision = narrative.edit_narrative(
        "A fine vase, edited.", edited_by=PermissionId("perm-staff")
    )
    report = InSituVisitReport.create(
        created_by=PermissionId("perm-staff"),
        project_id="p1",
        narrative_id=narrative.id,
        in_situ_visit_record_id=record.id,
    )
    publication = ExternalPublication.publish(
        resource_type=ExternalPublicationResourceType.IN_SITU_VISIT_REPORT,
        resource_id=report.id,
        access_mode=ExternalPublicationAccessMode.TOKEN,
        profile=ExternalPublicationProfile.DETAIL,
        created_by=PermissionId("perm-admin"),
        token_hash="token-hash",
    )
    async with session_factory() as session:
        narrative_repo = SqlAlchemyNarrativeRepository(session)
        await SqlAlchemyInSituVisitRecordRepository(session).add(record)
        await narrative_repo.add_facts_snapshot(snapshot)
        await narrative_repo.add(narrative)
        await narrative_repo.add_revision(revision)
        await SqlAlchemyInSituVisitReportRepository(session).add(report)
        await SqlAlchemyExternalPublicationRepository(session).add(publication)
        await session.commit()

    async def _override_session() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _override_session
    app.dependency_overrides[get_caller_permission] = lambda: _STAFF
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.delete(
                f"/api/v1/reports/collection-use/p1/in_situ_visit/{report.id}"
            )
        async with session_factory() as session:
            report_row = await session.get(InSituVisitReportOrm, report.id)
            narrative_row = await session.get(GeneratedNarrativeOrm, narrative.id)
            revision_row = await session.get(GeneratedNarrativeRevisionOrm, revision.id)
            snapshot_row = await session.get(NarrativeFactSnapshotOrm, snapshot.id)
            record_row = await session.get(InSituVisitRecordOrm, record.id)
            publication_row = await session.get(ExternalPublicationOrm, publication.id)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()

    assert resp.status_code == 204
    assert report_row is None
    assert narrative_row is None
    assert revision_row is None
    assert snapshot_row is None
    assert record_row is not None
    assert publication_row is not None
    assert publication_row.status == ExternalPublicationStatus.REVOKED
    assert publication_row.revoked_by == "perm-staff"
    assert publication_row.revoked_at is not None
