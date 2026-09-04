"""Domain model for the In Situ Visit CIDOC mapping context.

A generated, read-oriented projection of an in-situ visit ready to be mapped to
CIDOC-CRM. ``InSituVisitRecord`` is the aggregate root; its four child
collections (requested objects, occurrences, logs, publications) and the
attachments hanging off occurrences/logs/publications form one consistency
boundary. Names follow
``docs/diagrams/cidoc-crm-in-situ-visit-record-model.puml`` (so they keep the
``...Record`` suffix); the ORM counterparts in ``infrastructure/models.py``
use an ``Orm`` suffix to avoid the clash.
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
    display_title: str | None = None
    object_name: str | None = None
    brief_description_snapshot: str | None = None


@dataclass(slots=True)
class InSituOccurrenceAttachmentRecord:
    id: InSituOccurrenceAttachmentId
    occurrence_id: InSituOccurrenceId
    source_id: str
    description: str
    reference: str
    position: int
    media_type: str | None = None


@dataclass(slots=True)
class InSituOccurrenceRecord:
    id: InSituOccurrenceId
    visit_record_id: InSituVisitId
    source_id: str
    description: str
    position: int
    attachments: list[InSituOccurrenceAttachmentRecord] = field(default_factory=list)
    related_object_source_id: str | None = None
    number_of_objects: int | None = None
    occurrence_date: datetime | None = None
    location: str | None = None
    reported_by: str | None = None
    testimonial: str | None = None
    occurrence_log_date_conclusion: datetime | None = None
    occurrence_log_curator: str | None = None


@dataclass(slots=True)
class InSituLogAttachmentRecord:
    id: InSituLogAttachmentId
    log_id: InSituLogId
    source_id: str
    description: str
    reference: str
    position: int
    media_type: str | None = None


@dataclass(slots=True)
class InSituLogRecord:
    id: InSituLogId
    visit_record_id: InSituVisitId
    source_id: str
    description: str
    position: int
    attachments: list[InSituLogAttachmentRecord] = field(default_factory=list)
    related_object_source_id: str | None = None
    number_of_objects: int | None = None
    added_at: datetime | None = None
    added_by: str | None = None
    access_log_date_conclusion: datetime | None = None
    access_log_curator: str | None = None


@dataclass(slots=True)
class InSituPublicationAttachmentRecord:
    id: InSituPublicationAttachmentId
    publication_id: InSituPublicationId
    source_id: str
    description: str
    reference: str
    position: int
    media_type: str | None = None


@dataclass(slots=True)
class InSituPublicationRecord:
    id: InSituPublicationId
    visit_record_id: InSituVisitId
    source_id: str
    description: str
    position: int
    attachments: list[InSituPublicationAttachmentRecord] = field(default_factory=list)
    related_object_source_id: str | None = None
    added_at: datetime | None = None
    added_by: str | None = None


# ── Children-as-data, used by the create() factory ─────────────────────────────


@dataclass(frozen=True, slots=True)
class AttachmentData:
    source_id: str
    description: str
    reference: str
    position: int
    media_type: str | None = None


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
    display_title: str | None = None
    object_name: str | None = None
    brief_description_snapshot: str | None = None
    number_of_objects: int | None = None
    occurrence_date: datetime | None = None
    location: str | None = None
    reported_by: str | None = None
    testimonial: str | None = None
    added_at: datetime | None = None
    added_by: str | None = None
    access_log_date_conclusion: datetime | None = None
    access_log_curator: str | None = None
    occurrence_log_date_conclusion: datetime | None = None
    occurrence_log_curator: str | None = None


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
    # The institution that produced this snapshot, captured at export time.
    # Stored rather than read back from configuration so that regenerating the
    # CIDOC graph of an old record still credits whoever produced it, even
    # after the institution is renamed.
    institution_name: str = ""
    record_schema_version: int | None = None
    mapping_version: str | None = None
    crm_version: str | None = None
    source_project_id: str | None = None
    project_title: str | None = None
    project_purpose: str | None = None
    planned_begin_date: date | None = None
    planned_end_date: date | None = None
    execution_evidence_type: str | None = None
    execution_occurred_at: datetime | None = None
    execution_recorded_by: str | None = None
    execution_evidence_gaps: list[str] = field(default_factory=list)
    approved_at: datetime | None = None
    approved_by: str | None = None
    approval_note: str | None = None
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
        institution_name: str = "",
        record_schema_version: int = 2,
        mapping_version: str | None = None,
        crm_version: str | None = None,
        source_project_id: str | None = None,
        project_title: str | None = None,
        project_purpose: str | None = None,
        planned_begin_date: date | None = None,
        planned_end_date: date | None = None,
        execution_evidence_type: str | None = None,
        execution_occurred_at: datetime | None = None,
        execution_recorded_by: str | None = None,
        execution_evidence_gaps: list[str] | None = None,
        approved_at: datetime | None = None,
        approved_by: str | None = None,
        approval_note: str | None = None,
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
            institution_name=institution_name,
            record_schema_version=record_schema_version,
            mapping_version=mapping_version,
            crm_version=crm_version,
            source_project_id=source_project_id,
            project_title=project_title,
            project_purpose=project_purpose,
            planned_begin_date=planned_begin_date,
            planned_end_date=planned_end_date,
            execution_evidence_type=execution_evidence_type,
            execution_occurred_at=execution_occurred_at,
            execution_recorded_by=execution_recorded_by,
            execution_evidence_gaps=execution_evidence_gaps or [],
            approved_at=approved_at,
            approved_by=approved_by,
            approval_note=approval_note,
            requested_objects=[
                RequestedObjectRecord(
                    id=RequestedObjectRecordId(_new_id()),
                    visit_record_id=visit_id,
                    source_id=ro.source_id,
                    description=ro.description,
                    position=ro.position,
                    display_title=ro.display_title,
                    object_name=ro.object_name,
                    brief_description_snapshot=ro.brief_description_snapshot,
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
        number_of_objects=data.number_of_objects,
        occurrence_date=data.occurrence_date,
        location=data.location,
        reported_by=data.reported_by,
        testimonial=data.testimonial,
        occurrence_log_date_conclusion=data.occurrence_log_date_conclusion,
        occurrence_log_curator=data.occurrence_log_curator,
        attachments=[
            InSituOccurrenceAttachmentRecord(
                id=InSituOccurrenceAttachmentId(_new_id()),
                occurrence_id=occurrence_id,
                source_id=att.source_id,
                description=att.description,
                reference=att.reference,
                position=att.position,
                media_type=att.media_type,
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
        number_of_objects=data.number_of_objects,
        added_at=data.added_at,
        added_by=data.added_by,
        access_log_date_conclusion=data.access_log_date_conclusion,
        access_log_curator=data.access_log_curator,
        attachments=[
            InSituLogAttachmentRecord(
                id=InSituLogAttachmentId(_new_id()),
                log_id=log_id,
                source_id=att.source_id,
                description=att.description,
                reference=att.reference,
                position=att.position,
                media_type=att.media_type,
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
        added_at=data.added_at,
        added_by=data.added_by,
        attachments=[
            InSituPublicationAttachmentRecord(
                id=InSituPublicationAttachmentId(_new_id()),
                publication_id=publication_id,
                source_id=att.source_id,
                description=att.description,
                reference=att.reference,
                position=att.position,
                media_type=att.media_type,
            )
            for att in data.attachments
        ],
    )
