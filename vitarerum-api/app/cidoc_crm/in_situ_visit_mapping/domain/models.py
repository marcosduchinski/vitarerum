"""Domain model for the In Situ Visit CIDOC mapping context.

A generated, read-oriented projection of an in-situ visit ready to be mapped to
CIDOC-CRM. ``InSituVisitRecord`` is the aggregate root; its four child
collections (requested objects, occurrences, logs, publications) and the
attachments hanging off occurrences/logs/publications form one consistency
boundary. Names follow ``docs/cidoc-crm.puml`` (so they keep the ``...Record``
suffix); the ORM counterparts in ``infrastructure/models.py`` use an ``Orm``
suffix to avoid the clash.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import NewType

InSituVisitId = NewType("InSituVisitId", str)
RequestedObjectRecordId = NewType("RequestedObjectRecordId", str)
InSituOccurrenceId = NewType("InSituOccurrenceId", str)
InSituOccurrenceAttachmentId = NewType("InSituOccurrenceAttachmentId", str)
InSituLogId = NewType("InSituLogId", str)
InSituLogAttachmentId = NewType("InSituLogAttachmentId", str)
InSituPublicationId = NewType("InSituPublicationId", str)
InSituPublicationAttachmentId = NewType("InSituPublicationAttachmentId", str)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class RequestedObjectRecord:
    id: RequestedObjectRecordId
    visit_record_id: InSituVisitId
    source_id: str
    description: str
    position: int


@dataclass(slots=True)
class InSituOccurrenceAttachmentRecord:
    id: InSituOccurrenceAttachmentId
    occurrence_id: InSituOccurrenceId
    source_id: str
    description: str
    reference: str
    position: int


@dataclass(slots=True)
class InSituOccurrenceRecord:
    id: InSituOccurrenceId
    visit_record_id: InSituVisitId
    source_id: str
    description: str
    position: int
    attachments: list[InSituOccurrenceAttachmentRecord] = field(default_factory=list)
    related_object_source_id: str | None = None


@dataclass(slots=True)
class InSituLogAttachmentRecord:
    id: InSituLogAttachmentId
    log_id: InSituLogId
    source_id: str
    description: str
    reference: str
    position: int


@dataclass(slots=True)
class InSituLogRecord:
    id: InSituLogId
    visit_record_id: InSituVisitId
    source_id: str
    description: str
    position: int
    attachments: list[InSituLogAttachmentRecord] = field(default_factory=list)
    related_object_source_id: str | None = None


@dataclass(slots=True)
class InSituPublicationAttachmentRecord:
    id: InSituPublicationAttachmentId
    publication_id: InSituPublicationId
    source_id: str
    description: str
    reference: str
    position: int


@dataclass(slots=True)
class InSituPublicationRecord:
    id: InSituPublicationId
    visit_record_id: InSituVisitId
    source_id: str
    description: str
    position: int
    attachments: list[InSituPublicationAttachmentRecord] = field(default_factory=list)
    related_object_source_id: str | None = None


# ── Children-as-data, used by the create() factory ─────────────────────────────


@dataclass(frozen=True, slots=True)
class AttachmentData:
    source_id: str
    description: str
    reference: str
    position: int


@dataclass(frozen=True, slots=True)
class ChildData:
    """A requested object, occurrence, log, or publication before id assignment.
    ``attachments`` is ignored for requested objects (they carry none).
    ``related_object_source_id`` is only used by occurrences and logs, to link
    the entry back to the specific requested object it concerns."""

    source_id: str
    description: str
    position: int
    attachments: list[AttachmentData] = field(default_factory=list)
    related_object_source_id: str | None = None


@dataclass(slots=True)
class InSituVisitRecord:
    """Aggregate root — a generated snapshot of an in-situ visit for CIDOC-CRM
    mapping."""

    id: InSituVisitId
    code: str
    visit_begin_date: date
    visit_end_date: date
    visitor_name: str
    place_name: str
    generated_at: datetime
    requested_objects: list[RequestedObjectRecord] = field(default_factory=list)
    in_situ_occurrences: list[InSituOccurrenceRecord] = field(default_factory=list)
    in_situ_logs: list[InSituLogRecord] = field(default_factory=list)
    in_situ_publications: list[InSituPublicationRecord] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        code: str,
        visit_begin_date: date,
        visit_end_date: date,
        visitor_name: str,
        place_name: str,
        requested_objects: list[ChildData] | None = None,
        in_situ_occurrences: list[ChildData] | None = None,
        in_situ_logs: list[ChildData] | None = None,
        in_situ_publications: list[ChildData] | None = None,
    ) -> InSituVisitRecord:
        """Build a fresh aggregate, assigning ids and stamping ``generated_at``."""
        visit_id = InSituVisitId(_new_id())
        return cls(
            id=visit_id,
            code=code,
            visit_begin_date=visit_begin_date,
            visit_end_date=visit_end_date,
            visitor_name=visitor_name,
            place_name=place_name,
            generated_at=_now(),
            requested_objects=[
                RequestedObjectRecord(
                    id=RequestedObjectRecordId(_new_id()),
                    visit_record_id=visit_id,
                    source_id=ro.source_id,
                    description=ro.description,
                    position=ro.position,
                )
                for ro in (requested_objects or [])
            ],
            in_situ_occurrences=[
                _build_occurrence(visit_id, occ) for occ in (in_situ_occurrences or [])
            ],
            in_situ_logs=[_build_log(visit_id, log) for log in (in_situ_logs or [])],
            in_situ_publications=[
                _build_publication(visit_id, pub)
                for pub in (in_situ_publications or [])
            ],
        )


def _build_occurrence(
    visit_id: InSituVisitId, data: ChildData
) -> InSituOccurrenceRecord:
    occurrence_id = InSituOccurrenceId(_new_id())
    return InSituOccurrenceRecord(
        id=occurrence_id,
        visit_record_id=visit_id,
        source_id=data.source_id,
        description=data.description,
        position=data.position,
        related_object_source_id=data.related_object_source_id,
        attachments=[
            InSituOccurrenceAttachmentRecord(
                id=InSituOccurrenceAttachmentId(_new_id()),
                occurrence_id=occurrence_id,
                source_id=att.source_id,
                description=att.description,
                reference=att.reference,
                position=att.position,
            )
            for att in data.attachments
        ],
    )


def _build_log(visit_id: InSituVisitId, data: ChildData) -> InSituLogRecord:
    log_id = InSituLogId(_new_id())
    return InSituLogRecord(
        id=log_id,
        visit_record_id=visit_id,
        source_id=data.source_id,
        description=data.description,
        position=data.position,
        related_object_source_id=data.related_object_source_id,
        attachments=[
            InSituLogAttachmentRecord(
                id=InSituLogAttachmentId(_new_id()),
                log_id=log_id,
                source_id=att.source_id,
                description=att.description,
                reference=att.reference,
                position=att.position,
            )
            for att in data.attachments
        ],
    )


def _build_publication(
    visit_id: InSituVisitId, data: ChildData
) -> InSituPublicationRecord:
    publication_id = InSituPublicationId(_new_id())
    return InSituPublicationRecord(
        id=publication_id,
        visit_record_id=visit_id,
        source_id=data.source_id,
        description=data.description,
        position=data.position,
        related_object_source_id=data.related_object_source_id,
        attachments=[
            InSituPublicationAttachmentRecord(
                id=InSituPublicationAttachmentId(_new_id()),
                publication_id=publication_id,
                source_id=att.source_id,
                description=att.description,
                reference=att.reference,
                position=att.position,
            )
            for att in data.attachments
        ],
    )
