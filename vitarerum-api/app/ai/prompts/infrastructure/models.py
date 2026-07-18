from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PromptTemplateOrm(Base):
    __tablename__ = "ai_prompt_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(64), index=True)
    key: Mapped[str] = mapped_column(String(96), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    variables_schema_json: Mapped[str] = mapped_column(Text)
    active_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        UniqueConstraint("purpose", "key", name="uq_ai_prompt_templates_purpose_key"),
    )


class PromptTemplateVersionOrm(Base):
    __tablename__ = "ai_prompt_template_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ai_prompt_templates.id"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    version_label: Mapped[str] = mapped_column(String(96), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(Text)
    default_temperature: Mapped[float] = mapped_column(Float)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    published_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "template_id", "version", name="uq_ai_prompt_template_versions_number"
        ),
        UniqueConstraint(
            "template_id", "version_label", name="uq_ai_prompt_template_versions_label"
        ),
        Index(
            "ix_ai_prompt_template_versions_one_published",
            "template_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
            sqlite_where=text("status = 'published'"),
        ),
    )
