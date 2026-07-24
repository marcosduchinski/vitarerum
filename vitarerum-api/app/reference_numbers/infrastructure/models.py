from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReferencePolicyRecord(Base):
    __tablename__ = "reference_policies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    mask: Mapped[str] = mapped_column(String(128))
    sequence_scope: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    active_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    active_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReferenceLegacyFormatRecord(Base):
    __tablename__ = "reference_legacy_formats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(96))
    pattern: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        UniqueConstraint(
            "kind", "pattern", name="uq_reference_legacy_formats_kind_pattern"
        ),
    )


class ReferencePolicySequenceRecord(Base):
    __tablename__ = "reference_policy_sequences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reference_policies.id"), index=True
    )
    scope_key: Mapped[str] = mapped_column(String(32))
    next_value: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "policy_id", "scope_key", name="uq_reference_policy_sequences_scope"
        ),
    )


class ReferencePolicyEventRecord(Base):
    __tablename__ = "reference_policy_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reference_policies.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    actor_permission_id: Mapped[str] = mapped_column(String(128), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
