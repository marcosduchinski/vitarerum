"""Maps a project's publication log onto the RRP register read model."""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.use_of_collections.application.documents import (
    PublicationLogDocument,
    PublicationLogDocumentAttachment,
    PublicationLogDocumentEntry,
)
from app.use_of_collections.domain.models import (
    CollectionUseObject,
    CollectionUseProject,
    PermissionId,
    PublicationLog,
    PublicationLogEntry,
    RequesterContact,
)
from app.use_of_collections.presentation.permissions import hydrate_permission


async def _permission_names(
    permission_ids: set[PermissionId], session: AsyncSession
) -> dict[PermissionId, str]:
    names: dict[PermissionId, str] = {}
    for permission_id in permission_ids:
        detail = await hydrate_permission(permission_id, session)
        names[permission_id] = detail.user.name if detail else ""
    return names


def _object_reference(obj: CollectionUseObject | None) -> str:
    if obj is None:
        return "—"
    designation = obj.display_title or obj.object_name or ""
    reference = (
        f"{obj.inventory_number} — {designation}"
        if designation
        else obj.inventory_number
    )
    return (
        f"{reference}\n{obj.collection_name}"
        if obj.collection_name
        else reference
    )


async def build_publication_log_document(
    project: CollectionUseProject,
    publication_log: PublicationLog,
    entries: list[PublicationLogEntry],
    session: AsyncSession,
    *,
    issued_on: date,
    requester_contact: RequesterContact | None,
) -> PublicationLogDocument:
    """Build the RRP projection without adding document concerns to the aggregate."""
    requester = await hydrate_permission(project.requested_by, session)
    requester_name = (requester.user.name if requester else "") or (
        requester_contact.name if requester_contact else ""
    )
    curator = (
        await hydrate_permission(publication_log.curator, session)
        if publication_log.curator
        else None
    )
    ordered_entries = sorted(entries, key=lambda entry: entry.added_at)
    author_names = await _permission_names(
        {entry.added_by for entry in ordered_entries}, session
    )
    objects_by_id = {obj.id: obj for obj in project.objects}

    return PublicationLogDocument(
        reference_number=publication_log.reference_number.value,
        issued_on=issued_on,
        project_reference=project.reference_number.value,
        project_title=project.title,
        requester=requester_name,
        curator=curator.user.name if curator else "",
        entries=tuple(
            PublicationLogDocumentEntry(
                sequence=index,
                added_at=entry.added_at,
                added_by=author_names.get(entry.added_by, ""),
                note=entry.note,
                object_reference=_object_reference(
                    objects_by_id.get(entry.collection_use_object_id)
                    if entry.collection_use_object_id is not None
                    else None
                ),
                attachments=tuple(
                    PublicationLogDocumentAttachment(
                        file_name=attachment.file_name,
                        description=attachment.description,
                    )
                    for attachment in entry.attachments
                ),
            )
            for index, entry in enumerate(ordered_entries, start=1)
        ),
    )
