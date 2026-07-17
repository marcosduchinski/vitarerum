"""Anti-corruption adapter over the CIDOC-CRM published language.

The adapter keeps CIDOC-CRM validation as the semantic gate, then translates the
stored in-situ visit record into canonical narrative facts. The LLM never sees
CIDOC IRIs or the JSON-LD graph.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_narrative.domain.facts import (
    AccessFact,
    ApprovalFact,
    AttachmentFact,
    CanonicalVisitFacts,
    EvidenceGap,
    ExecutionFact,
    MissingFact,
    ObjectFact,
    OccurrenceFact,
    PersonFact,
    PublicationFact,
)
from app.ai.museum_narrative.domain.ports import (
    RecordNotFound,
    SemanticValidationFailed,
)
from app.cidoc_crm.public import (
    build_in_situ_visit_cidoc,
    get_in_situ_visit_record_view,
    validate_cidoc,
)


def _datetime_sort(value: datetime | None) -> datetime:
    return value or datetime.max.replace(tzinfo=UTC)


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _object_label(item: Any) -> str:
    return (
        _text(item.displayTitle)
        or _text(item.objectName)
        or _text(item.description)
        or item.sourceId
    )


def _attachments(owner_collection: str, owner: Any) -> list[AttachmentFact]:
    return [
        AttachmentFact(
            source_id=att.sourceId,
            description=_text(att.description),
            reference=att.reference,
            media_type=att.mediaType,
            owner_collection=owner_collection,
            owner_source_id=owner.sourceId,
            position=att.position,
        )
        for att in sorted(
            owner.attachments, key=lambda att: (att.position, att.sourceId)
        )
    ]


def _evidence_gaps(view: Any) -> list[EvidenceGap]:
    messages = list(view.executionEvidenceGaps)
    if view.executionOccurredAt is None:
        messages.append("As datas disponíveis são datas planeadas do projeto.")
    if view.executionEvidenceType and view.executionOccurredAt is None:
        messages.append("Não há data factual de conclusão/devolução dos objetos.")
    if view.approvedAt is None:
        messages.append("Não foi registada aprovação formal no snapshot.")
    for occurrence in view.inSituOccurrences:
        label = occurrence.sourceId
        if occurrence.location is None:
            messages.append(
                f"Não foi registado local específico da ocorrência {label}."
            )
        if occurrence.reportedBy is None:
            messages.append(f"Não foi registado quem reportou a ocorrência {label}.")
    return [EvidenceGap(message=message) for message in dict.fromkeys(messages)]


def _record_view_to_facts(view: Any) -> CanonicalVisitFacts:
    objects = [
        ObjectFact(
            source_id=obj.sourceId,
            label=_object_label(obj),
            description=_text(obj.briefDescriptionSnapshot) or _text(obj.description),
            position=obj.position,
        )
        for obj in sorted(
            view.requestedObjects, key=lambda obj: (obj.position, obj.sourceId)
        )
    ]
    occurrences = [
        OccurrenceFact(
            source_id=occ.sourceId,
            description=_text(occ.description),
            related_object_source_id=occ.relatedObjectSourceId,
            number_of_objects=occ.numberOfObjects,
            occurrence_date=occ.occurrenceDate,
            location=_text(occ.location),
            reported_by=_text(occ.reportedBy),
            testimonial=_text(occ.testimonial),
            conclusion_at=occ.occurrenceLogDateConclusion,
            curator=_text(occ.occurrenceLogCurator),
            position=occ.position,
        )
        for occ in sorted(
            view.inSituOccurrences,
            key=lambda occ: (
                _datetime_sort(occ.occurrenceDate),
                occ.position,
                occ.sourceId,
            ),
        )
    ]
    access_logs = [
        AccessFact(
            source_id=log.sourceId,
            description=_text(log.description),
            related_object_source_id=log.relatedObjectSourceId,
            number_of_objects=log.numberOfObjects,
            added_at=log.addedAt,
            added_by=_text(log.addedBy),
            conclusion_at=log.accessLogDateConclusion,
            curator=_text(log.accessLogCurator),
            position=log.position,
        )
        for log in sorted(
            view.inSituLogs,
            key=lambda log: (_datetime_sort(log.addedAt), log.position, log.sourceId),
        )
    ]
    publications = [
        PublicationFact(
            source_id=pub.sourceId,
            description=_text(pub.description),
            related_object_source_id=pub.relatedObjectSourceId,
            added_at=pub.addedAt,
            added_by=_text(pub.addedBy),
            position=pub.position,
        )
        for pub in sorted(
            view.inSituPublications,
            key=lambda pub: (_datetime_sort(pub.addedAt), pub.position, pub.sourceId),
        )
    ]
    attachments = [
        att
        for collection, entries in (
            ("occurrence", view.inSituOccurrences),
            ("access_log", view.inSituLogs),
            ("publication", view.inSituPublications),
        )
        for entry in entries
        for att in _attachments(collection, entry)
    ]
    approval: ApprovalFact | MissingFact
    if view.approvedAt is None:
        approval = MissingFact(reason="No approval was recorded in this snapshot.")
    else:
        approval = ApprovalFact(
            approved_at=view.approvedAt,
            approved_by=_text(view.approvedBy),
            note=_text(view.approvalNote),
        )
    execution: ExecutionFact | MissingFact
    if view.executionEvidenceType is None:
        execution = MissingFact(reason="No execution evidence was recorded.")
    else:
        execution = ExecutionFact(
            evidence_type=view.executionEvidenceType,
            occurred_at=view.executionOccurredAt,
            recorded_by=_text(view.executionRecordedBy),
        )
    return CanonicalVisitFacts(
        report_subject=f"In-situ visit {view.code}",
        project_reference=view.code,
        project_title=_text(view.sourceProjectTitle),
        project_purpose=_text(view.sourceProjectPurpose),
        planned_begin_date=view.plannedBeginDate or view.visitBeginDate,
        planned_end_date=view.plannedEndDate or view.visitEndDate,
        requester=PersonFact(name=view.visitorName),
        approval=approval,
        execution=execution,
        objects=objects,
        access_logs=access_logs,
        occurrences=occurrences,
        publications=publications,
        attachments=sorted(
            attachments,
            key=lambda att: (att.owner_collection, att.owner_source_id, att.position),
        ),
        evidence_gaps=_evidence_gaps(view),
        source_snapshot_id=view.id,
        source_version=str(view.recordSchemaVersion or 1),
    )


class NarrativeFactsAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def prepare(self, record_id: str) -> CanonicalVisitFacts:
        doc = await build_in_situ_visit_cidoc(self._session, record_id)
        if doc is None:
            raise RecordNotFound(f"No in-situ visit record found with id {record_id}")
        conforms, report = validate_cidoc(doc)
        if not conforms:
            raise SemanticValidationFailed(report)
        view = await get_in_situ_visit_record_view(self._session, record_id)
        if view is None:
            raise RecordNotFound(f"No in-situ visit record found with id {record_id}")
        return _record_view_to_facts(view)
