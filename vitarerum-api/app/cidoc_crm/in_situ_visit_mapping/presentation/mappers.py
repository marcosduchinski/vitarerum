"""Domain → response mapping for the In Situ Visit CIDOC mapping context.

Extracted from ``routes.py`` so the same mapping can be reused by the published
language (``app.cidoc_crm.public``) without pulling in the router.
"""

from __future__ import annotations

from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    InSituLogAttachmentRecord,
    InSituOccurrenceAttachmentRecord,
    InSituPublicationAttachmentRecord,
    InSituVisitRecord,
)
from app.cidoc_crm.in_situ_visit_mapping.presentation.schemas import (
    AttachmentResponse,
    InSituVisitRecordResponse,
    LogResponse,
    OccurrenceResponse,
    PublicationResponse,
    RequestedObjectResponse,
)

DomainAttachment = (
    InSituOccurrenceAttachmentRecord
    | InSituLogAttachmentRecord
    | InSituPublicationAttachmentRecord
)


def attachment_to_response(att: DomainAttachment) -> AttachmentResponse:
    return AttachmentResponse(
        id=att.id,
        sourceId=att.source_id,
        description=att.description,
        reference=att.reference,
        position=att.position,
        mediaType=att.media_type,
    )


def record_to_response(record: InSituVisitRecord) -> InSituVisitRecordResponse:
    return InSituVisitRecordResponse(
        id=record.id,
        code=record.code,
        visitBeginDate=record.visit_begin_date,
        visitEndDate=record.visit_end_date,
        visitorName=record.visitor_name,
        placeName=record.place_name,
        generatedAt=record.generated_at,
        recordSchemaVersion=record.record_schema_version,
        sourceProjectId=record.source_project_id,
        sourceProjectTitle=record.project_title,
        sourceProjectPurpose=record.project_purpose,
        plannedBeginDate=record.planned_begin_date,
        plannedEndDate=record.planned_end_date,
        executionEvidenceType=record.execution_evidence_type,
        executionOccurredAt=record.execution_occurred_at,
        executionRecordedBy=record.execution_recorded_by,
        executionEvidenceGaps=record.execution_evidence_gaps,
        mappingVersion=record.mapping_version,
        crmVersion=record.crm_version,
        approvedAt=record.approved_at,
        approvedBy=record.approved_by,
        approvalNote=record.approval_note,
        requestedObjects=[
            RequestedObjectResponse(
                id=ro.id,
                sourceId=ro.source_id,
                description=ro.description,
                position=ro.position,
                displayTitle=ro.display_title,
                objectName=ro.object_name,
                briefDescriptionSnapshot=ro.brief_description_snapshot,
            )
            for ro in record.requested_objects
        ],
        inSituOccurrences=[
            OccurrenceResponse(
                id=occ.id,
                sourceId=occ.source_id,
                description=occ.description,
                position=occ.position,
                relatedObjectSourceId=occ.related_object_source_id,
                numberOfObjects=occ.number_of_objects,
                occurrenceDate=occ.occurrence_date,
                location=occ.location,
                reportedBy=occ.reported_by,
                testimonial=occ.testimonial,
                occurrenceLogDateConclusion=occ.occurrence_log_date_conclusion,
                occurrenceLogCurator=occ.occurrence_log_curator,
                attachments=[attachment_to_response(att) for att in occ.attachments],
            )
            for occ in record.in_situ_occurrences
        ],
        inSituLogs=[
            LogResponse(
                id=log.id,
                sourceId=log.source_id,
                description=log.description,
                position=log.position,
                relatedObjectSourceId=log.related_object_source_id,
                numberOfObjects=log.number_of_objects,
                addedAt=log.added_at,
                addedBy=log.added_by,
                accessLogDateConclusion=log.access_log_date_conclusion,
                accessLogCurator=log.access_log_curator,
                attachments=[attachment_to_response(att) for att in log.attachments],
            )
            for log in record.in_situ_logs
        ],
        inSituPublications=[
            PublicationResponse(
                id=pub.id,
                sourceId=pub.source_id,
                description=pub.description,
                position=pub.position,
                relatedObjectSourceId=pub.related_object_source_id,
                addedAt=pub.added_at,
                addedBy=pub.added_by,
                attachments=[attachment_to_response(att) for att in pub.attachments],
            )
            for pub in record.in_situ_publications
        ],
    )
