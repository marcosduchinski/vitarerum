from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.use_of_collections.application.context_views import (
    ExportAttachmentView,
    ExportEntryView,
    ExportObjectView,
    ProjectExportView,
)
from app.use_of_collections.application.ports import ProjectFilters, ProposalFilters
from app.use_of_collections.domain.enums import DocumentCorrectionStatus
from app.use_of_collections.domain.models import (
    Attachment,
    CollectionUseObject,
    CollectionUseObjectId,
    CollectionUseProject,
    CollectionUseProjectId,
    Conversation,
    ConversationId,
    Document,
    DocumentCorrectionItem,
    DocumentCorrectionItemId,
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
    RequestedDocument,
    RequestedDocumentId,
    RequestedObject,
    RequestedObjectId,
    RequesterContact,
    UseEvent,
)
from app.use_of_collections.infrastructure.models import (
    CollectionUseObjectRecord,
    CollectionUseProjectRecord,
    ConversationRecord,
    DocumentCorrectionItemRecord,
    DocumentRecord,
    LogEntryAttachmentRecord,
    MessageAttachmentRecord,
    MessageRecord,
    ObjectAccessLogRecord,
    ObjectLogEntryRecord,
    ObjectOccurrenceEntryRecord,
    ObjectOccurrenceLogRecord,
    OccurrenceEntryAttachmentRecord,
    ProposalEventRecord,
    ProposalRecord,
    PublicationEntryAttachmentRecord,
    PublicationLogEntryRecord,
    PublicationLogRecord,
    RequestedDocumentRecord,
    RequestedObjectRecord,
    UseEventRecord,
)

# ── mapper helpers ────────────────────────────────────────────────────────────


def project_to_record(project: CollectionUseProject) -> CollectionUseProjectRecord:
    return CollectionUseProjectRecord(
        id=project.id,
        reference_number=project.reference_number.value,
        title=project.title,
        purpose=project.purpose,
        note=project.note,
        request_note=project.request_note,
        proposal_id=project.proposal_id,
        type=project.intended_use,
        status=project.status,
        result=project.result,
        authorised_by=project.authorised_by,
        authorised_at=project.authorised_at,
        begin_date=project.begin_date,
        end_date=project.end_date,
        requested_by=project.requested_by,
        events=[
            UseEventRecord(
                occurred_at=event.occurred_at,
                type=event.type,
                triggered_by=event.triggered_by,
                note=event.note,
            )
            for event in project.events
        ],
        objects=[
            CollectionUseObjectRecord(
                id=obj.id,
                inventory_number=obj.inventory_number,
                display_title=obj.display_title,
                object_name=obj.object_name,
                brief_description_snapshot=obj.brief_description_snapshot,
                category=obj.category,
                description=obj.description,
                requested_at=obj.requested_at,
                requested_by=obj.requested_by,
            )
            for obj in project.objects
        ],
    )


def project_to_domain(record: CollectionUseProjectRecord) -> CollectionUseProject:
    return CollectionUseProject(
        id=CollectionUseProjectId(record.id),
        reference_number=ReferenceNumber(record.reference_number),
        title=record.title,
        purpose=record.purpose,
        note=record.note,
        request_note=record.request_note,
        proposal_id=ProposalId(record.proposal_id) if record.proposal_id else None,
        intended_use=record.type,
        status=record.status,
        result=record.result,
        authorised_by=PermissionId(record.authorised_by)
        if record.authorised_by
        else None,
        authorised_at=record.authorised_at,
        begin_date=record.begin_date,
        end_date=record.end_date,
        requested_by=PermissionId(record.requested_by),
        events=[
            UseEvent(
                occurred_at=event.occurred_at,
                type=event.type,
                triggered_by=PermissionId(event.triggered_by),
                note=event.note,
            )
            for event in record.events
        ],
        objects=[
            CollectionUseObject(
                id=CollectionUseObjectId(obj.id),
                inventory_number=obj.inventory_number,
                display_title=obj.display_title,
                object_name=obj.object_name,
                brief_description_snapshot=obj.brief_description_snapshot,
                category=obj.category,
                description=obj.description,
                requested_at=obj.requested_at,
                requested_by=PermissionId(obj.requested_by),
            )
            for obj in record.objects
        ],
    )


def _attachment_to_domain(record: object) -> Attachment:
    a: LogEntryAttachmentRecord = record  # type: ignore[assignment]
    return Attachment(
        file_reference=a.file_reference,
        file_name=a.file_name,
        media_type=a.media_type,
        uploaded_at=a.uploaded_at,
        note=a.note,
    )


def log_entry_to_record(entry: ObjectLogEntry) -> ObjectLogEntryRecord:
    return ObjectLogEntryRecord(
        id=entry.id,
        access_log_id=entry.object_access_log_id,
        number_of_objects=entry.number_of_objects,
        added_at=entry.added_at,
        added_by=entry.added_by,
        observations=entry.observations,
        collection_use_object_id=entry.collection_use_object_id,
        attachments=[
            LogEntryAttachmentRecord(
                file_reference=a.file_reference,
                file_name=a.file_name,
                media_type=a.media_type,
                uploaded_at=a.uploaded_at,
                note=a.note,
            )
            for a in entry.attachments
        ],
    )


def log_entry_to_domain(record: ObjectLogEntryRecord) -> ObjectLogEntry:
    return ObjectLogEntry(
        id=ObjectLogEntryId(record.id),
        object_access_log_id=ObjectAccessLogId(record.access_log_id),
        collection_use_object_id=CollectionUseObjectId(record.collection_use_object_id),
        number_of_objects=record.number_of_objects,
        added_at=record.added_at,
        added_by=PermissionId(record.added_by),
        observations=record.observations,
        attachments=[_attachment_to_domain(a) for a in record.attachments],
    )


def access_log_to_record(access_log: ObjectAccessLog) -> ObjectAccessLogRecord:
    return ObjectAccessLogRecord(
        id=access_log.id,
        reference_number=access_log.reference_number.value,
        project_id=access_log.collection_use_project_id,
        date_conclusion=access_log.date_conclusion,
        curator=access_log.curator,
        objects=[log_entry_to_record(e) for e in access_log.objects],
    )


def access_log_to_domain(record: ObjectAccessLogRecord) -> ObjectAccessLog:
    return ObjectAccessLog(
        id=ObjectAccessLogId(record.id),
        reference_number=ReferenceNumber(record.reference_number),
        collection_use_project_id=CollectionUseProjectId(record.project_id),
        date_conclusion=record.date_conclusion,
        curator=PermissionId(record.curator) if record.curator else None,
        objects=[log_entry_to_domain(e) for e in record.objects],
    )


def occurrence_entry_to_record(
    entry: ObjectOccurrenceEntry,
) -> ObjectOccurrenceEntryRecord:
    return ObjectOccurrenceEntryRecord(
        id=entry.id,
        occurrence_log_id=entry.object_occurrence_log_id,
        number_of_objects=entry.number_of_objects,
        occurrence_date=entry.occurrence_date,
        location=entry.location,
        reported_by=entry.reported_by,
        detailed_description=entry.detailed_description,
        testimonial=entry.testimonial,
        collection_use_object_id=entry.collection_use_object_id,
        attachments=[
            OccurrenceEntryAttachmentRecord(
                file_reference=a.file_reference,
                file_name=a.file_name,
                media_type=a.media_type,
                uploaded_at=a.uploaded_at,
                note=a.note,
            )
            for a in entry.attachments
        ],
    )


def occurrence_entry_to_domain(
    record: ObjectOccurrenceEntryRecord,
) -> ObjectOccurrenceEntry:
    return ObjectOccurrenceEntry(
        id=ObjectOccurrenceEntryId(record.id),
        object_occurrence_log_id=ObjectOccurrenceLogId(record.occurrence_log_id),
        collection_use_object_id=CollectionUseObjectId(record.collection_use_object_id),
        number_of_objects=record.number_of_objects,
        occurrence_date=record.occurrence_date,
        location=record.location,
        reported_by=PermissionId(record.reported_by),
        detailed_description=record.detailed_description,
        testimonial=record.testimonial,
        attachments=[_attachment_to_domain(a) for a in record.attachments],
    )


def occurrence_log_to_record(
    occurrence_log: ObjectOccurrenceLog,
) -> ObjectOccurrenceLogRecord:
    return ObjectOccurrenceLogRecord(
        id=occurrence_log.id,
        reference_number=occurrence_log.reference_number.value,
        project_id=occurrence_log.collection_use_project_id,
        date_conclusion=occurrence_log.date_conclusion,
        curator=occurrence_log.curator,
        objects=[occurrence_entry_to_record(e) for e in occurrence_log.objects],
    )


def occurrence_log_to_domain(
    record: ObjectOccurrenceLogRecord,
) -> ObjectOccurrenceLog:
    return ObjectOccurrenceLog(
        id=ObjectOccurrenceLogId(record.id),
        reference_number=ReferenceNumber(record.reference_number),
        collection_use_project_id=CollectionUseProjectId(record.project_id),
        date_conclusion=record.date_conclusion,
        curator=PermissionId(record.curator) if record.curator else None,
        objects=[occurrence_entry_to_domain(e) for e in record.objects],
    )


def publication_entry_to_record(
    entry: PublicationLogEntry,
) -> PublicationLogEntryRecord:
    return PublicationLogEntryRecord(
        id=entry.id,
        publication_log_id=entry.publication_log_id,
        added_at=entry.added_at,
        added_by=entry.added_by,
        note=entry.note,
        attachments=[
            PublicationEntryAttachmentRecord(
                file_reference=a.file_reference,
                file_name=a.file_name,
                media_type=a.media_type,
                uploaded_at=a.uploaded_at,
                note=a.note,
            )
            for a in entry.attachments
        ],
    )


def publication_entry_to_domain(
    record: PublicationLogEntryRecord,
) -> PublicationLogEntry:
    return PublicationLogEntry(
        id=PublicationLogEntryId(record.id),
        publication_log_id=PublicationLogId(record.publication_log_id),
        added_at=record.added_at,
        added_by=PermissionId(record.added_by),
        note=record.note,
        attachments=[_attachment_to_domain(a) for a in record.attachments],
    )


def publication_log_to_record(
    publication_log: PublicationLog,
) -> PublicationLogRecord:
    return PublicationLogRecord(
        id=publication_log.id,
        reference_number=publication_log.reference_number.value,
        project_id=publication_log.collection_use_project_id,
        curator=publication_log.curator,
        entries=[publication_entry_to_record(e) for e in publication_log.entries],
    )


def publication_log_to_domain(
    record: PublicationLogRecord,
) -> PublicationLog:
    return PublicationLog(
        id=PublicationLogId(record.id),
        reference_number=ReferenceNumber(record.reference_number),
        collection_use_project_id=CollectionUseProjectId(record.project_id),
        curator=PermissionId(record.curator) if record.curator else None,
        entries=[publication_entry_to_domain(e) for e in record.entries],
    )


def proposal_to_record(proposal: Proposal) -> ProposalRecord:
    return ProposalRecord(
        id=proposal.id,
        reference_number=proposal.reference_number.value,
        title=proposal.title,
        collection_use_project_id=proposal.collection_use_project_id,
        type=proposal.intended_use,
        begin_date=proposal.begin_date,
        end_date=proposal.end_date,
        status=proposal.status,
        requested_by=proposal.requested_by,
        requester_name=(
            proposal.requester_contact.name if proposal.requester_contact else None
        ),
        requester_email=(
            proposal.requester_contact.email.value
            if proposal.requester_contact
            else None
        ),
        assigned_to=proposal.assigned_to,
        submitted_at=proposal.submitted_at,
        events=[
            ProposalEventRecord(
                occurred_at=event.occurred_at,
                type=event.type,
                triggered_by=event.triggered_by,
                note=event.note,
            )
            for event in proposal.events
        ],
        requested_documents=[
            RequestedDocumentRecord(
                id=rd.id,
                type=rd.type.value,
                description=rd.description,
                requested_at=rd.requested_at,
                requested_by=rd.requested_by,
            )
            for rd in proposal.requested_documents
        ],
        requested_objects=[
            RequestedObjectRecord(
                id=ro.id,
                inventory_number=ro.inventory_number,
                display_title=ro.display_title,
                object_name=ro.object_name,
                brief_description_snapshot=ro.brief_description_snapshot,
                category=ro.category,
                description=ro.description,
                requested_at=ro.requested_at,
                requested_by=ro.requested_by,
            )
            for ro in proposal.requested_objects
        ],
        documents=[
            DocumentRecord(
                id=document.id,
                type=document.type.value,
                file_name=document.file_name,
                file_reference=document.file_reference,
                submitted_at=document.submitted_at,
                submitted_by=document.submitted_by,
            )
            for document in proposal.documents
        ],
        correction_items=[
            DocumentCorrectionItemRecord(
                id=item.id,
                document_id=item.document_id,
                document_type=item.document_type.value,
                reason=item.reason,
                status=item.status.value,
                requested_at=item.requested_at,
                requested_by=item.requested_by,
                resolved_at=item.resolved_at,
            )
            for item in proposal.correction_items
        ],
    )


def proposal_to_domain(record: ProposalRecord) -> Proposal:
    return Proposal(
        id=ProposalId(record.id),
        reference_number=ReferenceNumber(record.reference_number),
        title=record.title,
        collection_use_project_id=(
            CollectionUseProjectId(record.collection_use_project_id)
            if record.collection_use_project_id is not None
            else None
        ),
        intended_use=record.type,
        begin_date=record.begin_date,
        end_date=record.end_date,
        status=record.status,
        requested_by=PermissionId(record.requested_by)
        if record.requested_by is not None
        else None,
        assigned_to=PermissionId(record.assigned_to) if record.assigned_to else None,
        submitted_at=record.submitted_at,
        requester_contact=(
            RequesterContact(
                name=record.requester_name,
                email=EmailAddress(record.requester_email),
            )
            if record.requester_name is not None and record.requester_email is not None
            else None
        ),
        events=[
            ProposalEvent(
                occurred_at=event.occurred_at,
                type=event.type,
                triggered_by=PermissionId(event.triggered_by)
                if event.triggered_by is not None
                else None,
                note=event.note,
            )
            for event in record.events
        ],
        requested_documents=[
            RequestedDocument(
                id=RequestedDocumentId(rd.id),
                type=DocumentType(rd.type),
                description=rd.description,
                requested_at=rd.requested_at,
                requested_by=PermissionId(rd.requested_by),
            )
            for rd in record.requested_documents
        ],
        requested_objects=[
            RequestedObject(
                id=RequestedObjectId(ro.id),
                inventory_number=ro.inventory_number,
                display_title=ro.display_title,
                object_name=ro.object_name,
                brief_description_snapshot=ro.brief_description_snapshot,
                category=ro.category,
                description=ro.description,
                requested_at=ro.requested_at,
                requested_by=PermissionId(ro.requested_by)
                if ro.requested_by is not None
                else None,
            )
            for ro in record.requested_objects
        ],
        documents=[
            Document(
                id=DocumentId(document.id),
                type=DocumentType(document.type),
                file_name=document.file_name,
                file_reference=document.file_reference,
                submitted_at=document.submitted_at,
                submitted_by=PermissionId(document.submitted_by)
                if document.submitted_by is not None
                else None,
            )
            for document in record.documents
        ],
        correction_items=[
            DocumentCorrectionItem(
                id=DocumentCorrectionItemId(item.id),
                document_type=DocumentType(item.document_type),
                reason=item.reason,
                requested_at=item.requested_at,
                requested_by=PermissionId(item.requested_by),
                document_id=DocumentId(item.document_id)
                if item.document_id is not None
                else None,
                status=DocumentCorrectionStatus(item.status),
                resolved_at=item.resolved_at,
            )
            for item in record.correction_items
        ],
    )


def conversation_to_record(conversation: Conversation) -> ConversationRecord:
    return ConversationRecord(
        id=conversation.id,
        proposal_id=conversation.proposal_id,
        external_message_id=conversation.external_message_id,
        messages=[
            MessageRecord(
                id=message.id,
                sent_at=message.sent_at,
                sender=message.sender.value,
                recipient=message.recipient.value,
                subject=message.subject,
                body=message.body,
                attachments=[
                    MessageAttachmentRecord(
                        document_id=attachment.document_id,
                        file_name=attachment.file_name,
                    )
                    for attachment in message.attachments
                ],
            )
            for message in conversation.messages
        ],
    )


def conversation_to_domain(record: ConversationRecord) -> Conversation:
    return Conversation(
        id=ConversationId(record.id),
        proposal_id=ProposalId(record.proposal_id),
        external_message_id=record.external_message_id,
        messages=[
            Message(
                id=MessageId(message.id),
                sent_at=message.sent_at,
                sender=EmailAddress(message.sender),
                recipient=EmailAddress(message.recipient),
                subject=message.subject,
                body=message.body,
                attachments=[
                    MessageAttachment(
                        document_id=DocumentId(attachment.document_id),
                        file_name=attachment.file_name,
                    )
                    for attachment in message.attachments
                ],
            )
            for message in record.messages
        ],
    )


# ── eager-load options ──────────────────────────────────────────────────────--

_PROJECT_EAGER = [
    selectinload(CollectionUseProjectRecord.events),
    selectinload(CollectionUseProjectRecord.objects),
]

_PROPOSAL_EAGER = [
    selectinload(ProposalRecord.events),
    selectinload(ProposalRecord.requested_documents),
    selectinload(ProposalRecord.requested_objects),
    selectinload(ProposalRecord.documents),
    selectinload(ProposalRecord.correction_items),
]

_LOG_ENTRY_EAGER = [
    selectinload(ObjectLogEntryRecord.attachments),
]

_ACCESS_LOG_EAGER = [
    selectinload(ObjectAccessLogRecord.objects).options(
        selectinload(ObjectLogEntryRecord.attachments)
    ),
]

_OCCURRENCE_ENTRY_EAGER = [
    selectinload(ObjectOccurrenceEntryRecord.attachments),
]

_OCCURRENCE_LOG_EAGER = [
    selectinload(ObjectOccurrenceLogRecord.objects).options(
        selectinload(ObjectOccurrenceEntryRecord.attachments)
    ),
]

_PUBLICATION_ENTRY_EAGER = [
    selectinload(PublicationLogEntryRecord.attachments),
]

_PUBLICATION_LOG_EAGER = [
    selectinload(PublicationLogRecord.entries).options(
        selectinload(PublicationLogEntryRecord.attachments)
    ),
]

_MESSAGE_EAGER = selectinload(ConversationRecord.messages).options(
    selectinload(MessageRecord.attachments)
)


# ── repositories ──────────────────────────────────────────────────────────────


class SqlAlchemyCollectionUseProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, project: CollectionUseProject) -> None:
        self._session.add(project_to_record(project))
        await self._session.flush()

    async def get_by_id(
        self, project_id: CollectionUseProjectId
    ) -> CollectionUseProject | None:
        stmt = (
            select(CollectionUseProjectRecord)
            .where(CollectionUseProjectRecord.id == project_id)
            .options(*_PROJECT_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return project_to_domain(record) if record else None

    async def get_by_reference(
        self,
        reference_number: ReferenceNumber,
    ) -> CollectionUseProject | None:
        stmt = (
            select(CollectionUseProjectRecord)
            .where(
                CollectionUseProjectRecord.reference_number == reference_number.value
            )
            .options(*_PROJECT_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return project_to_domain(record) if record else None

    async def save(self, project: CollectionUseProject) -> None:
        record = project_to_record(project)
        await self._session.merge(record)
        await self._session.flush()

    async def list(
        self,
        filters: ProjectFilters,
        page: int,
        size: int,
    ) -> tuple[list[CollectionUseProject], int]:
        base_stmt = select(CollectionUseProjectRecord)
        if filters.status:
            base_stmt = base_stmt.where(
                CollectionUseProjectRecord.status == filters.status
            )
        if filters.use_type:
            base_stmt = base_stmt.where(
                CollectionUseProjectRecord.type == filters.use_type
            )
        if filters.requested_by:
            base_stmt = base_stmt.where(
                CollectionUseProjectRecord.requested_by == filters.requested_by
            )
        if filters.date_from:
            base_stmt = base_stmt.where(
                CollectionUseProjectRecord.begin_date >= filters.date_from
            )
        if filters.date_to:
            base_stmt = base_stmt.where(
                CollectionUseProjectRecord.begin_date <= filters.date_to
            )
        if filters.search:
            pattern = f"%{filters.search}%"
            base_stmt = base_stmt.where(
                CollectionUseProjectRecord.title.ilike(pattern)
                | CollectionUseProjectRecord.reference_number.ilike(pattern)
            )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        data_stmt = (
            base_stmt.options(*_PROJECT_EAGER)
            .order_by(CollectionUseProjectRecord.begin_date.desc())
            .offset(page * size)
            .limit(size)
        )
        data_result = await self._session.execute(data_stmt)
        records = data_result.scalars().all()
        return [project_to_domain(r) for r in records], total


class SqlAlchemyProposalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, proposal: Proposal) -> None:
        self._session.add(proposal_to_record(proposal))
        await self._session.flush()

    async def next_reference_number_for(self, day: date) -> ReferenceNumber:
        prefix = f"VRP-{day:%Y%m%d}-"
        stmt = select(func.max(ProposalRecord.reference_number)).where(
            ProposalRecord.reference_number.like(f"{prefix}%")
        )
        result = await self._session.execute(stmt)
        latest = result.scalar_one_or_none()
        sequence = int(latest.removeprefix(prefix)) + 1 if latest else 1
        return ReferenceNumber(f"{prefix}{sequence:04d}")

    async def get_by_id(self, proposal_id: ProposalId) -> Proposal | None:
        stmt = (
            select(ProposalRecord)
            .where(ProposalRecord.id == proposal_id)
            .options(*_PROPOSAL_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return proposal_to_domain(record) if record else None

    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> Proposal | None:
        stmt = (
            select(ProposalRecord)
            .where(ProposalRecord.collection_use_project_id == project_id)
            .options(*_PROPOSAL_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return proposal_to_domain(record) if record else None

    async def list_by_project_ids(
        self, project_ids: list[CollectionUseProjectId]
    ) -> list[Proposal]:
        if not project_ids:
            return []
        stmt = (
            select(ProposalRecord)
            .where(ProposalRecord.collection_use_project_id.in_(project_ids))
            .options(*_PROPOSAL_EAGER)
        )
        result = await self._session.execute(stmt)
        records = result.scalars().all()
        return [proposal_to_domain(record) for record in records]

    async def save(self, proposal: Proposal) -> None:
        record = proposal_to_record(proposal)
        await self._session.merge(record)
        await self._session.flush()

    async def list(
        self,
        filters: ProposalFilters,
        page: int,
        size: int,
    ) -> tuple[list[Proposal], int]:
        base_stmt = select(ProposalRecord)
        if filters.statuses:
            base_stmt = base_stmt.where(ProposalRecord.status.in_(filters.statuses))
        if filters.use_type:
            base_stmt = base_stmt.where(ProposalRecord.type == filters.use_type)
        if filters.assigned_to:
            base_stmt = base_stmt.where(
                ProposalRecord.assigned_to == filters.assigned_to
            )
        if filters.requested_by:
            base_stmt = base_stmt.where(
                ProposalRecord.requested_by == filters.requested_by
            )
        if filters.date_from:
            base_stmt = base_stmt.where(ProposalRecord.begin_date >= filters.date_from)
        if filters.date_to:
            base_stmt = base_stmt.where(ProposalRecord.begin_date <= filters.date_to)
        if filters.search:
            pattern = f"%{filters.search}%"
            base_stmt = base_stmt.outerjoin(
                CollectionUseProjectRecord,
                CollectionUseProjectRecord.id
                == ProposalRecord.collection_use_project_id,
            ).where(
                or_(
                    ProposalRecord.title.ilike(pattern),
                    ProposalRecord.reference_number.ilike(pattern),
                    CollectionUseProjectRecord.title.ilike(pattern),
                    CollectionUseProjectRecord.reference_number.ilike(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total_result = await self._session.execute(count_stmt)
        total = total_result.scalar_one()

        data_stmt = (
            base_stmt.options(*_PROPOSAL_EAGER)
            .order_by(ProposalRecord.submitted_at.desc())
            .offset(page * size)
            .limit(size)
        )
        data_result = await self._session.execute(data_stmt)
        records = data_result.scalars().all()
        return [proposal_to_domain(r) for r in records], total


class SqlAlchemyConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, conversation: Conversation) -> None:
        self._session.add(conversation_to_record(conversation))
        await self._session.flush()

    async def get_by_id(self, conversation_id: ConversationId) -> Conversation | None:
        stmt = (
            select(ConversationRecord)
            .where(ConversationRecord.id == conversation_id)
            .options(_MESSAGE_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return conversation_to_domain(record) if record else None

    async def get_by_proposal_id(self, proposal_id: ProposalId) -> Conversation | None:
        stmt = (
            select(ConversationRecord)
            .where(ConversationRecord.proposal_id == proposal_id)
            .options(_MESSAGE_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return conversation_to_domain(record) if record else None

    async def get_by_external_message_id(self, message_id: str) -> Conversation | None:
        stmt = (
            select(ConversationRecord)
            .where(ConversationRecord.external_message_id == message_id)
            .options(_MESSAGE_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return conversation_to_domain(record) if record else None

    async def save(self, conversation: Conversation) -> None:
        record = conversation_to_record(conversation)
        await self._session.merge(record)
        await self._session.flush()


class SqlAlchemyObjectAccessLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, access_log: ObjectAccessLog) -> None:
        self._session.add(access_log_to_record(access_log))
        await self._session.flush()

    async def get_by_id(
        self, access_log_id: ObjectAccessLogId
    ) -> ObjectAccessLog | None:
        stmt = (
            select(ObjectAccessLogRecord)
            .where(ObjectAccessLogRecord.id == access_log_id)
            .options(*_ACCESS_LOG_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return access_log_to_domain(record) if record else None

    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> ObjectAccessLog | None:
        stmt = (
            select(ObjectAccessLogRecord)
            .where(ObjectAccessLogRecord.project_id == project_id)
            .options(*_ACCESS_LOG_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return access_log_to_domain(record) if record else None

    async def get_entry_by_id(
        self, entry_id: ObjectLogEntryId
    ) -> ObjectLogEntry | None:
        stmt = (
            select(ObjectLogEntryRecord)
            .where(ObjectLogEntryRecord.id == entry_id)
            .options(*_LOG_ENTRY_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return log_entry_to_domain(record) if record else None

    async def save(self, access_log: ObjectAccessLog) -> None:
        await self._session.merge(access_log_to_record(access_log))
        await self._session.flush()

    async def save_entry(self, entry: ObjectLogEntry) -> None:
        await self._session.merge(log_entry_to_record(entry))
        await self._session.flush()

    async def list_entries_by_project(
        self,
        project_id: CollectionUseProjectId,
        added_by: str | None,
        page: int,
        size: int,
    ) -> tuple[list[ObjectLogEntry], int]:
        base_stmt = (
            select(ObjectLogEntryRecord)
            .join(
                ObjectAccessLogRecord,
                ObjectLogEntryRecord.access_log_id == ObjectAccessLogRecord.id,
            )
            .where(ObjectAccessLogRecord.project_id == project_id)
        )
        if added_by:
            base_stmt = base_stmt.where(ObjectLogEntryRecord.added_by == added_by)
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        data_stmt = (
            base_stmt.options(*_LOG_ENTRY_EAGER)
            .order_by(ObjectLogEntryRecord.added_at)
            .offset(page * size)
            .limit(size)
        )
        records = (await self._session.execute(data_stmt)).scalars().all()
        return [log_entry_to_domain(r) for r in records], total


class SqlAlchemyObjectOccurrenceLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, occurrence_log: ObjectOccurrenceLog) -> None:
        self._session.add(occurrence_log_to_record(occurrence_log))
        await self._session.flush()

    async def get_by_id(
        self, occurrence_log_id: ObjectOccurrenceLogId
    ) -> ObjectOccurrenceLog | None:
        stmt = (
            select(ObjectOccurrenceLogRecord)
            .where(ObjectOccurrenceLogRecord.id == occurrence_log_id)
            .options(*_OCCURRENCE_LOG_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return occurrence_log_to_domain(record) if record else None

    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> ObjectOccurrenceLog | None:
        stmt = (
            select(ObjectOccurrenceLogRecord)
            .where(ObjectOccurrenceLogRecord.project_id == project_id)
            .options(*_OCCURRENCE_LOG_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return occurrence_log_to_domain(record) if record else None

    async def get_entry_by_id(
        self, entry_id: ObjectOccurrenceEntryId
    ) -> ObjectOccurrenceEntry | None:
        stmt = (
            select(ObjectOccurrenceEntryRecord)
            .where(ObjectOccurrenceEntryRecord.id == entry_id)
            .options(*_OCCURRENCE_ENTRY_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return occurrence_entry_to_domain(record) if record else None

    async def save(self, occurrence_log: ObjectOccurrenceLog) -> None:
        await self._session.merge(occurrence_log_to_record(occurrence_log))
        await self._session.flush()

    async def save_entry(self, entry: ObjectOccurrenceEntry) -> None:
        await self._session.merge(occurrence_entry_to_record(entry))
        await self._session.flush()

    async def list_entries_by_project(
        self,
        project_id: CollectionUseProjectId,
        reported_by: str | None,
        page: int,
        size: int,
    ) -> tuple[list[ObjectOccurrenceEntry], int]:
        base_stmt = (
            select(ObjectOccurrenceEntryRecord)
            .join(
                ObjectOccurrenceLogRecord,
                ObjectOccurrenceEntryRecord.occurrence_log_id
                == ObjectOccurrenceLogRecord.id,
            )
            .where(ObjectOccurrenceLogRecord.project_id == project_id)
        )
        if reported_by:
            base_stmt = base_stmt.where(
                ObjectOccurrenceEntryRecord.reported_by == reported_by
            )
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        data_stmt = (
            base_stmt.options(*_OCCURRENCE_ENTRY_EAGER)
            .order_by(ObjectOccurrenceEntryRecord.occurrence_date)
            .offset(page * size)
            .limit(size)
        )
        records = (await self._session.execute(data_stmt)).scalars().all()
        return [occurrence_entry_to_domain(r) for r in records], total


class SqlAlchemyPublicationLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, publication_log: PublicationLog) -> None:
        self._session.add(publication_log_to_record(publication_log))
        await self._session.flush()

    async def get_by_id(
        self, publication_log_id: PublicationLogId
    ) -> PublicationLog | None:
        stmt = (
            select(PublicationLogRecord)
            .where(PublicationLogRecord.id == publication_log_id)
            .options(*_PUBLICATION_LOG_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return publication_log_to_domain(record) if record else None

    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> PublicationLog | None:
        stmt = (
            select(PublicationLogRecord)
            .where(PublicationLogRecord.project_id == project_id)
            .options(*_PUBLICATION_LOG_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return publication_log_to_domain(record) if record else None

    async def get_entry_by_id(
        self, entry_id: PublicationLogEntryId
    ) -> PublicationLogEntry | None:
        stmt = (
            select(PublicationLogEntryRecord)
            .where(PublicationLogEntryRecord.id == entry_id)
            .options(*_PUBLICATION_ENTRY_EAGER)
        )
        result = await self._session.execute(stmt)
        record = result.scalar_one_or_none()
        return publication_entry_to_domain(record) if record else None

    async def save(self, publication_log: PublicationLog) -> None:
        await self._session.merge(publication_log_to_record(publication_log))
        await self._session.flush()

    async def save_entry(self, entry: PublicationLogEntry) -> None:
        await self._session.merge(publication_entry_to_record(entry))
        await self._session.flush()

    async def list_entries_by_project(
        self,
        project_id: CollectionUseProjectId,
        added_by: str | None,
        page: int,
        size: int,
    ) -> tuple[list[PublicationLogEntry], int]:
        base_stmt = (
            select(PublicationLogEntryRecord)
            .join(
                PublicationLogRecord,
                PublicationLogEntryRecord.publication_log_id == PublicationLogRecord.id,
            )
            .where(PublicationLogRecord.project_id == project_id)
        )
        if added_by:
            base_stmt = base_stmt.where(PublicationLogEntryRecord.added_by == added_by)
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()
        data_stmt = (
            base_stmt.options(*_PUBLICATION_ENTRY_EAGER)
            .order_by(PublicationLogEntryRecord.added_at)
            .offset(page * size)
            .limit(size)
        )
        records = (await self._session.execute(data_stmt)).scalars().all()
        return [publication_entry_to_domain(r) for r in records], total


def _attachment_views(attachments: list[Attachment]) -> list[ExportAttachmentView]:
    return [
        ExportAttachmentView(
            source_id=att.file_reference,
            description=att.note or att.file_name,
            reference=att.file_reference,
            position=index,
        )
        for index, att in enumerate(attachments)
    ]


class SqlAlchemyProjectExportReader:
    """OHS read adapter backing :class:`ProjectExportReader`.

    Composes the project, proposal and the three journal repositories into a
    single read-only :class:`ProjectExportView`, hydrating the requester's
    display name through Identity's published reader.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, project_id: str) -> ProjectExportView | None:
        typed_id = CollectionUseProjectId(project_id)
        project = await SqlAlchemyCollectionUseProjectRepository(
            self._session
        ).get_by_id(typed_id)
        if project is None:
            return None

        proposal = await SqlAlchemyProposalRepository(self._session).get_by_project_id(
            typed_id
        )
        access_log = await SqlAlchemyObjectAccessLogRepository(
            self._session
        ).get_by_project_id(typed_id)
        occurrence_log = await SqlAlchemyObjectOccurrenceLogRepository(
            self._session
        ).get_by_project_id(typed_id)
        publication_log = await SqlAlchemyPublicationLogRepository(
            self._session
        ).get_by_project_id(typed_id)

        return ProjectExportView(
            project_id=str(project.id),
            reference_number=project.reference_number.value,
            begin_date=project.begin_date,
            end_date=project.end_date,
            intended_use=project.intended_use,
            visitor_name=await self._visitor_name(project.requested_by),
            requested_objects=[
                ExportObjectView(
                    source_id=ro.inventory_number,
                    description=ro.description,
                    position=index,
                )
                for index, ro in enumerate(
                    proposal.requested_objects if proposal else []
                )
            ],
            in_situ_occurrences=[
                ExportEntryView(
                    source_id=str(entry.id),
                    description=entry.detailed_description,
                    position=index,
                    attachments=_attachment_views(entry.attachments),
                )
                for index, entry in enumerate(
                    occurrence_log.objects if occurrence_log else []
                )
            ],
            in_situ_logs=[
                ExportEntryView(
                    source_id=str(entry.id),
                    description=entry.observations or "",
                    position=index,
                    attachments=_attachment_views(entry.attachments),
                )
                for index, entry in enumerate(access_log.objects if access_log else [])
            ],
            in_situ_publications=[
                ExportEntryView(
                    source_id=str(entry.id),
                    description=entry.note,
                    position=index,
                    attachments=_attachment_views(entry.attachments),
                )
                for index, entry in enumerate(
                    publication_log.entries if publication_log else []
                )
            ],
        )

    async def _visitor_name(self, requested_by: PermissionId) -> str:
        from app.identity.public import get_permission_reader

        detail = await get_permission_reader(self._session).get_detail(requested_by)
        return detail.user.name if detail else str(requested_by)
