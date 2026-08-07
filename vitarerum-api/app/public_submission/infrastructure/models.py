"""SQLAlchemy ORM model for the public submission context.

A single table, ``public_proposal_submissions``, holding one row per pending
double opt-in request. ``proposal_reference`` references the materialised
proposal (Use of Collections) by its human-readable number, kept as a plain
string (no cross-context FK), matching the convention used elsewhere.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PublicProposalSubmissionRecord(Base):
    __tablename__ = "public_proposal_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    citizen_name: Mapped[str] = mapped_column(Text)
    citizen_email: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    use_type: Mapped[str] = mapped_column(String(32))
    proposed_begin_date: Mapped[date] = mapped_column(Date)
    proposed_end_date: Mapped[date] = mapped_column(Date)
    consent: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    proposal_reference: Mapped[str | None] = mapped_column(String(32), nullable=True)

    documents: Mapped[list[PublicDocumentSubmissionRecord]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class PublicDocumentSubmissionRecord(Base):
    __tablename__ = "public_proposal_submission_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    submission_id: Mapped[str] = mapped_column(
        ForeignKey("public_proposal_submissions.id"), index=True
    )
    file_name: Mapped[str] = mapped_column(Text)
    file_reference: Mapped[str] = mapped_column(String(512))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    submission: Mapped[PublicProposalSubmissionRecord] = relationship(
        back_populates="documents"
    )


class ProposalAmendmentTokenRecord(Base):
    __tablename__ = "proposal_amendment_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(36), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    requester_email: Mapped[str] = mapped_column(Text)
    correction_item_ids: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
