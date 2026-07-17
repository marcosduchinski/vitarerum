"""Canonical factual input for narrative generation.

These facts are deliberately independent from CIDOC-CRM JSON-LD. The CIDOC
projection remains the semantic validation gate, but the LLM receives only this
stable, compact fact model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class MissingFact:
    reason: str


@dataclass(frozen=True, slots=True)
class EvidenceGap:
    message: str


@dataclass(frozen=True, slots=True)
class PersonFact:
    name: str


@dataclass(frozen=True, slots=True)
class ApprovalFact:
    approved_at: datetime | None
    approved_by: str | None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionFact:
    evidence_type: str
    occurred_at: datetime | None
    recorded_by: str | None = None


@dataclass(frozen=True, slots=True)
class ObjectFact:
    source_id: str
    label: str
    description: str | None
    position: int


@dataclass(frozen=True, slots=True)
class AccessFact:
    source_id: str
    description: str | None
    related_object_source_id: str | None
    number_of_objects: int | None
    added_at: datetime | None
    added_by: str | None
    conclusion_at: datetime | None
    curator: str | None
    position: int


@dataclass(frozen=True, slots=True)
class OccurrenceFact:
    source_id: str
    description: str | None
    related_object_source_id: str | None
    number_of_objects: int | None
    occurrence_date: datetime | None
    location: str | None
    reported_by: str | None
    testimonial: str | None
    conclusion_at: datetime | None
    curator: str | None
    position: int


@dataclass(frozen=True, slots=True)
class PublicationFact:
    source_id: str
    description: str | None
    related_object_source_id: str | None
    added_at: datetime | None
    added_by: str | None
    position: int


@dataclass(frozen=True, slots=True)
class AttachmentFact:
    source_id: str
    description: str | None
    reference: str
    media_type: str | None
    owner_collection: str
    owner_source_id: str
    position: int


@dataclass(frozen=True, slots=True)
class CanonicalVisitFacts:
    report_subject: str
    project_reference: str
    project_title: str | None
    project_purpose: str | None
    planned_begin_date: date | None
    planned_end_date: date | None
    requester: PersonFact
    approval: ApprovalFact | MissingFact
    execution: ExecutionFact | MissingFact
    objects: list[ObjectFact] = field(default_factory=list)
    access_logs: list[AccessFact] = field(default_factory=list)
    occurrences: list[OccurrenceFact] = field(default_factory=list)
    publications: list[PublicationFact] = field(default_factory=list)
    attachments: list[AttachmentFact] = field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = field(default_factory=list)
    source_snapshot_id: str = ""
    source_version: str = ""
