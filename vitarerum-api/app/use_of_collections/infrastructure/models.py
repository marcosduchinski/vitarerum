from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

import app.identity.infrastructure.models  # noqa: F401
from app.database import Base
from app.use_of_collections.domain.enums import (
    MediaType,
    ProposalEventType,
    ProposalStatus,
    SubmissionChannel,
    UseEventType,
    UseResult,
    UseStatus,
    UseType,
)


class CollectionUseProjectRecord(Base):
    __tablename__ = "collection_use_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reference_number: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_id: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True
    )
    origin_project_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "collection_use_projects.id",
            name="fk_collection_use_projects_origin_project_id",
        ),
        index=True,
        nullable=True,
    )
    type: Mapped[UseType] = mapped_column(SAEnum(UseType, name="use_type"))
    status: Mapped[UseStatus] = mapped_column(SAEnum(UseStatus, name="use_status"))
    result: Mapped[UseResult | None] = mapped_column(
        SAEnum(UseResult, name="use_result"),
        nullable=True,
    )
    authorised_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    authorised_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    begin_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    requested_by: Mapped[str] = mapped_column(String(36), index=True)

    events: Mapped[list[UseEventRecord]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    objects: Mapped[list[CollectionUseObjectRecord]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    origin_project: Mapped[CollectionUseProjectRecord | None] = relationship(
        remote_side=[id],
    )


class CollectionUseObjectRecord(Base):
    __tablename__ = "collection_use_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("collection_use_projects.id"), index=True
    )
    inventory_number: Mapped[str] = mapped_column(String(128))
    display_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brief_description_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    collection_id: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True
    )
    collection_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str] = mapped_column(String(36), index=True)

    project: Mapped[CollectionUseProjectRecord] = relationship(back_populates="objects")
    log_entries: Mapped[list[ObjectLogEntryRecord]] = relationship(
        back_populates="collection_use_object"
    )
    occurrence_entries: Mapped[list[ObjectOccurrenceEntryRecord]] = relationship(
        back_populates="collection_use_object"
    )


class StaffProjectTodoItemRecord(Base):
    __tablename__ = "staff_project_todo_items"
    __table_args__ = (
        Index(
            "ix_staff_project_todo_project_owner_position_created",
            "project_id",
            "owner_permission_id",
            "position",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("collection_use_projects.id"),
        nullable=False,
    )
    owner_permission_id: Mapped[str] = mapped_column(
        ForeignKey("identity_permissions.id"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(String(160))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)


class UseEventRecord(Base):
    __tablename__ = "use_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("collection_use_projects.id"),
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    type: Mapped[UseEventType] = mapped_column(
        SAEnum(UseEventType, name="use_event_type")
    )
    triggered_by: Mapped[str] = mapped_column(String(36), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped[CollectionUseProjectRecord] = relationship(back_populates="events")


# ── Journal aggregates ──────────────────────────────────────────────────────--


class ObjectAccessLogRecord(Base):
    __tablename__ = "object_access_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reference_number: Mapped[str] = mapped_column(String(32), unique=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("collection_use_projects.id"),
        unique=True,
        index=True,
    )
    date_conclusion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    curator: Mapped[str | None] = mapped_column(String(36), nullable=True)

    objects: Mapped[list[ObjectLogEntryRecord]] = relationship(
        back_populates="access_log",
        cascade="all, delete-orphan",
    )


class ObjectLogEntryRecord(Base):
    __tablename__ = "object_log_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    access_log_id: Mapped[str] = mapped_column(
        ForeignKey("object_access_logs.id"),
        index=True,
    )
    number_of_objects: Mapped[int] = mapped_column(Integer)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    added_by: Mapped[str] = mapped_column(String(36), index=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    collection_use_object_id: Mapped[str] = mapped_column(
        ForeignKey("collection_use_objects.id"), index=True
    )

    access_log: Mapped[ObjectAccessLogRecord] = relationship(back_populates="objects")
    collection_use_object: Mapped[CollectionUseObjectRecord] = relationship(
        back_populates="log_entries"
    )
    attachments: Mapped[list[LogEntryAttachmentRecord]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
    )


class LogEntryAttachmentRecord(Base):
    __tablename__ = "log_entry_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(
        ForeignKey("object_log_entries.id"), index=True
    )
    file_reference: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[MediaType] = mapped_column(SAEnum(MediaType, name="media_type"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    description: Mapped[str] = mapped_column(Text)

    entry: Mapped[ObjectLogEntryRecord] = relationship(back_populates="attachments")


class ObjectOccurrenceLogRecord(Base):
    __tablename__ = "object_occurrence_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reference_number: Mapped[str] = mapped_column(String(32), unique=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("collection_use_projects.id"),
        unique=True,
        index=True,
    )
    date_conclusion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    curator: Mapped[str | None] = mapped_column(String(36), nullable=True)

    objects: Mapped[list[ObjectOccurrenceEntryRecord]] = relationship(
        back_populates="occurrence_log",
        cascade="all, delete-orphan",
    )


class ObjectOccurrenceEntryRecord(Base):
    __tablename__ = "object_occurrence_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    occurrence_log_id: Mapped[str] = mapped_column(
        ForeignKey("object_occurrence_logs.id"),
        index=True,
    )
    number_of_objects: Mapped[int] = mapped_column(Integer)
    occurrence_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location: Mapped[str] = mapped_column(String(255))
    reported_by: Mapped[str] = mapped_column(String(36), index=True)
    detailed_description: Mapped[str] = mapped_column(Text)
    testimonial: Mapped[str | None] = mapped_column(Text, nullable=True)
    collection_use_object_id: Mapped[str] = mapped_column(
        ForeignKey("collection_use_objects.id"), index=True
    )

    occurrence_log: Mapped[ObjectOccurrenceLogRecord] = relationship(
        back_populates="objects"
    )
    collection_use_object: Mapped[CollectionUseObjectRecord] = relationship(
        back_populates="occurrence_entries"
    )
    attachments: Mapped[list[OccurrenceEntryAttachmentRecord]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
    )


class OccurrenceEntryAttachmentRecord(Base):
    __tablename__ = "occurrence_entry_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(
        ForeignKey("object_occurrence_entries.id"), index=True
    )
    file_reference: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[MediaType] = mapped_column(SAEnum(MediaType, name="media_type"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    description: Mapped[str] = mapped_column(Text)

    entry: Mapped[ObjectOccurrenceEntryRecord] = relationship(
        back_populates="attachments"
    )


class PublicationLogRecord(Base):
    __tablename__ = "publication_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reference_number: Mapped[str] = mapped_column(String(32), unique=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("collection_use_projects.id"),
        unique=True,
        index=True,
    )
    curator: Mapped[str | None] = mapped_column(String(36), nullable=True)

    entries: Mapped[list[PublicationLogEntryRecord]] = relationship(
        back_populates="publication_log",
        cascade="all, delete-orphan",
    )


class PublicationLogEntryRecord(Base):
    __tablename__ = "publication_log_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_log_id: Mapped[str] = mapped_column(
        ForeignKey("publication_logs.id"),
        index=True,
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    added_by: Mapped[str] = mapped_column(String(36), index=True)
    note: Mapped[str] = mapped_column(Text)
    collection_use_object_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_use_objects.id"), index=True, default=None
    )

    publication_log: Mapped[PublicationLogRecord] = relationship(
        back_populates="entries"
    )
    attachments: Mapped[list[PublicationEntryAttachmentRecord]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
    )


class PublicationEntryAttachmentRecord(Base):
    __tablename__ = "publication_entry_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(
        ForeignKey("publication_log_entries.id"), index=True
    )
    file_reference: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[MediaType] = mapped_column(SAEnum(MediaType, name="media_type"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    description: Mapped[str] = mapped_column(Text)

    entry: Mapped[PublicationLogEntryRecord] = relationship(
        back_populates="attachments"
    )


class ProposalRecord(Base):
    __tablename__ = "proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reference_number: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )
    # title/type/dates are nullable: a proposal may be created as a stub and
    # completed in a later step.
    title: Mapped[str | None] = mapped_column(String(255), nullable=True, default="")
    collection_use_project_id: Mapped[str | None] = mapped_column(
        String(36),
        index=True,
        nullable=True,
    )
    type: Mapped[UseType | None] = mapped_column(
        SAEnum(UseType, name="proposal_use_type"), nullable=True
    )
    begin_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus, name="proposal_status")
    )
    submission_channel: Mapped[SubmissionChannel] = mapped_column(
        SAEnum(SubmissionChannel, name="proposal_submission_channel")
    )
    requested_by: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True
    )
    requester_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    requester_email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    events: Mapped[list[ProposalEventRecord]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
    )
    requested_documents: Mapped[list[RequestedDocumentRecord]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
    )
    requested_objects: Mapped[list[RequestedObjectRecord]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list[DocumentRecord]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
    )
    correction_items: Mapped[list[DocumentCorrectionItemRecord]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
    )


class ProposalEventRecord(Base):
    __tablename__ = "proposal_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    type: Mapped[ProposalEventType] = mapped_column(
        SAEnum(ProposalEventType, name="proposal_event_type")
    )
    triggered_by: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    proposal: Mapped[ProposalRecord] = relationship(back_populates="events")


class RequestedDocumentRecord(Base):
    __tablename__ = "requested_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    type: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str] = mapped_column(String(36), index=True)

    proposal: Mapped[ProposalRecord] = relationship(
        back_populates="requested_documents"
    )


class RequestedObjectRecord(Base):
    __tablename__ = "proposal_requested_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    inventory_number: Mapped[str] = mapped_column(String(128))
    display_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brief_description_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    collection_id: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True
    )
    collection_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True
    )

    proposal: Mapped[ProposalRecord] = relationship(back_populates="requested_objects")


class DocumentRecord(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    type: Mapped[str] = mapped_column(String(128))
    file_name: Mapped[str] = mapped_column(String(255), default="")
    file_reference: Mapped[str] = mapped_column(String(255))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Nullable since migration 00000006: public-submission documents carry no
    # PermissionId (the citizen has no account).
    submitted_by: Mapped[str | None] = mapped_column(
        String(36), index=True, nullable=True
    )

    proposal: Mapped[ProposalRecord] = relationship(back_populates="documents")


class DocumentCorrectionItemRecord(Base):
    __tablename__ = "document_correction_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    document_type: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="REQUESTED")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str] = mapped_column(String(36), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    proposal: Mapped[ProposalRecord] = relationship(back_populates="correction_items")


class ConversationRecord(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(36), index=True, unique=True)
    external_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )

    messages: Mapped[list[MessageRecord]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"),
        index=True,
    )
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sender: Mapped[str] = mapped_column(String(255))
    recipient: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)

    conversation: Mapped[ConversationRecord] = relationship(back_populates="messages")
    attachments: Mapped[list[MessageAttachmentRecord]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class MessageAttachmentRecord(Base):
    __tablename__ = "message_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"), index=True)
    document_id: Mapped[str] = mapped_column(String(36))
    file_name: Mapped[str] = mapped_column(String(255))

    message: Mapped[MessageRecord] = relationship(back_populates="attachments")
