"""SQLAlchemy ORM models for the In Situ Visit CIDOC mapping context.

Class names carry an ``Orm`` suffix because the domain classes (in
``domain/models.py``) already use the PUML ``...Record`` names. Tables form the
``InSituVisitRecord`` aggregate: a root plus four child collections, with
attachments cascading off occurrences, logs, and publications.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
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

    publication: Mapped[InSituPublicationRecordOrm] = relationship(
        back_populates="attachments"
    )
