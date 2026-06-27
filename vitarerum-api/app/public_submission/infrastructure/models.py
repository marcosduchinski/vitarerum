"""SQLAlchemy ORM model for the public submission context.

A single table, ``public_proposal_submissions``, holding one row per pending
double opt-in request. ``proposal_reference`` references the materialised
proposal (Use of Collections) by its human-readable number, kept as a plain
string (no cross-context FK), matching the convention used elsewhere.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PublicProposalSubmissionRecord(Base):
    __tablename__ = "public_proposal_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    citizen_name: Mapped[str] = mapped_column(String(120))
    citizen_email: Mapped[str] = mapped_column(String(180), index=True)
    subject: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    consent: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    proposal_reference: Mapped[str | None] = mapped_column(String(32), nullable=True)
