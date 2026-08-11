"""Maps an occurrence entry onto the ROC report's read model.

Sits alongside the other ``_build_*`` response mappers in ``common.py``: no
rules, only the translation from project/occurrence-log/entry state (plus the
Identity lookup the report's "Reportado por" needs) into
:class:`ObjectOccurrenceDocument`.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.use_of_collections.application.documents import (
    ObjectOccurrenceDocument,
    ObjectOccurrenceDocumentImage,
)
from app.use_of_collections.domain.models import (
    CollectionUseObject,
    CollectionUseProject,
    ObjectOccurrenceEntry,
    ObjectOccurrenceLog,
    RequesterContact,
)
from app.use_of_collections.presentation.permissions import hydrate_permission


async def build_object_occurrence_document(
    project: CollectionUseProject,
    occurrence_log: ObjectOccurrenceLog,
    entry: ObjectOccurrenceEntry,
    collection_use_object: CollectionUseObject,
    session: AsyncSession,
    *,
    issued_on: date,
    requester_contact: RequesterContact | None,
) -> ObjectOccurrenceDocument:
    requester = await hydrate_permission(project.requested_by, session)
    # External requesters are provisioned into Identity, but a proposal that has
    # not reached that point still carries the contact the citizen submitted.
    institution = (requester.user.name if requester else "") or (
        requester_contact.name if requester_contact else ""
    )
    reporter = await hydrate_permission(entry.reported_by, session)

    return ObjectOccurrenceDocument(
        reference_number=occurrence_log.reference_number.value,
        issued_on=issued_on,
        institution=institution,
        collection=collection_use_object.collection_name or "",
        designation=(
            collection_use_object.display_title
            or collection_use_object.object_name
            or ""
        ),
        inventory_number=collection_use_object.inventory_number,
        number_of_objects=entry.number_of_objects,
        occurred_at=entry.occurrence_date,
        location=entry.location,
        detailed_description=entry.detailed_description,
        testimonial=entry.testimonial or "",
        images=tuple(
            ObjectOccurrenceDocumentImage(
                file_name=attachment.file_name,
                description=attachment.description,
            )
            for attachment in entry.attachments
        ),
        reported_by=reporter.user.name if reporter else "",
    )
