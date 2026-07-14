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
        requestedObjects=[
            RequestedObjectResponse(
                id=ro.id,
                sourceId=ro.source_id,
                description=ro.description,
                position=ro.position,
            )
            for ro in record.requested_objects
        ],
        inSituOccurrences=[
            OccurrenceResponse(
                id=occ.id,
                sourceId=occ.source_id,
                description=occ.description,
                position=occ.position,
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
                attachments=[attachment_to_response(att) for att in pub.attachments],
            )
            for pub in record.in_situ_publications
        ],
    )
