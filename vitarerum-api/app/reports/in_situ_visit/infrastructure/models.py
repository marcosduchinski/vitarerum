"""SQLAlchemy ORM model for the In-Situ Visit Report context.

A single table, ``in_situ_visit_reports``, storing one immutable row per report
(append-only history). ``project_id`` / ``narrative_id`` / ``in_situ_visit_record_id``
reference aggregates in other contexts but are kept as plain strings (no
cross-context FKs), matching the convention used by ``generated_narratives``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InSituVisitReportOrm(Base):
    __tablename__ = "in_situ_visit_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str] = mapped_column(String(36))
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    narrative_id: Mapped[str] = mapped_column(String(36))
    in_situ_visit_record_id: Mapped[str] = mapped_column(String(36))
