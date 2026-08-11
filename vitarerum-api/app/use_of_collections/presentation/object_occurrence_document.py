"""Maps a project's occurrence log onto the ROC report's read model.

Sits alongside the other ``_build_*`` response mappers in ``common.py``: no
rules, only the translation from project/occurrence-log/entry state (plus the
Identity lookups the report's "Reportado por" needs) into
:class:`ObjectOccurrenceDocument`.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.use_of_collections.application.documents import (
    ObjectOccurrenceDocument,
    ObjectOccurrenceDocumentEntry,
    ObjectOccurrenceDocumentImage,
)
from app.use_of_collections.domain.models import (
    CollectionUseObject,
    CollectionUseProject,
    ObjectOccurrenceEntry,
    ObjectOccurrenceLog,
    PermissionId,
    RequesterContact,
)
from app.use_of_collections.presentation.permissions import hydrate_permission


async def _reporter_names(
    entries: list[ObjectOccurrenceEntry], session: AsyncSession
) -> dict[PermissionId, str]:
    """Resolve each distinct reporter once, however many entries they filed."""
    names: dict[PermissionId, str] = {}
    for permission_id in {entry.reported_by for entry in entries}:
        reporter = await hydrate_permission(permission_id, session)
        names[permission_id] = reporter.user.name if reporter else ""
    return names


def _designation(obj: CollectionUseObject) -> str:
    return obj.display_title or obj.object_name or ""


async def build_object_occurrence_document(
    project: CollectionUseProject,
    occurrence_log: ObjectOccurrenceLog,
    entries: list[ObjectOccurrenceEntry],
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
    reporters = await _reporter_names(entries, session)
    objects_by_id = {obj.id: obj for obj in project.objects}
    # An entry whose object was removed from the project has nothing to print.
    reportable = [
        (entry, objects_by_id[entry.collection_use_object_id])
        for entry in sorted(entries, key=lambda entry: entry.occurrence_date)
        if entry.collection_use_object_id in objects_by_id
    ]

    return ObjectOccurrenceDocument(
        reference_number=occurrence_log.reference_number.value,
        issued_on=issued_on,
        institution=institution,
        occurrences=tuple(
            ObjectOccurrenceDocumentEntry(
                collection=obj.collection_name or "",
                designation=_designation(obj),
                inventory_number=obj.inventory_number,
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
                reported_by=reporters.get(entry.reported_by, ""),
            )
            for entry, obj in reportable
        ),
    )
