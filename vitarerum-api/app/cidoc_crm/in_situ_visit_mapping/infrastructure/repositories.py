"""SQLAlchemy repository for the In Situ Visit CIDOC mapping aggregate.

The whole aggregate is written in one shot (the root cascades to children and
attachments) and read back with the nested relationships eagerly loaded.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    InSituLogAttachmentId,
    InSituLogAttachmentRecord,
    InSituLogId,
    InSituLogRecord,
    InSituOccurrenceAttachmentId,
    InSituOccurrenceAttachmentRecord,
    InSituOccurrenceId,
    InSituOccurrenceRecord,
    InSituPublicationAttachmentId,
    InSituPublicationAttachmentRecord,
    InSituPublicationId,
    InSituPublicationRecord,
    InSituVisitId,
    InSituVisitRecord,
    RequestedObjectRecord,
    RequestedObjectRecordId,
)
from app.cidoc_crm.in_situ_visit_mapping.infrastructure.models import (
    InSituLogAttachmentRecordOrm,
    InSituLogRecordOrm,
    InSituOccurrenceAttachmentRecordOrm,
    InSituOccurrenceRecordOrm,
    InSituPublicationAttachmentRecordOrm,
    InSituPublicationRecordOrm,
    InSituVisitRecordOrm,
    RequestedObjectRecordOrm,
)

_VISIT_EAGER = (
    selectinload(InSituVisitRecordOrm.requested_objects),
    selectinload(InSituVisitRecordOrm.occurrences).selectinload(
        InSituOccurrenceRecordOrm.attachments
    ),
    selectinload(InSituVisitRecordOrm.logs).selectinload(
        InSituLogRecordOrm.attachments
    ),
    selectinload(InSituVisitRecordOrm.publications).selectinload(
        InSituPublicationRecordOrm.attachments
    ),
)


# ── domain → ORM ───────────────────────────────────────────────────────────────


def record_to_orm(record: InSituVisitRecord) -> InSituVisitRecordOrm:
    return InSituVisitRecordOrm(
        id=record.id,
        code=record.code,
        visit_begin_date=record.visit_begin_date,
        visit_end_date=record.visit_end_date,
        visitor_name=record.visitor_name,
        place_name=record.place_name,
        generated_at=record.generated_at,
        requested_objects=[
            RequestedObjectRecordOrm(
                id=ro.id,
                visit_record_id=ro.visit_record_id,
                source_id=ro.source_id,
                description=ro.description,
                position=ro.position,
            )
            for ro in record.requested_objects
        ],
        occurrences=[
            InSituOccurrenceRecordOrm(
                id=occ.id,
                visit_record_id=occ.visit_record_id,
                source_id=occ.source_id,
                description=occ.description,
                position=occ.position,
                related_object_source_id=occ.related_object_source_id,
                attachments=[
                    InSituOccurrenceAttachmentRecordOrm(
                        id=att.id,
                        occurrence_id=att.occurrence_id,
                        source_id=att.source_id,
                        description=att.description,
                        reference=att.reference,
                        position=att.position,
                    )
                    for att in occ.attachments
                ],
            )
            for occ in record.in_situ_occurrences
        ],
        logs=[
            InSituLogRecordOrm(
                id=log.id,
                visit_record_id=log.visit_record_id,
                source_id=log.source_id,
                description=log.description,
                position=log.position,
                related_object_source_id=log.related_object_source_id,
                attachments=[
                    InSituLogAttachmentRecordOrm(
                        id=att.id,
                        log_id=att.log_id,
                        source_id=att.source_id,
                        description=att.description,
                        reference=att.reference,
                        position=att.position,
                    )
                    for att in log.attachments
                ],
            )
            for log in record.in_situ_logs
        ],
        publications=[
            InSituPublicationRecordOrm(
                id=pub.id,
                visit_record_id=pub.visit_record_id,
                source_id=pub.source_id,
                description=pub.description,
                position=pub.position,
                related_object_source_id=pub.related_object_source_id,
                attachments=[
                    InSituPublicationAttachmentRecordOrm(
                        id=att.id,
                        publication_id=att.publication_id,
                        source_id=att.source_id,
                        description=att.description,
                        reference=att.reference,
                        position=att.position,
                    )
                    for att in pub.attachments
                ],
            )
            for pub in record.in_situ_publications
        ],
    )


# ── ORM → domain ───────────────────────────────────────────────────────────────


def record_to_domain(orm: InSituVisitRecordOrm) -> InSituVisitRecord:
    return InSituVisitRecord(
        id=InSituVisitId(orm.id),
        code=orm.code,
        visit_begin_date=orm.visit_begin_date,
        visit_end_date=orm.visit_end_date,
        visitor_name=orm.visitor_name,
        place_name=orm.place_name,
        generated_at=orm.generated_at,
        requested_objects=[
            RequestedObjectRecord(
                id=RequestedObjectRecordId(ro.id),
                visit_record_id=InSituVisitId(ro.visit_record_id),
                source_id=ro.source_id,
                description=ro.description,
                position=ro.position,
            )
            for ro in orm.requested_objects
        ],
        in_situ_occurrences=[
            InSituOccurrenceRecord(
                id=InSituOccurrenceId(occ.id),
                visit_record_id=InSituVisitId(occ.visit_record_id),
                source_id=occ.source_id,
                description=occ.description,
                position=occ.position,
                related_object_source_id=occ.related_object_source_id,
                attachments=[
                    InSituOccurrenceAttachmentRecord(
                        id=InSituOccurrenceAttachmentId(att.id),
                        occurrence_id=InSituOccurrenceId(att.occurrence_id),
                        source_id=att.source_id,
                        description=att.description,
                        reference=att.reference,
                        position=att.position,
                    )
                    for att in occ.attachments
                ],
            )
            for occ in orm.occurrences
        ],
        in_situ_logs=[
            InSituLogRecord(
                id=InSituLogId(log.id),
                visit_record_id=InSituVisitId(log.visit_record_id),
                source_id=log.source_id,
                description=log.description,
                position=log.position,
                related_object_source_id=log.related_object_source_id,
                attachments=[
                    InSituLogAttachmentRecord(
                        id=InSituLogAttachmentId(att.id),
                        log_id=InSituLogId(att.log_id),
                        source_id=att.source_id,
                        description=att.description,
                        reference=att.reference,
                        position=att.position,
                    )
                    for att in log.attachments
                ],
            )
            for log in orm.logs
        ],
        in_situ_publications=[
            InSituPublicationRecord(
                id=InSituPublicationId(pub.id),
                visit_record_id=InSituVisitId(pub.visit_record_id),
                source_id=pub.source_id,
                description=pub.description,
                position=pub.position,
                related_object_source_id=pub.related_object_source_id,
                attachments=[
                    InSituPublicationAttachmentRecord(
                        id=InSituPublicationAttachmentId(att.id),
                        publication_id=InSituPublicationId(att.publication_id),
                        source_id=att.source_id,
                        description=att.description,
                        reference=att.reference,
                        position=att.position,
                    )
                    for att in pub.attachments
                ],
            )
            for pub in orm.publications
        ],
    )


class SqlAlchemyInSituVisitRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: InSituVisitRecord) -> None:
        self._session.add(record_to_orm(record))
        await self._session.flush()

    async def get_by_id(self, record_id: InSituVisitId) -> InSituVisitRecord | None:
        stmt = (
            select(InSituVisitRecordOrm)
            .where(InSituVisitRecordOrm.id == record_id)
            .options(*_VISIT_EAGER)
        )
        result = await self._session.execute(stmt)
        orm = result.scalar_one_or_none()
        return record_to_domain(orm) if orm else None

    async def list(self, page: int, size: int) -> tuple[list[InSituVisitRecord], int]:
        count_stmt = select(func.count()).select_from(InSituVisitRecordOrm)
        total = (await self._session.execute(count_stmt)).scalar_one()
        data_stmt = (
            select(InSituVisitRecordOrm)
            .options(*_VISIT_EAGER)
            .order_by(InSituVisitRecordOrm.generated_at.desc())
            .offset(page * size)
            .limit(size)
        )
        orms = (await self._session.execute(data_stmt)).scalars().all()
        return [record_to_domain(orm) for orm in orms], total
