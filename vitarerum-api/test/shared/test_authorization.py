from datetime import UTC, date, datetime

import pytest

from app.identity.public import Actor, GroupName, PermissionId
from app.shared.authorization import (
    is_staff,
    require_group,
    require_staff,
)
from app.shared.exceptions import AccessDenied, InsufficientGroup
from app.use_of_collections.application.authorization import (
    assert_project_access,
    assert_proposal_access,
)
from app.use_of_collections.domain.enums import (
    ProposalStatus,
    SubmissionChannel,
    UseStatus,
    UseType,
)
from app.use_of_collections.domain.models import (
    CollectionUseProject,
    CollectionUseProjectId,
    Proposal,
    ProposalId,
    ReferenceNumber,
)


def _permission(permission_id: str, group_name: GroupName) -> Actor:
    return Actor(id=PermissionId(permission_id), group=group_name)


def _proposal(requested_by: PermissionId) -> Proposal:
    return Proposal(
        id=ProposalId("proposal-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id=CollectionUseProjectId("project-1"),
        intended_use=UseType.IN_SITU_VISIT,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.SUBMITTED,
        requested_by=requested_by,
        submitted_at=datetime.now(UTC),
        submission_channel=SubmissionChannel.AUTHENTICATED,
    )


def _project(requested_by: PermissionId) -> CollectionUseProject:
    return CollectionUseProject(
        id=CollectionUseProjectId("project-1"),
        reference_number=ReferenceNumber("CUP-ABCDEFG1"),
        title="Project title",
        purpose="Use collection",
        intended_use=UseType.IN_SITU_VISIT,
        status=UseStatus.CREATED,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        requested_by=requested_by,
    )


def test_staff_groups_are_recognized() -> None:
    assert is_staff(_permission("curatorial", GroupName.CURATORIAL))
    assert is_staff(_permission("collections", GroupName.COLLECTIONS_MANAGEMENT))
    assert is_staff(_permission("direction", GroupName.DIRECTION))
    assert is_staff(_permission("sys-admin", GroupName.SYS_ADMIN))
    assert not is_staff(_permission("external", GroupName.EXTERNAL))


def test_require_group_rejects_wrong_group() -> None:
    with pytest.raises(InsufficientGroup, match="DIRECTION"):
        require_group(_permission("external", GroupName.EXTERNAL), GroupName.DIRECTION)


def test_require_staff_rejects_external() -> None:
    with pytest.raises(InsufficientGroup):
        require_staff(_permission("external", GroupName.EXTERNAL))


def test_proposal_access_allows_owner_and_staff() -> None:
    owner = _permission("owner", GroupName.EXTERNAL)
    proposal = _proposal(owner.id)

    assert_proposal_access(owner, proposal)
    assert_proposal_access(_permission("staff", GroupName.CURATORIAL), proposal)


def test_proposal_access_rejects_non_owner_external() -> None:
    proposal = _proposal(PermissionId("owner"))

    with pytest.raises(AccessDenied):
        assert_proposal_access(_permission("other", GroupName.EXTERNAL), proposal)


def test_project_access_allows_owner_and_staff() -> None:
    owner = _permission("owner", GroupName.EXTERNAL)
    project = _project(owner.id)
    proposal = _proposal(owner.id)

    assert_project_access(owner, project, proposal)
    assert_project_access(_permission("staff", GroupName.CURATORIAL), project, proposal)


def test_project_access_rejects_missing_or_foreign_proposal_for_external() -> None:
    caller = _permission("other", GroupName.EXTERNAL)
    project = _project(PermissionId("owner"))

    with pytest.raises(AccessDenied):
        assert_project_access(caller, project, None)
    with pytest.raises(AccessDenied):
        assert_project_access(caller, project, _proposal(PermissionId("owner")))


def test_project_access_allows_owner_without_a_proposal() -> None:
    """A follow-up project (see ``CreateFollowUpProject``) has no proposal of
    its own — ``requested_by`` is copied from the origin project directly, so
    access must be granted from ``project.requested_by`` even when no
    ``Proposal`` links back to it."""
    owner = _permission("owner", GroupName.EXTERNAL)
    project = _project(owner.id)

    assert_project_access(owner, project, None)
