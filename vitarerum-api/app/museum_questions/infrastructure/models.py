"""SQLAlchemy ORM model for the Museum Questions context.

A single table, ``museum_questions``. The answer/out-of-scope/close columns
are mapped now (schema created up front, see the migration) but this plan
only ever writes ``SUBMITTED`` rows with those columns left null — the
internal response section populates them.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MuseumQuestionRecord(Base):
    __tablename__ = "museum_questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    requester_name: Mapped[str] = mapped_column(Text)
    requester_email: Mapped[str] = mapped_column(Text)
    requester_email_hash: Mapped[str] = mapped_column(String(64), index=True)
    subject: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    answered_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    answer_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    out_of_scope_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    out_of_scope_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    out_of_scope_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    out_of_scope_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
