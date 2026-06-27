from datetime import UTC, date, datetime

import pytest

from app.use_of_collections.domain.enums import (
    ProposalEventType,
    ProposalStatus,
    UseEventType,
    UseStatus,
    UseType,
)
from app.use_of_collections.domain.models import (
    CollectionUseProject,
    CollectionUseProjectId,
    EmailAddress,
    IntendedUse,
    InvalidTransition,
    PermissionId,
    Proposal,
    ProposalId,
    ReferenceNumber,
)


def _now() -> datetime:
    return datetime(2026, 6, 1, tzinfo=UTC)


def _make_project(**kwargs) -> CollectionUseProject:
    defaults = dict(
        id=CollectionUseProjectId("project-1"),
        reference_number=ReferenceNumber("CUP-1234ABCD"),
        title="Collection study",
        purpose="To study the collection",
        intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
        status=UseStatus.IN_PROGRESS,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        requested_by=PermissionId("permission-1"),
    )
    defaults.update(kwargs)
    return CollectionUseProject(**defaults)


def _make_proposal(**kwargs) -> Proposal:
    defaults = dict(
        id=ProposalId("proposal-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id=CollectionUseProjectId("project-1"),
        intended_use=IntendedUse(use_type=UseType.OTHER),
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.PENDING,
        requested_by=PermissionId("permission-1"),
        assigned_to=None,
        submitted_at=_now(),
    )
    defaults.update(kwargs)
    return Proposal(**defaults)


def test_submitted_project_records_requested_event() -> None:
    project = _make_project()

    project.record_requested(
        occurred_at=_now(),
        triggered_by=PermissionId("permission-1"),
    )

    assert project.status == UseStatus.CREATED
    assert project.events[0].type == UseEventType.REQUESTED
    assert project.events[0].triggered_by == "permission-1"


def test_submitted_proposal_records_submitted_event() -> None:
    proposal = _make_proposal()

    proposal.record_submitted(
        occurred_at=_now(),
        triggered_by=PermissionId("permission-1"),
    )

    assert proposal.status == ProposalStatus.SUBMITTED
    assert proposal.events[0].type == ProposalEventType.SUBMITTED
    assert proposal.events[0].triggered_by == "permission-1"


def test_assign_proposal_records_assigned_event() -> None:
    proposal = _make_proposal(status=ProposalStatus.SUBMITTED)

    proposal.assign(
        occurred_at=_now(),
        triggered_by=PermissionId("permission-1"),
        target_permission_id=PermissionId("permission-2"),
    )

    assert proposal.status == ProposalStatus.PENDING
    assert proposal.assigned_to == "permission-2"
    assert proposal.events[-1].type == ProposalEventType.ASSIGNED


def test_cancel_project_blocks_completed_project() -> None:
    project = _make_project(status=UseStatus.COMPLETED)

    with pytest.raises(InvalidTransition, match="completed or cancelled"):
        project.record_cancelled(
            occurred_at=_now(),
            triggered_by=PermissionId("permission-1"),
            reason="No longer needed",
        )


def test_cancel_project_blocks_already_cancelled_project() -> None:
    project = _make_project(status=UseStatus.IN_PROGRESS)
    project.record_cancelled(
        occurred_at=_now(),
        triggered_by=PermissionId("permission-1"),
        reason="No longer needed",
    )
    event_count = len(project.events)

    with pytest.raises(InvalidTransition, match="completed or cancelled"):
        project.record_cancelled(
            occurred_at=_now(),
            triggered_by=PermissionId("permission-1"),
            reason="Duplicate cancellation",
        )

    assert project.status == UseStatus.CANCELLED
    assert len(project.events) == event_count


def test_proposal_cancellation_records_cancelled_status_and_event() -> None:
    proposal = _make_proposal(status=ProposalStatus.APPROVED)

    proposal.cancel(
        occurred_at=_now(),
        triggered_by=PermissionId("permission-1"),
        reason="No longer needed",
    )

    assert proposal.status == ProposalStatus.CANCELLED
    assert proposal.events[-1].type == ProposalEventType.CANCELLED
    assert proposal.events[-1].note == "No longer needed"


def test_rejected_proposal_cannot_be_cancelled() -> None:
    proposal = _make_proposal(status=ProposalStatus.REJECTED)

    with pytest.raises(InvalidTransition, match="Cannot cancel a rejected proposal"):
        proposal.cancel(
            occurred_at=_now(),
            triggered_by=PermissionId("permission-1"),
            reason="No longer needed",
        )

    assert proposal.status == ProposalStatus.REJECTED
    assert proposal.events == []


def test_cancelled_proposal_is_terminal_for_assignment() -> None:
    proposal = _make_proposal(status=ProposalStatus.CANCELLED)

    with pytest.raises(InvalidTransition, match="decided or cancelled"):
        proposal.assign(
            occurred_at=_now(),
            triggered_by=PermissionId("permission-1"),
            target_permission_id=PermissionId("permission-2"),
        )


def test_proposal_driven_project_cancellation_allows_completed_project() -> None:
    project = _make_project(status=UseStatus.COMPLETED)

    project.record_cancelled_from_proposal(
        occurred_at=_now(),
        triggered_by=PermissionId("permission-1"),
        reason="Proposal cancelled",
    )

    assert project.status == UseStatus.CANCELLED
    assert project.events[-1].type == UseEventType.CANCELLED
    assert project.events[-1].note == "Proposal cancelled"


def test_reference_number_validation_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Reference number"):
        ReferenceNumber("CUP-1")


def test_reference_number_validation_rejects_old_uc_prefix() -> None:
    with pytest.raises(ValueError, match="Reference number"):
        ReferenceNumber("UC-1234ABCD")


def test_reference_number_validation_accepts_proposal_format() -> None:
    assert ReferenceNumber("VRP-20260610-0001").value == "VRP-20260610-0001"


def test_email_address_validation_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Invalid email address"):
        EmailAddress("not-an-email")
