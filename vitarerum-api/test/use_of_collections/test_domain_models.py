from datetime import UTC, date, datetime

import pytest

from app.use_of_collections.application.context_views import (
    build_visit_execution_evidence,
)
from app.use_of_collections.domain.enums import (
    DocumentCorrectionStatus,
    ProposalEventType,
    ProposalStatus,
    SubmissionChannel,
    UseEventType,
    UseStatus,
    UseType,
)
from app.use_of_collections.domain.models import (
    CollectionUseObject,
    CollectionUseObjectId,
    CollectionUseProject,
    CollectionUseProjectId,
    Document,
    DocumentCorrectionItem,
    DocumentCorrectionItemId,
    DocumentId,
    DocumentType,
    EmailAddress,
    InvalidTransition,
    PermissionId,
    Proposal,
    ProposalId,
    ReferenceNumber,
    RequesterContact,
    UnsatisfiedCorrection,
)


def _now() -> datetime:
    return datetime(2026, 6, 1, tzinfo=UTC)


def _make_project(**kwargs) -> CollectionUseProject:
    defaults = dict(
        id=CollectionUseProjectId("project-1"),
        reference_number=ReferenceNumber("CUP-1234ABCD"),
        title="Collection study",
        purpose="To study the collection",
        intended_use=UseType.IN_SITU_VISIT,
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
        intended_use=UseType.OTHER,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.PENDING,
        requested_by=PermissionId("permission-1"),
        assigned_to=None,
        submitted_at=_now(),
        submission_channel=SubmissionChannel.AUTHENTICATED,
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


def test_visit_execution_evidence_rejects_created_project() -> None:
    project = _make_project(status=UseStatus.CREATED)

    evidence = build_visit_execution_evidence(project)

    assert evidence.occurred is False
    assert evidence.gaps == ["project_status_not_completed", "completed_event_missing"]


def test_visit_execution_evidence_rejects_in_progress_project() -> None:
    project = _make_project(status=UseStatus.IN_PROGRESS)

    evidence = build_visit_execution_evidence(project)

    assert evidence.occurred is False
    assert evidence.gaps == ["project_status_not_completed", "completed_event_missing"]


def test_visit_execution_evidence_accepts_completed_project_with_event() -> None:
    project = _make_project(status=UseStatus.IN_PROGRESS)
    project.record_completed(
        occurred_at=_now(),
        triggered_by=PermissionId("permission-1"),
    )

    evidence = build_visit_execution_evidence(project)

    assert evidence.occurred is True
    assert evidence.evidence_type == "project_completed_event"
    assert evidence.occurred_at == _now()
    assert evidence.recorded_by == "permission-1"
    assert evidence.gaps == []


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


def test_proposal_requires_requested_by_or_requester_contact() -> None:
    with pytest.raises(
        ValueError, match="requested_by or requester_contact"
    ):
        _make_proposal(requested_by=None, requester_contact=None)


def test_resolve_requester_sets_requested_by() -> None:
    proposal = _make_proposal(
        requested_by=None,
        requester_contact=RequesterContact(
            name="Pedro Silva", email=EmailAddress("pedro@example.test")
        ),
        submission_channel=SubmissionChannel.PUBLIC,
    )

    proposal.resolve_requester(PermissionId("permission-external-1"))

    assert proposal.requested_by == "permission-external-1"


def test_resolve_requester_blocks_when_already_resolved() -> None:
    proposal = _make_proposal(requested_by=PermissionId("permission-1"))

    with pytest.raises(InvalidTransition, match="already resolved"):
        proposal.resolve_requester(PermissionId("permission-external-1"))


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


def test_edit_project_updates_metadata_without_lifecycle_event() -> None:
    project = _make_project(status=UseStatus.IN_PROGRESS)

    project.edit(
        title="Corrected title",
        update_title=True,
        purpose="Corrected purpose",
        update_purpose=True,
        begin_date=date(2026, 7, 1),
        update_begin_date=True,
        end_date=date(2026, 7, 5),
        update_end_date=True,
    )

    assert project.title == "Corrected title"
    assert project.purpose == "Corrected purpose"
    assert project.begin_date == date(2026, 7, 1)
    assert project.end_date == date(2026, 7, 5)
    assert project.events == []


def test_edit_project_blocks_terminal_status() -> None:
    project = _make_project(status=UseStatus.COMPLETED)

    with pytest.raises(InvalidTransition, match="completed or cancelled"):
        project.edit(
            title="Corrected title",
            update_title=True,
            purpose=None,
            update_purpose=False,
            begin_date=None,
            update_begin_date=False,
            end_date=None,
            update_end_date=False,
        )


def test_edit_project_rejects_invalid_effective_date_range() -> None:
    project = _make_project(status=UseStatus.CREATED)

    with pytest.raises(ValueError, match="endDate"):
        project.edit(
            title=None,
            update_title=False,
            purpose=None,
            update_purpose=False,
            begin_date=date(2026, 7, 10),
            update_begin_date=True,
            end_date=None,
            update_end_date=False,
        )


def test_add_project_objects_appends_to_editable_project() -> None:
    project = _make_project(status=UseStatus.CREATED)
    project_object = CollectionUseObject(
        id=CollectionUseObjectId("object-1"),
        inventory_number="INV-001",
        category="zoology",
        description="",
        requested_at=_now(),
        requested_by=PermissionId("permission-staff"),
        display_title="Specimen drawer",
        object_name="Drawer",
    )

    project.add_objects([project_object])

    assert project.objects == [project_object]


def test_add_project_objects_blocks_terminal_project() -> None:
    project = _make_project(status=UseStatus.CANCELLED)

    with pytest.raises(InvalidTransition, match="completed or cancelled"):
        project.add_objects([])


def test_remove_project_object_removes_existing_object() -> None:
    project_object = CollectionUseObject(
        id=CollectionUseObjectId("object-1"),
        inventory_number="INV-001",
        category="zoology",
        description="",
        requested_at=_now(),
        requested_by=PermissionId("permission-staff"),
    )
    project = _make_project(status=UseStatus.IN_PROGRESS, objects=[project_object])

    project.remove_object(CollectionUseObjectId("object-1"))

    assert project.objects == []


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


def test_reference_number_validation_rejects_blank_values() -> None:
    with pytest.raises(ValueError, match="Reference number"):
        ReferenceNumber("   ")


def test_reference_number_validation_rejects_overlong_values() -> None:
    with pytest.raises(ValueError, match="Reference number"):
        ReferenceNumber("X" * 129)


def test_reference_number_normalizes_storage_value() -> None:
    assert ReferenceNumber(" MUHNAC/COL/2026/0001 ").value == (
        "MUHNAC/COL/2026/0001"
    )


def test_email_address_validation_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="Invalid email address"):
        EmailAddress("not-an-email")


def test_document_type_accepts_free_text_and_trims() -> None:
    assert DocumentType("  Insurance certificate  ").value == "Insurance certificate"


def test_document_type_rejects_blank() -> None:
    with pytest.raises(ValueError, match="Document type is required"):
        DocumentType("   ")


def test_document_type_rejects_over_128_characters() -> None:
    with pytest.raises(ValueError, match="at most 128 characters"):
        DocumentType("x" * 129)


def test_document_type_accepts_exactly_128_characters() -> None:
    assert DocumentType("x" * 128).value == "x" * 128


# ── Document corrections ──────────────────────────────────────────────────────


def _make_document(doc_id: str = "doc-1", doc_type: str = "ID_CARD") -> Document:
    return Document(
        id=DocumentId(doc_id),
        type=DocumentType(doc_type),
        file_name=f"{doc_id}.pdf",
        file_reference=f"proposals/prop/{doc_id}.pdf",
        submitted_at=_now(),
        submitted_by=None,
    )


def _make_correction_item(
    item_id: str = "ci-1",
    doc_type: str = "ID_CARD",
    document_id: str | None = "doc-1",
) -> DocumentCorrectionItem:
    return DocumentCorrectionItem(
        id=DocumentCorrectionItemId(item_id),
        document_type=DocumentType(doc_type),
        reason="Illegible scan",
        requested_at=_now(),
        requested_by=PermissionId("staff-1"),
        document_id=DocumentId(document_id) if document_id is not None else None,
    )


def test_request_document_corrections_records_items_and_event() -> None:
    proposal = _make_proposal(status=ProposalStatus.PENDING)
    proposal.documents = [_make_document()]
    proposal.request_document_corrections(
        occurred_at=_now(),
        triggered_by=PermissionId("staff-1"),
        items=[_make_correction_item()],
        note="Please resend",
    )
    assert len(proposal.correction_items) == 1
    assert proposal.events[-1].type == ProposalEventType.DOCUMENT_CORRECTIONS_REQUESTED
    assert proposal.status == ProposalStatus.PENDING  # stays open


def test_request_document_corrections_requires_pending() -> None:
    proposal = _make_proposal(status=ProposalStatus.APPROVED)
    with pytest.raises(InvalidTransition):
        proposal.request_document_corrections(
            occurred_at=_now(),
            triggered_by=PermissionId("staff-1"),
            items=[_make_correction_item()],
        )


def test_request_document_corrections_unknown_document_id_raises() -> None:
    proposal = _make_proposal(status=ProposalStatus.PENDING)
    proposal.documents = []
    with pytest.raises(ValueError, match="not found"):
        proposal.request_document_corrections(
            occurred_at=_now(),
            triggered_by=PermissionId("staff-1"),
            items=[_make_correction_item(document_id="ghost")],
        )


def test_request_document_corrections_missing_document_needs_no_document_id() -> None:
    proposal = _make_proposal(status=ProposalStatus.PENDING)
    proposal.documents = []
    proposal.request_document_corrections(
        occurred_at=_now(),
        triggered_by=PermissionId("staff-1"),
        items=[_make_correction_item(document_id=None)],
    )
    assert proposal.correction_items[0].document_id is None


def test_remove_document_within_scope_returns_and_detaches() -> None:
    proposal = _make_proposal(status=ProposalStatus.PENDING)
    document = _make_document()
    proposal.documents = [document]
    removed = proposal.remove_document(
        DocumentId("doc-1"), allowed_ids={DocumentId("doc-1")}
    )
    assert removed is document
    assert proposal.documents == []


def test_remove_document_out_of_scope_raises() -> None:
    proposal = _make_proposal(status=ProposalStatus.PENDING)
    proposal.documents = [_make_document()]
    with pytest.raises(InvalidTransition, match="scope"):
        proposal.remove_document(DocumentId("doc-1"), allowed_ids=set())
    assert len(proposal.documents) == 1  # untouched


def test_remove_document_requires_pending() -> None:
    proposal = _make_proposal(status=ProposalStatus.APPROVED)
    proposal.documents = [_make_document()]
    with pytest.raises(InvalidTransition):
        proposal.remove_document(DocumentId("doc-1"), allowed_ids={DocumentId("doc-1")})


def test_submit_document_corrections_resolves_satisfied_missing_item() -> None:
    # Missing-document item (document_id=None) satisfied by a present doc of type.
    proposal = _make_proposal(status=ProposalStatus.PENDING)
    proposal.documents = [_make_document(doc_id="doc-cv", doc_type="CV")]
    item = _make_correction_item(doc_type="CV", document_id=None)
    proposal.correction_items = [item]
    proposal.submit_document_corrections(
        occurred_at=_now(), triggered_by=None, item_ids=[item.id]
    )
    assert proposal.correction_items[0].status == DocumentCorrectionStatus.RESOLVED
    assert proposal.correction_items[0].resolved_at == _now()
    assert proposal.events[-1].type == ProposalEventType.DOCUMENT_CORRECTIONS_SUBMITTED


def test_submit_document_corrections_rejects_unsatisfied_item() -> None:
    # No document of the requested type present → cannot finalise.
    proposal = _make_proposal(status=ProposalStatus.PENDING)
    proposal.documents = []
    item = _make_correction_item(doc_type="CV", document_id=None)
    proposal.correction_items = [item]
    with pytest.raises(UnsatisfiedCorrection, match="CV"):
        proposal.submit_document_corrections(
            occurred_at=_now(), triggered_by=None, item_ids=[item.id]
        )
    # Nothing resolved, no event recorded.
    assert proposal.correction_items[0].status == DocumentCorrectionStatus.REQUESTED
    assert not proposal.events


def test_submit_document_corrections_replacement_needs_fresh_document() -> None:
    # A replacement item is satisfied only by a *different* doc of the same type.
    proposal = _make_proposal(status=ProposalStatus.PENDING)
    old = _make_document(doc_id="doc-1", doc_type="ID_CARD")
    proposal.documents = [old]
    item = _make_correction_item(doc_type="ID_CARD", document_id="doc-1")
    proposal.correction_items = [item]
    with pytest.raises(UnsatisfiedCorrection):
        proposal.submit_document_corrections(occurred_at=_now(), triggered_by=None)

    proposal.documents.append(_make_document(doc_id="doc-2", doc_type="ID_CARD"))
    proposal.submit_document_corrections(occurred_at=_now(), triggered_by=None)
    assert proposal.correction_items[0].status == DocumentCorrectionStatus.RESOLVED
