from __future__ import annotations

from datetime import date

import pytest

from app.identity.application.read_models import PermissionView, UserView
from app.identity.public import GroupName, PermissionId
from app.scientific_return.domain.enums import WatchIneligibilityReason
from app.scientific_return.infrastructure.acls import (
    UseOfCollectionsProjectSnapshotProvider,
)
from app.use_of_collections.domain.enums import UseStatus, UseType
from app.use_of_collections.public import PublishedObjectView, PublishedProjectView


class _ProjectReader:
    def __init__(self, projects: list[PublishedProjectView]) -> None:
        self.projects = projects
        self.calls: list[tuple[str, ...]] = []

    async def get_projects(
        self, project_ids: tuple[str, ...]
    ) -> list[PublishedProjectView]:
        self.calls.append(project_ids)
        requested = set(project_ids)
        return [project for project in self.projects if project.id in requested]


class _PermissionReader:
    def __init__(self, permissions: list[PermissionView]) -> None:
        self.permissions = permissions
        self.calls: list[tuple[PermissionId, ...]] = []

    async def get_details(
        self, permission_ids: tuple[PermissionId, ...]
    ) -> list[PermissionView]:
        self.calls.append(permission_ids)
        requested = {str(permission_id) for permission_id in permission_ids}
        return [
            permission
            for permission in self.permissions
            if permission.permission_id in requested
        ]


def _project(project_id: str, permission_id: str) -> PublishedProjectView:
    return PublishedProjectView(
        id=project_id,
        reference_number=f"PRJ-{project_id}",
        title="Research",
        purpose="Research",
        intended_use=UseType.OTHER,
        status=UseStatus.COMPLETED,
        begin_date=date(2026, 1, 1),
        end_date=date(2026, 2, 1),
        objects=[
            PublishedObjectView(
                id=f"object-{project_id}",
                inventory_number=f"MUHNAC-{project_id}",
                category="Specimen",
                description="Specimen",
                object_name="Taxon",
            )
        ],
        requested_by_permission_id=permission_id,
    )


@pytest.mark.asyncio
async def test_snapshot_assessment_batches_projects_and_permissions() -> None:
    projects = _ProjectReader(
        [_project("one", "permission-1"), _project("two", "permission-2")]
    )
    permissions = _PermissionReader(
        [
            PermissionView(
                permission_id="permission-1",
                user=UserView("user-1", "Researcher One", "one@example.test"),
                group=GroupName.EXTERNAL,
            )
        ]
    )
    provider = UseOfCollectionsProjectSnapshotProvider(projects, permissions)

    assessments = await provider.assess_completed_projects(("one", "two", "missing"))

    assert projects.calls == [("one", "two", "missing")]
    assert permissions.calls == [
        (PermissionId("permission-1"), PermissionId("permission-2"))
    ]
    assert assessments["one"].payload is not None
    assert (
        assessments["two"].ineligibility_reason
        is WatchIneligibilityReason.REQUESTER_NOT_FOUND
    )
    assert (
        assessments["missing"].ineligibility_reason
        is WatchIneligibilityReason.PROJECT_NOT_COMPLETED
    )
