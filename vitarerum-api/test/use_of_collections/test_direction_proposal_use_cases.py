from datetime import UTC, date, datetime

import pytest

from app.identity.public import Actor, GroupName, PermissionView, UserStatus, UserView
from app.shared.exceptions import InsufficientGroup
from app.use_of_collections.application.use_cases import (
    ReferProposalToDirection,
    ReferProposalToDirectionInput,
    ReturnProposalToStaff,
    ReturnProposalToStaffInput,
)
from app.use_of_collections.domain.enums import (
    ProposalStatus,
    SubmissionChannel,
    UseType,
)
from app.use_of_collections.domain.models import (
    PermissionId,
    Proposal,
    ProposalId,
    ReferenceNumber,
)


def _proposal(assigned_to: str) -> Proposal:
    return Proposal(
        id=ProposalId("proposal-1"),
        reference_number=ReferenceNumber("VRP-20260831-0001"),
        title="Direction review",
        collection_use_project_id=None,
        intended_use=UseType.OTHER,
        begin_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        status=ProposalStatus.PENDING,
        requested_by=PermissionId("requester-1"),
        assigned_to=PermissionId(assigned_to),
        submitted_at=datetime(2026, 8, 31, tzinfo=UTC),
        submission_channel=SubmissionChannel.AUTHENTICATED,
    )


class Repo:
    def __init__(self, proposal: Proposal) -> None:
        self.proposal = proposal
        self.saved = False

    async def get_by_id(self, proposal_id: ProposalId) -> Proposal | None:
        return self.proposal if proposal_id == self.proposal.id else None

    async def save(self, proposal: Proposal) -> None:
        self.proposal = proposal
        self.saved = True


class Permissions:
    def __init__(self, views: dict[str, PermissionView]) -> None:
        self.views = views

    async def get_detail(self, permission_id: PermissionId) -> PermissionView | None:
        return self.views.get(permission_id)


def _view(permission_id: str, group: GroupName) -> PermissionView:
    return PermissionView(
        permission_id=permission_id,
        user=UserView(
            id=f"user-{permission_id}",
            name=permission_id,
            email=f"{permission_id}@example.test",
            status=UserStatus.ACTIVE,
        ),
        group=group,
    )


@pytest.mark.asyncio
async def test_refer_and_return_validate_groups_and_record_targets() -> None:
    direction = _view("direction-1", GroupName.DIRECTION)
    staff = _view("staff-2", GroupName.COLLECTIONS_MANAGEMENT)
    permissions = Permissions({"direction-1": direction, "staff-2": staff})
    repo = Repo(_proposal("staff-1"))

    referred = await ReferProposalToDirection(repo, permissions).execute(
        ReferProposalToDirectionInput(
            proposal_id=ProposalId("proposal-1"),
            caller=Actor(PermissionId("staff-1"), GroupName.CURATORIAL),
            target_permission_id=PermissionId("direction-1"),
            reason="Needs institutional guidance",
        )
    )
    assert referred.assigned_to == "direction-1"
    assert referred.events[-1].target_permission_id == "direction-1"

    returned = await ReturnProposalToStaff(repo, permissions).execute(
        ReturnProposalToStaffInput(
            proposal_id=ProposalId("proposal-1"),
            caller=Actor(PermissionId("direction-1"), GroupName.DIRECTION),
            target_permission_id=PermissionId("staff-2"),
            reason="Proceed with the attached guidance",
        )
    )
    assert returned.assigned_to == "staff-2"
    assert returned.events[-1].note == "Proceed with the attached guidance"


@pytest.mark.asyncio
async def test_direction_cannot_initiate_referral() -> None:
    repo = Repo(_proposal("direction-1"))
    permissions = Permissions(
        {"direction-2": _view("direction-2", GroupName.DIRECTION)}
    )

    with pytest.raises(InsufficientGroup):
        await ReferProposalToDirection(repo, permissions).execute(
            ReferProposalToDirectionInput(
                proposal_id=ProposalId("proposal-1"),
                caller=Actor(PermissionId("direction-1"), GroupName.DIRECTION),
                target_permission_id=PermissionId("direction-2"),
                reason="No",
            )
        )
