"""SQLAlchemy ORM models for the In Situ Visit CIDOC mapping context.

Class names carry an ``Orm`` suffix because the domain classes (in
``domain/models.py``) already use the PUML ``...Record`` names. Tables form the
``InSituVisitRecord`` aggregate: a root plus four child collections, with
attachments cascading off occurrences, logs, and publications.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InSituVisitRecordOrm(Base):
    __tablename__ = "in_situ_visit_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    visit_begin_date: Mapped[date] = mapped_column(Date)
    visit_end_date: Mapped[date] = mapped_column(Date)
    visitor_name: Mapped[str] = mapped_column(String(255))
    place_name: Mapped[str] = mapped_column(String(255))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    institution_name: Mapped[str] = mapped_column(String(255), default="")
    record_schema_version: Mapped[int | None] = mapped_column(Integer, default=None)
    mapping_version: Mapped[str | None] = mapped_column(String(64), default=None)
    crm_version: Mapped[str | None] = mapped_column(String(64), default=None)
    source_project_id: Mapped[str | None] = mapped_column(String(36), default=None)
    project_title: Mapped[str | None] = mapped_column(String(255), default=None)
    project_purpose: Mapped[str | None] = mapped_column(Text, default=None)
    planned_begin_date: Mapped[date | None] = mapped_column(Date, default=None)
    planned_end_date: Mapped[date | None] = mapped_column(Date, default=None)
    execution_evidence_type: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    execution_occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    execution_recorded_by: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    execution_evidence_gaps: Mapped[list[str] | None] = mapped_column(
        JSON, default=None
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    approved_by: Mapped[str | None] = mapped_column(String(255), default=None)
    approval_note: Mapped[str | None] = mapped_column(Text, default=None)

    requested_objects: Mapped[list[RequestedObjectRecordOrm]] = relationship(
        back_populates="visit",
        cascade="all, delete-orphan",
        order_by="RequestedObjectRecordOrm.position",
    )
    occurrences: Mapped[list[InSituOccurrenceRecordOrm]] = relationship(
        back_populates="visit",
        cascade="all, delete-orphan",
        order_by="InSituOccurrenceRecordOrm.position",
    )
    logs: Mapped[list[InSituLogRecordOrm]] = relationship(
        back_populates="visit",
        cascade="all, delete-orphan",
        order_by="InSituLogRecordOrm.position",
    )
    publications: Mapped[list[InSituPublicationRecordOrm]] = relationship(
        back_populates="visit",
        cascade="all, delete-orphan",
        order_by="InSituPublicationRecordOrm.position",
    )


class RequestedObjectRecordOrm(Base):
    __tablename__ = "requested_object_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    visit_record_id: Mapped[str] = mapped_column(
        ForeignKey("in_situ_visit_records.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer)
    display_title: Mapped[str | None] = mapped_column(String(255), default=None)
    object_name: Mapped[str | None] = mapped_column(String(255), default=None)
    brief_description_snapshot: Mapped[str | None] = mapped_column(Text, default=None)

    visit: Mapped[InSituVisitRecordOrm] = relationship(
        back_populates="requested_objects"
    )


class InSituOccurrenceRecordOrm(Base):
    __tablename__ = "in_situ_occurrence_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    visit_record_id: Mapped[str] = mapped_column(
        ForeignKey("in_situ_visit_records.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer)
    related_object_source_id: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    number_of_objects: Mapped[int | None] = mapped_column(Integer, default=None)
    occurrence_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    location: Mapped[str | None] = mapped_column(String(255), default=None)
    reported_by: Mapped[str | None] = mapped_column(String(255), default=None)
    testimonial: Mapped[str | None] = mapped_column(Text, default=None)
    occurrence_log_date_conclusion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    occurrence_log_curator: Mapped[str | None] = mapped_column(
        String(255), default=None
    )

    visit: Mapped[InSituVisitRecordOrm] = relationship(back_populates="occurrences")
    attachments: Mapped[list[InSituOccurrenceAttachmentRecordOrm]] = relationship(
        back_populates="occurrence",
        cascade="all, delete-orphan",
        order_by="InSituOccurrenceAttachmentRecordOrm.position",
    )


class InSituOccurrenceAttachmentRecordOrm(Base):
    __tablename__ = "in_situ_occurrence_attachment_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    occurrence_id: Mapped[str] = mapped_column(
        ForeignKey("in_situ_occurrence_records.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    reference: Mapped[str] = mapped_column(String(1024))
    position: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str | None] = mapped_column(String(64), default=None)

    occurrence: Mapped[InSituOccurrenceRecordOrm] = relationship(
        back_populates="attachments"
    )


class InSituLogRecordOrm(Base):
    __tablename__ = "in_situ_log_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    visit_record_id: Mapped[str] = mapped_column(
        ForeignKey("in_situ_visit_records.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer)
    related_object_source_id: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    number_of_objects: Mapped[int | None] = mapped_column(Integer, default=None)
    added_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    added_by: Mapped[str | None] = mapped_column(String(255), default=None)
    access_log_date_conclusion: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    access_log_curator: Mapped[str | None] = mapped_column(String(255), default=None)

    visit: Mapped[InSituVisitRecordOrm] = relationship(back_populates="logs")
    attachments: Mapped[list[InSituLogAttachmentRecordOrm]] = relationship(
        back_populates="log",
        cascade="all, delete-orphan",
        order_by="InSituLogAttachmentRecordOrm.position",
    )


class InSituLogAttachmentRecordOrm(Base):
    __tablename__ = "in_situ_log_attachment_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    log_id: Mapped[str] = mapped_column(
        ForeignKey("in_situ_log_records.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    reference: Mapped[str] = mapped_column(String(1024))
    position: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str | None] = mapped_column(String(64), default=None)

    log: Mapped[InSituLogRecordOrm] = relationship(back_populates="attachments")


class InSituPublicationRecordOrm(Base):
    __tablename__ = "in_situ_publication_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    visit_record_id: Mapped[str] = mapped_column(
        ForeignKey("in_situ_visit_records.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer)
    related_object_source_id: Mapped[str | None] = mapped_column(
        String(255), default=None
    )
    added_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    added_by: Mapped[str | None] = mapped_column(String(255), default=None)

    visit: Mapped[InSituVisitRecordOrm] = relationship(back_populates="publications")
    attachments: Mapped[list[InSituPublicationAttachmentRecordOrm]] = relationship(
        back_populates="publication",
        cascade="all, delete-orphan",
        order_by="InSituPublicationAttachmentRecordOrm.position",
    )


class InSituPublicationAttachmentRecordOrm(Base):
    __tablename__ = "in_situ_publication_attachment_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("in_situ_publication_records.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    reference: Mapped[str] = mapped_column(String(1024))
    position: Mapped[int] = mapped_column(Integer)
    media_type: Mapped[str | None] = mapped_column(String(64), default=None)

    publication: Mapped[InSituPublicationRecordOrm] = relationship(
        back_populates="attachments"
    )
