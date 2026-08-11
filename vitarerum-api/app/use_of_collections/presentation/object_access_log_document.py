"""Maps journal aggregates onto the RAIS register's read model.

Sits alongside the other ``_build_*`` response mappers in ``common.py``: no
rules, only the translation from project/access-log/entry state (plus the
Identity lookups the form's name and e-mail fields need) into
:class:`ObjectAccessLogDocument`.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.use_of_collections.application.documents import (
    ObjectAccessLogDocument,
    ObjectAccessLogDocumentObject,
)
from app.use_of_collections.domain.models import (
    CollectionUseObject,
    CollectionUseProject,
    ObjectAccessLog,
    ObjectLogEntry,
    RequesterContact,
)
from app.use_of_collections.presentation.permissions import hydrate_permission


def _designation(obj: CollectionUseObject) -> str:
    return obj.display_title or obj.object_name or ""


def _collections_of(objects: list[CollectionUseObject]) -> str:
    """The register has one Collection field; list every collection reached."""
    names: dict[str, None] = {}
    for obj in objects:
        if obj.collection_name:
            names.setdefault(obj.collection_name, None)
    return "; ".join(names)


async def build_object_access_log_document(
    project: CollectionUseProject,
    access_log: ObjectAccessLog,
    entries: list[ObjectLogEntry],
    session: AsyncSession,
    *,
    issued_on: date,
    requester_contact: RequesterContact | None,
) -> ObjectAccessLogDocument:
    objects_by_id = {obj.id: obj for obj in project.objects}
    # An entry whose object was removed from the project has nothing to print.
    logged = [
        (entry, objects_by_id[entry.collection_use_object_id])
        for entry in entries
        if entry.collection_use_object_id in objects_by_id
    ]

    requester = await hydrate_permission(project.requested_by, session)
    # External requesters are provisioned into Identity, but a proposal that has
    # not reached that point still carries the contact the citizen submitted.
    researcher_name = (requester.user.name if requester else "") or (
        requester_contact.name if requester_contact else ""
    )
    researcher_email = (requester.user.email if requester else "") or (
        requester_contact.email.value if requester_contact else ""
    )
    curator = (
        await hydrate_permission(access_log.curator, session)
        if access_log.curator
        else None
    )

    return ObjectAccessLogDocument(
        reference_number=access_log.reference_number.value,
        issued_on=issued_on,
        requester=researcher_name,
        researcher_name=researcher_name,
        researcher_email=researcher_email,
        collection=_collections_of([obj for _, obj in logged]),
        curator=curator.user.name if curator else "",
        conclusion_date=(
            access_log.date_conclusion.date() if access_log.date_conclusion else None
        ),
        objects=tuple(
            ObjectAccessLogDocumentObject(
                inventory_number=obj.inventory_number,
                designation=_designation(obj),
                object_type=obj.category,
                number_of_objects=entry.number_of_objects,
                accessed_at=entry.added_at,
                observations=entry.observations or "",
            )
            for entry, obj in logged
        ),
    )
