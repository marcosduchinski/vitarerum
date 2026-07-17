from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    AttachmentData,
    ChildData,
    InSituVisitId,
    InSituVisitRecord,
)
from app.cidoc_crm.in_situ_visit_mapping.infrastructure.repositories import (
    SqlAlchemyInSituVisitRecordRepository,
)
from app.database import Base


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None)


def _record() -> InSituVisitRecord:
    return InSituVisitRecord.create(
        code="CUP-ABCD1234",
        visit_begin_date=date(2026, 6, 1),
        visit_end_date=date(2026, 6, 3),
        visitor_name="Maria do Rosario",
        place_name="Test Museum",
        mapping_version="test-mapping-v1",
        crm_version="7.1.3-test",
        source_project_id="p1",
        project_title="Wolf study",
        project_purpose="Study collection objects in situ",
        planned_begin_date=date(2026, 6, 1),
        planned_end_date=date(2026, 6, 3),
        execution_evidence_type="project_completed_event",
        execution_occurred_at=datetime(2026, 6, 3, 17, 0, tzinfo=UTC),
        execution_recorded_by="perm-staff",
        execution_evidence_gaps=[],
        approved_at=datetime(2026, 5, 31, 12, 0, tzinfo=UTC),
        approved_by="perm-director",
        approval_note="Approved for in-situ handling.",
        requested_objects=[
            ChildData(
                "INV-1",
                "lupus",
                0,
                display_title="Iberian wolf",
                object_name="Canis lupus signatus",
                brief_description_snapshot="Mounted specimen",
            )
        ],
        in_situ_occurrences=[
            ChildData(
                "occ-1",
                "an occurrence",
                0,
                [AttachmentData("att-1", "a photo", "photo.jpg", 0, "IMAGE")],
                related_object_source_id="INV-1",
                number_of_objects=1,
                occurrence_date=datetime(2026, 6, 2, 10, 0, tzinfo=UTC),
                location="Gallery A",
                reported_by="perm-reporter",
                testimonial="Observed during handling.",
                occurrence_log_date_conclusion=datetime(
                    2026, 6, 2, 18, 0, tzinfo=UTC
                ),
                occurrence_log_curator="perm-curator",
            )
        ],
        in_situ_logs=[
            ChildData(
                "log-1",
                "observed",
                0,
                [AttachmentData("log-att", "log photo", "log.jpg", 0, "IMAGE")],
                related_object_source_id="INV-1",
                number_of_objects=1,
                added_at=datetime(2026, 6, 2, 11, 0, tzinfo=UTC),
                added_by="perm-log",
                access_log_date_conclusion=datetime(2026, 6, 2, 19, 0, tzinfo=UTC),
                access_log_curator="perm-access-curator",
            )
        ],
        in_situ_publications=[
            ChildData(
                "pub-1",
                "a paper",
                0,
                [AttachmentData("pub-att", "paper pdf", "paper.pdf", 0, "DOCUMENT")],
                related_object_source_id="INV-1",
                added_at=datetime(2026, 6, 3, 9, 0, tzinfo=UTC),
                added_by="perm-pub",
            )
        ],
    )


async def test_repository_round_trips_enriched_snapshot_fields() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    record = _record()
    async with session_factory() as session:
        repository = SqlAlchemyInSituVisitRecordRepository(session)
        await repository.add(record)
        await session.commit()

    async with session_factory() as session:
        repository = SqlAlchemyInSituVisitRecordRepository(session)
        reloaded = await repository.get_by_id(InSituVisitId(record.id))

    await engine.dispose()

    assert reloaded is not None
    assert reloaded.record_schema_version == 2
    assert reloaded.mapping_version == "test-mapping-v1"
    assert reloaded.crm_version == "7.1.3-test"
    assert reloaded.source_project_id == "p1"
    assert reloaded.project_title == "Wolf study"
    assert reloaded.project_purpose == "Study collection objects in situ"
    assert reloaded.planned_begin_date == date(2026, 6, 1)
    assert reloaded.planned_end_date == date(2026, 6, 3)
    assert reloaded.execution_evidence_type == "project_completed_event"
    assert reloaded.execution_occurred_at == _naive(
        datetime(2026, 6, 3, 17, 0, tzinfo=UTC)
    )
    assert reloaded.execution_recorded_by == "perm-staff"
    assert reloaded.execution_evidence_gaps == []
    assert reloaded.approved_at == _naive(datetime(2026, 5, 31, 12, 0, tzinfo=UTC))
    assert reloaded.approved_by == "perm-director"
    assert reloaded.approval_note == "Approved for in-situ handling."
    assert reloaded.requested_objects[0].display_title == "Iberian wolf"
    assert reloaded.requested_objects[0].object_name == "Canis lupus signatus"
    assert (
        reloaded.requested_objects[0].brief_description_snapshot
        == "Mounted specimen"
    )
    assert reloaded.in_situ_occurrences[0].number_of_objects == 1
    assert reloaded.in_situ_occurrences[0].occurrence_date == _naive(
        datetime(2026, 6, 2, 10, 0, tzinfo=UTC)
    )
    assert reloaded.in_situ_occurrences[0].location == "Gallery A"
    assert reloaded.in_situ_occurrences[0].reported_by == "perm-reporter"
    assert reloaded.in_situ_occurrences[0].testimonial == "Observed during handling."
    assert reloaded.in_situ_occurrences[0].occurrence_log_curator == "perm-curator"
    assert reloaded.in_situ_occurrences[0].attachments[0].media_type == "IMAGE"
    assert reloaded.in_situ_logs[0].number_of_objects == 1
    assert reloaded.in_situ_logs[0].added_by == "perm-log"
    assert reloaded.in_situ_logs[0].access_log_curator == "perm-access-curator"
    assert reloaded.in_situ_logs[0].attachments[0].media_type == "IMAGE"
    assert reloaded.in_situ_publications[0].added_by == "perm-pub"
    assert reloaded.in_situ_publications[0].attachments[0].media_type == "DOCUMENT"
