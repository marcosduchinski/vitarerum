from __future__ import annotations

from app.identity.public import Actor, PermissionId, PermissionReader
from app.scientific_return.application.ports import (
    ConfirmedPublicationWriter,
    ProjectSnapshotAssessment,
)
from app.scientific_return.domain.enums import WatchIneligibilityReason
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

    async def assess_completed_project(
        self, project_id: str
    ) -> ProjectSnapshotAssessment:
        return (await self.assess_completed_projects((project_id,)))[project_id]

    async def assess_completed_projects(
        self, project_ids: tuple[str, ...]
    ) -> dict[str, ProjectSnapshotAssessment]:
        unique_ids = tuple(dict.fromkeys(project_ids))
        projects = await self._project_reader.get_projects(unique_ids)
        completed = {
            project.id: project
            for project in projects
            if project.status.value == "COMPLETED"
        }
        permission_ids = tuple(
            dict.fromkeys(
                PermissionId(project.requested_by_permission_id)
                for project in completed.values()
            )
        )
        requesters = await self._permission_reader.get_details(permission_ids)
        requesters_by_id = {
            str(requester.permission_id): requester for requester in requesters
        }

        assessments: dict[str, ProjectSnapshotAssessment] = {}
        for project_id in unique_ids:
            project = completed.get(project_id)
            if project is None:
                assessments[project_id] = ProjectSnapshotAssessment(
                    payload=None,
                    ineligibility_reason=(
                        WatchIneligibilityReason.PROJECT_NOT_COMPLETED
                    ),
                )
                continue
            requester = requesters_by_id.get(project.requested_by_permission_id)
            if requester is None:
                assessments[project_id] = ProjectSnapshotAssessment(
                    payload=None,
                    ineligibility_reason=WatchIneligibilityReason.REQUESTER_NOT_FOUND,
                )
                continue
            assessments[project_id] = ProjectSnapshotAssessment(
                payload=ProjectSnapshotPayload(
                    project_id=project.id,
                    project_reference=project.reference_number,
                    researcher=requester.user.name,
                    consulted_objects=tuple(
                        ConsultedObjectSnapshot(
                            id=obj.id,
                            inventory_number=obj.inventory_number,
                            object_name=(
                                obj.object_name or obj.display_title or ""
                            ).strip(),
                        )
                        for obj in project.objects
                    ),
                )
            )
        return assessments


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
