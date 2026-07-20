from datetime import UTC, date, datetime

from app.identity.domain.enums import GroupName
from app.identity.domain.models import (
    Group,
    GroupId,
    InstitutionId,
    Permission,
    User,
    UserId,
)
from app.identity.infrastructure.repositories import (
    group_to_domain,
    group_to_record,
    permission_to_domain,
    permission_to_record,
    user_to_domain,
    user_to_record,
)
from app.use_of_collections.domain.enums import (
    MediaType,
    ProposalEventType,
    ProposalStatus,
    SubmissionChannel,
    UseEventType,
    UseStatus,
    UseType,
)
from app.use_of_collections.domain.models import (
    Attachment,
    CollectionUseObject,
    CollectionUseObjectId,
    CollectionUseProject,
    CollectionUseProjectId,
    Conversation,
    ConversationId,
    Document,
    DocumentId,
    DocumentType,
    EmailAddress,
    Message,
    MessageAttachment,
    MessageId,
    ObjectAccessLog,
    ObjectAccessLogId,
    ObjectLogEntry,
    ObjectLogEntryId,
    ObjectOccurrenceEntry,
    ObjectOccurrenceEntryId,
    ObjectOccurrenceLog,
    ObjectOccurrenceLogId,
    PermissionId,
    Proposal,
    ProposalEvent,
    ProposalId,
    PublicationLog,
    PublicationLogEntry,
    PublicationLogEntryId,
    PublicationLogId,
    ReferenceNumber,
    RequestedObject,
    RequestedObjectId,
    RequesterContact,
    UseEvent,
)
from app.use_of_collections.infrastructure.repositories import (
    access_log_to_domain,
    access_log_to_record,
    conversation_to_domain,
    conversation_to_record,
    log_entry_to_domain,
    log_entry_to_record,
    occurrence_entry_to_domain,
    occurrence_entry_to_record,
    occurrence_log_to_domain,
    occurrence_log_to_record,
    project_to_domain,
    project_to_record,
    proposal_to_domain,
    proposal_to_record,
    publication_entry_to_domain,
    publication_entry_to_record,
    publication_log_to_domain,
    publication_log_to_record,
)


def test_collection_use_project_roundtrip_preserves_key_data() -> None:
    now = datetime(2026, 5, 28, 10, 30, tzinfo=UTC)
    project = CollectionUseProject(
        id=CollectionUseProjectId("project-1"),
        reference_number=ReferenceNumber("CUP-1234ABCD"),
        title="Collection study",
        purpose="To study the collection",
        intended_use=UseType.IN_SITU_VISIT,
        status=UseStatus.IN_PROGRESS,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        requested_by=PermissionId("permission-1"),
        proposal_id=ProposalId("proposal-1"),
        authorised_by=PermissionId("permission-9"),
        authorised_at=now,
        events=[
            UseEvent(
                occurred_at=now,
                type=UseEventType.REQUESTED,
                triggered_by=PermissionId("permission-1"),
                note="Submitted",
            )
        ],
        objects=[
            CollectionUseObject(
                id=CollectionUseObjectId("cuo-1"),
                inventory_number="INV-001",
                display_title="Illuminated manuscript",
                category="manuscript",
                description="for study",
                requested_at=now,
                requested_by=PermissionId("permission-1"),
            )
        ],
    )

    rebuilt = project_to_domain(project_to_record(project))

    assert rebuilt.id == project.id
    assert rebuilt.reference_number == project.reference_number
    assert rebuilt.title == "Collection study"
    assert rebuilt.purpose == "To study the collection"
    assert rebuilt.requested_by == "permission-1"
    assert rebuilt.proposal_id == "proposal-1"
    assert rebuilt.authorised_by == "permission-9"
    assert rebuilt.authorised_at == now
    assert rebuilt.events[0].type == UseEventType.REQUESTED
    assert rebuilt.objects[0].id == "cuo-1"
    assert rebuilt.objects[0].inventory_number == "INV-001"
    assert rebuilt.objects[0].display_title == "Illuminated manuscript"


def test_object_log_entry_roundtrip_preserves_reference_and_attachments() -> None:
    now = datetime(2026, 6, 3, 14, 0, tzinfo=UTC)
    entry = ObjectLogEntry(
        id=ObjectLogEntryId("entry-1"),
        object_access_log_id=ObjectAccessLogId("log-1"),
        collection_use_object_id=CollectionUseObjectId("cuo-1"),
        number_of_objects=3,
        added_at=now,
        added_by=PermissionId("permission-1"),
        observations="Inspected the manuscript",
        attachments=[
            Attachment(
                file_reference="files/photo.jpg",
                file_name="photo.jpg",
                media_type=MediaType.IMAGE,
                uploaded_at=now,
                description="Photo of the object",
            )
        ],
    )

    rebuilt = log_entry_to_domain(log_entry_to_record(entry))

    assert rebuilt.id == entry.id
    assert rebuilt.object_access_log_id == "log-1"
    assert rebuilt.collection_use_object_id == "cuo-1"
    assert rebuilt.number_of_objects == 3
    assert rebuilt.observations == "Inspected the manuscript"
    assert rebuilt.attachments[0].media_type == MediaType.IMAGE


def test_object_access_log_roundtrip_preserves_entries_and_conclusion() -> None:
    now = datetime(2026, 6, 3, 14, 0, tzinfo=UTC)
    access_log = ObjectAccessLog(
        id=ObjectAccessLogId("log-1"),
        reference_number=ReferenceNumber("OAL-1234ABCD"),
        collection_use_project_id=CollectionUseProjectId("project-1"),
        date_conclusion=now,
        curator=PermissionId("permission-9"),
        objects=[
            ObjectLogEntry(
                id=ObjectLogEntryId("entry-1"),
                object_access_log_id=ObjectAccessLogId("log-1"),
                collection_use_object_id=CollectionUseObjectId("cuo-1"),
                number_of_objects=1,
                added_at=now,
                added_by=PermissionId("permission-1"),
            )
        ],
    )

    rebuilt = access_log_to_domain(access_log_to_record(access_log))

    assert rebuilt.id == access_log.id
    assert rebuilt.reference_number == access_log.reference_number
    assert rebuilt.collection_use_project_id == "project-1"
    assert rebuilt.date_conclusion == now
    assert rebuilt.curator == "permission-9"
    assert rebuilt.objects[0].collection_use_object_id == "cuo-1"


def test_publication_log_roundtrip_preserves_entries_and_curator() -> None:
    now = datetime(2026, 6, 3, 14, 0, tzinfo=UTC)
    publication_log = PublicationLog(
        id=PublicationLogId("pub-1"),
        reference_number=ReferenceNumber("PUB-1234ABCD"),
        collection_use_project_id=CollectionUseProjectId("project-1"),
        curator=PermissionId("permission-9"),
        entries=[
            PublicationLogEntry(
                id=PublicationLogEntryId("entry-1"),
                publication_log_id=PublicationLogId("pub-1"),
                added_at=now,
                added_by=PermissionId("permission-1"),
                note="Published an article",
                attachments=[
                    Attachment(
                        file_reference="files/paper.pdf",
                        file_name="paper.pdf",
                        media_type=MediaType.DOCUMENT,
                        uploaded_at=now,
                        description="Publication PDF",
                    )
                ],
            )
        ],
    )

    rebuilt = publication_log_to_domain(publication_log_to_record(publication_log))

    assert rebuilt.id == publication_log.id
    assert rebuilt.reference_number == publication_log.reference_number
    assert rebuilt.collection_use_project_id == "project-1"
    assert rebuilt.curator == "permission-9"
    assert rebuilt.entries[0].note == "Published an article"
    assert rebuilt.entries[0].publication_log_id == "pub-1"
    assert rebuilt.entries[0].attachments[0].media_type == MediaType.DOCUMENT


def test_publication_log_entry_roundtrip_preserves_note_and_attachments() -> None:
    now = datetime(2026, 6, 3, 14, 0, tzinfo=UTC)
    entry = PublicationLogEntry(
        id=PublicationLogEntryId("entry-1"),
        publication_log_id=PublicationLogId("pub-1"),
        added_at=now,
        added_by=PermissionId("permission-1"),
        note="Exhibition catalogue",
    )

    rebuilt = publication_entry_to_domain(publication_entry_to_record(entry))

    assert rebuilt.id == entry.id
    assert rebuilt.publication_log_id == "pub-1"
    assert rebuilt.added_by == "permission-1"
    assert rebuilt.note == "Exhibition catalogue"
    assert rebuilt.attachments == []


def test_object_occurrence_entry_roundtrip_preserves_occurrence_data() -> None:
    now = datetime(2026, 6, 3, 14, 0, tzinfo=UTC)
    entry = ObjectOccurrenceEntry(
        id=ObjectOccurrenceEntryId("occ-1"),
        object_occurrence_log_id=ObjectOccurrenceLogId("log-1"),
        collection_use_object_id=CollectionUseObjectId("cuo-1"),
        number_of_objects=2,
        occurrence_date=now,
        location="Conservation lab",
        reported_by=PermissionId("permission-1"),
        detailed_description="Object handled during the session",
        testimonial="Witnessed by the conservator",
    )

    rebuilt = occurrence_entry_to_domain(occurrence_entry_to_record(entry))

    assert rebuilt.id == entry.id
    assert rebuilt.object_occurrence_log_id == "log-1"
    assert rebuilt.collection_use_object_id == "cuo-1"
    assert rebuilt.number_of_objects == 2
    assert rebuilt.occurrence_date == now
    assert rebuilt.location == "Conservation lab"
    assert rebuilt.detailed_description == "Object handled during the session"
    assert rebuilt.testimonial == "Witnessed by the conservator"


def test_object_occurrence_log_roundtrip_preserves_entries_and_conclusion() -> None:
    now = datetime(2026, 6, 3, 14, 0, tzinfo=UTC)
    occurrence_log = ObjectOccurrenceLog(
        id=ObjectOccurrenceLogId("log-1"),
        reference_number=ReferenceNumber("OOL-1234ABCD"),
        collection_use_project_id=CollectionUseProjectId("project-1"),
        date_conclusion=now,
        curator=PermissionId("permission-9"),
        objects=[
            ObjectOccurrenceEntry(
                id=ObjectOccurrenceEntryId("occ-1"),
                object_occurrence_log_id=ObjectOccurrenceLogId("log-1"),
                collection_use_object_id=CollectionUseObjectId("cuo-1"),
                number_of_objects=1,
                occurrence_date=now,
                location="Storage room",
                reported_by=PermissionId("permission-1"),
                detailed_description="Occurrence",
            )
        ],
    )

    rebuilt = occurrence_log_to_domain(occurrence_log_to_record(occurrence_log))

    assert rebuilt.id == occurrence_log.id
    assert rebuilt.reference_number == occurrence_log.reference_number
    assert rebuilt.collection_use_project_id == "project-1"
    assert rebuilt.date_conclusion == now
    assert rebuilt.curator == "permission-9"
    assert rebuilt.objects[0].collection_use_object_id == "cuo-1"


def test_proposal_roundtrip_preserves_key_data() -> None:
    now = datetime(2026, 5, 28, 10, 30, tzinfo=UTC)
    proposal = Proposal(
        id=ProposalId("proposal-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id=CollectionUseProjectId("project-1"),
        intended_use=UseType.OTHER,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.SUBMITTED,
        requested_by=PermissionId("permission-1"),
        assigned_to=PermissionId("permission-2"),
        submitted_at=now,
        submission_channel=SubmissionChannel.AUTHENTICATED,
        events=[
            ProposalEvent(
                occurred_at=now,
                type=ProposalEventType.SUBMITTED,
                triggered_by=PermissionId("permission-1"),
                note="Submitted",
            )
        ],
        requested_objects=[
            RequestedObject(
                id=RequestedObjectId("ro-1"),
                inventory_number="INV-010",
                category="manuscript",
                description="for study",
                requested_at=now,
            )
        ],
        documents=[
            Document(
                id=DocumentId("document-1"),
                type=DocumentType("request-form"),
                file_name="request.pdf",
                file_reference="files/request.pdf",
                submitted_at=now,
                submitted_by=PermissionId("permission-1"),
            )
        ],
    )

    rebuilt = proposal_to_domain(proposal_to_record(proposal))

    assert rebuilt.id == proposal.id
    assert rebuilt.collection_use_project_id == proposal.collection_use_project_id
    assert rebuilt.title == "Proposal title"
    assert rebuilt.intended_use == UseType.OTHER
    assert rebuilt.begin_date == date(2026, 6, 1)
    assert rebuilt.end_date == date(2026, 6, 7)
    assert rebuilt.submitted_at == now
    assert rebuilt.submission_channel == SubmissionChannel.AUTHENTICATED
    assert rebuilt.events[0].type == ProposalEventType.SUBMITTED
    assert rebuilt.requested_objects[0].inventory_number == "INV-010"
    assert rebuilt.requested_objects[0].category == "manuscript"
    assert rebuilt.requested_objects[0].requested_by is None
    assert rebuilt.documents[0].type.value == "request-form"
    assert rebuilt.documents[0].file_name == "request.pdf"


def test_public_contact_proposal_roundtrip_without_requester_or_project() -> None:
    now = datetime(2026, 5, 28, 10, 30, tzinfo=UTC)
    proposal = Proposal(
        id=ProposalId("proposal-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Public proposal",
        collection_use_project_id=None,
        intended_use=UseType.IN_SITU_VISIT,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.SUBMITTED,
        requested_by=None,
        requester_contact=RequesterContact(
            name="Pedro Silva",
            email=EmailAddress("pedro@example.test"),
        ),
        submitted_at=now,
        submission_channel=SubmissionChannel.PUBLIC,
        events=[
            ProposalEvent(
                occurred_at=now,
                type=ProposalEventType.SUBMITTED,
                triggered_by=None,
                note="Submitted publicly",
            )
        ],
    )

    rebuilt = proposal_to_domain(proposal_to_record(proposal))

    assert rebuilt.collection_use_project_id is None
    assert rebuilt.requested_by is None
    assert rebuilt.requester_contact is not None
    assert rebuilt.requester_contact.name == "Pedro Silva"
    assert rebuilt.requester_contact.email.value == "pedro@example.test"
    assert rebuilt.submission_channel == SubmissionChannel.PUBLIC
    assert rebuilt.events[0].triggered_by is None


def test_conversation_roundtrip_preserves_messages_and_attachments() -> None:
    now = datetime(2026, 5, 28, 10, 30, tzinfo=UTC)
    conversation = Conversation(
        id=ConversationId("conversation-1"),
        proposal_id=ProposalId("proposal-1"),
        messages=[
            Message(
                id=MessageId("message-1"),
                sent_at=now,
                sender=EmailAddress("sender@example.org"),
                recipient=EmailAddress("recipient@example.org"),
                subject="Documents",
                body="Please submit documents.",
                attachments=[
                    MessageAttachment(
                        document_id=DocumentId("document-1"),
                        file_name="request.pdf",
                    )
                ],
            )
        ],
    )

    rebuilt = conversation_to_domain(conversation_to_record(conversation))

    assert rebuilt.id == conversation.id
    assert rebuilt.proposal_id == conversation.proposal_id
    assert rebuilt.messages[0].sender.value == "sender@example.org"
    assert rebuilt.messages[0].subject == "Documents"
    assert rebuilt.messages[0].attachments[0].document_id == "document-1"
    assert rebuilt.messages[0].attachments[0].file_name == "request.pdf"


def test_identity_roundtrip_preserves_group_and_permission() -> None:
    user = User(id=UserId("user-1"), name="Test User", email="test@example.org")
    group = Group(
        id=GroupId("group-1"),
        name=GroupName.CURATORIAL,
        institution_id=InstitutionId("institution-1"),
    )
    permission = Permission(
        id=PermissionId("permission-1"),
        user_id=user.id,
        group_id=group.id,
    )

    assert user_to_domain(user_to_record(user)).id == user.id
    assert user_to_domain(user_to_record(user)).email == "test@example.org"
    assert group_to_domain(group_to_record(group)).name == GroupName.CURATORIAL
    assert group_to_domain(group_to_record(group)).institution_id == "institution-1"
    assert permission_to_domain(permission_to_record(permission)).group_id == group.id
