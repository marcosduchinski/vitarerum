from __future__ import annotations

from app.identity.public import Actor, PermissionId, PermissionReader
from app.scientific_return.application.ports import ConfirmedPublicationWriter
from app.scientific_return.domain.models import (
    CandidatePublication,
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
)
from app.use_of_collections.public import (
    PublishedPublicationEntryWriter,
    PublishedUseOfCollectionsReader,
)


class UseOfCollectionsProjectSnapshotProvider:
    def __init__(
        self,
        project_reader: PublishedUseOfCollectionsReader,
        permission_reader: PermissionReader,
    ) -> None:
        self._project_reader = project_reader
        self._permission_reader = permission_reader

    async def get_completed_project(
        self, project_id: str
    ) -> ProjectSnapshotPayload | None:
        project = await self._project_reader.get_project(project_id)
        if project is None or project.status.value != "COMPLETED":
            return None
        requester = await self._permission_reader.get_detail(
            PermissionId(project.requested_by_permission_id)
        )
        if requester is None:
            return None
        return ProjectSnapshotPayload(
            project_id=project.id,
            project_reference=project.reference_number,
            researcher=requester.user.name,
            consulted_objects=tuple(
                ConsultedObjectSnapshot(
                    id=obj.id,
                    inventory_number=obj.inventory_number,
                    object_name=(obj.object_name or obj.display_title or "").strip(),
                )
                for obj in project.objects
            ),
        )


class UseOfCollectionsPublicationWriter(ConfirmedPublicationWriter):
    def __init__(self, writer: PublishedPublicationEntryWriter) -> None:
        self._writer = writer

    async def add_confirmed_publication(
        self,
        project_id: str,
        caller: Actor,
        candidate: CandidatePublication,
    ) -> str:
        authors = ", ".join(candidate.authors) or "Unknown authors"
        details = [candidate.title, authors]
        if candidate.publication_date:
            details.append(candidate.publication_date)
        if candidate.doi:
            details.append(f"DOI: {candidate.doi}")
        if candidate.url:
            details.append(candidate.url)
        note = ". ".join(part.rstrip(".") for part in details if part).strip() + "."
        return await self._writer.add(project_id=project_id, caller=caller, note=note)
