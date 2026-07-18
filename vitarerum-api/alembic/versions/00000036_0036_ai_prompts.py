"""Create AI prompt registry

Revision ID: 0036_ai_prompts
Revises: 0035_revision_edited_by
Create Date: 2026-07-18
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0036_ai_prompts"
down_revision: str | None = "0035_revision_edited_by"
branch_labels: str | None = None
depends_on: str | None = None


SCHEMA_JSON = (
    '{"additionalProperties":false,"properties":{"narrative_type":'
    '{"description":"Resolved NarrativeType for this template.","type":"string"}},'
    '"required":["narrative_type"],"type":"object"}'
)
CREATED_AT = datetime(2026, 7, 18, tzinfo=UTC)

PROMPTS = [
    {
        "template_id": "ptpl-insitu-institutional",
        "version_id": "pver-insitu-institutional-v1",
        "key": "system_institutional",
        "name": "In-situ narrative — institutional",
        "description": "System prompt for institutional in-situ visit narratives.",
        "version_label": "museum-narrative-institutional-v1",
        "content": (
            "You are an expert museum communicator specializing in institutional "
            "storytelling (formal, bureaucratic institutional reporting — focused "
            "on institutional impact, preservation, administrative completeness and "
            "compliance). Translate the provided canonical visit facts into a fluid "
            "narrative.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. You must ONLY use facts declared in the provided context. Do not "
            "invent events, people, dates or outcomes beyond these facts.\n"
            "2. Adopt the absolute tone, style and structure of the requested "
            "narrative type: institutional.\n"
            "3. If useful, mention declared evidence gaps naturally, without "
            "turning them into accusations or filling them with invented detail.\n"
            "4. Output only the narrative text, with no preamble or metadata."
        ),
    },
    {
        "template_id": "ptpl-insitu-scientific",
        "version_id": "pver-insitu-scientific-v1",
        "key": "system_scientific",
        "name": "In-situ narrative — scientific",
        "description": "System prompt for scientific in-situ visit narratives.",
        "version_label": "museum-narrative-scientific-v1",
        "content": (
            "You are an expert museum communicator specializing in scientific "
            "storytelling (rigorous, objective scientific communication — "
            "emphasising research methodology, metadata accuracy and scientific "
            "output such as publications). Translate the provided canonical visit "
            "facts into a fluid narrative.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. You must ONLY use facts declared in the provided context. Do not "
            "invent events, people, dates or outcomes beyond these facts.\n"
            "2. Adopt the absolute tone, style and structure of the requested "
            "narrative type: scientific.\n"
            "3. If useful, mention declared evidence gaps naturally, without "
            "turning them into accusations or filling them with invented detail.\n"
            "4. Output only the narrative text, with no preamble or metadata."
        ),
    },
    {
        "template_id": "ptpl-insitu-audio-adult",
        "version_id": "pver-insitu-audio-adult-v1",
        "key": "system_audioguide_adult",
        "name": "In-situ narrative — adult audioguide",
        "description": "System prompt for adult audioguide in-situ visit narratives.",
        "version_label": "museum-narrative-audioguide-adult-v1",
        "content": (
            "You are an expert museum communicator specializing in audioguide_adult "
            "storytelling (an engaging, clear museum audio-guide for general adult "
            "visitors — contextualising historical and cultural significance without "
            "heavy jargon). Translate the provided canonical visit facts into a "
            "fluid narrative.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. You must ONLY use facts declared in the provided context. Do not "
            "invent events, people, dates or outcomes beyond these facts.\n"
            "2. Adopt the absolute tone, style and structure of the requested "
            "narrative type: audioguide_adult.\n"
            "3. If useful, mention declared evidence gaps naturally, without "
            "turning them into accusations or filling them with invented detail.\n"
            "4. Output only the narrative text, with no preamble or metadata."
        ),
    },
    {
        "template_id": "ptpl-insitu-audio-child",
        "version_id": "pver-insitu-audio-child-v1",
        "key": "system_audioguide_child",
        "name": "In-situ narrative — child audioguide",
        "description": "System prompt for child audioguide in-situ visit narratives.",
        "version_label": "museum-narrative-audioguide-child-v1",
        "content": (
            "You are an expert museum communicator specializing in audioguide_child "
            "storytelling (a playful, pedagogical audio-guide for young learners — "
            "storytelling, enthusiastic, with curiosity triggers and interactive "
            "framing). Translate the provided canonical visit facts into a fluid "
            "narrative.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. You must ONLY use facts declared in the provided context. Do not "
            "invent events, people, dates or outcomes beyond these facts.\n"
            "2. Adopt the absolute tone, style and structure of the requested "
            "narrative type: audioguide_child.\n"
            "3. If useful, mention declared evidence gaps naturally, without "
            "turning them into accusations or filling them with invented detail.\n"
            "4. Output only the narrative text, with no preamble or metadata."
        ),
    },
    {
        "template_id": "ptpl-insitu-social-media",
        "version_id": "pver-insitu-social-media-v1",
        "key": "system_social_media",
        "name": "In-situ narrative — social media",
        "description": "System prompt for social-media in-situ visit narratives.",
        "version_label": "museum-narrative-social-media-v1",
        "content": (
            "You are an expert museum communicator specializing in social_media "
            "storytelling (concise, dynamic, hook-driven social-media copy — "
            "enthusiastic, with a call-to-action and native use of emojis). "
            "Translate the provided canonical visit facts into a fluid narrative.\n\n"
            "CRITICAL CONSTRAINTS:\n"
            "1. You must ONLY use facts declared in the provided context. Do not "
            "invent events, people, dates or outcomes beyond these facts.\n"
            "2. Adopt the absolute tone, style and structure of the requested "
            "narrative type: social_media.\n"
            "3. If useful, mention declared evidence gaps naturally, without "
            "turning them into accusations or filling them with invented detail.\n"
            "4. Output only the narrative text, with no preamble or metadata."
        ),
    },
]


def upgrade() -> None:
    op.create_table(
        "ai_prompt_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("variables_schema_json", sa.Text(), nullable=False),
        sa.Column("active_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "purpose", "key", name="uq_ai_prompt_templates_purpose_key"
        ),
    )
    op.create_index(
        "ix_ai_prompt_templates_purpose", "ai_prompt_templates", ["purpose"]
    )
    op.create_index("ix_ai_prompt_templates_key", "ai_prompt_templates", ["key"])
    op.create_index(
        "ix_ai_prompt_templates_created_at", "ai_prompt_templates", ["created_at"]
    )

    op.create_table(
        "ai_prompt_template_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("version_label", sa.String(length=96), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("default_temperature", sa.Float(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by", sa.String(length=128), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["ai_prompt_templates.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "version",
            name="uq_ai_prompt_template_versions_number",
        ),
        sa.UniqueConstraint(
            "template_id",
            "version_label",
            name="uq_ai_prompt_template_versions_label",
        ),
    )
    op.create_index(
        "ix_ai_prompt_template_versions_template_id",
        "ai_prompt_template_versions",
        ["template_id"],
    )
    op.create_index(
        "ix_ai_prompt_template_versions_version_label",
        "ai_prompt_template_versions",
        ["version_label"],
    )
    op.create_index(
        "ix_ai_prompt_template_versions_status",
        "ai_prompt_template_versions",
        ["status"],
    )
    op.create_index(
        "ix_ai_prompt_template_versions_created_at",
        "ai_prompt_template_versions",
        ["created_at"],
    )
    op.create_index(
        "ix_ai_prompt_template_versions_one_published",
        "ai_prompt_template_versions",
        ["template_id"],
        unique=True,
        postgresql_where=sa.text("status = 'published'"),
        sqlite_where=sa.text("status = 'published'"),
    )

    templates_table = sa.table(
        "ai_prompt_templates",
        sa.column("id", sa.String),
        sa.column("purpose", sa.String),
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("variables_schema_json", sa.Text),
        sa.column("active_version_id", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    versions_table = sa.table(
        "ai_prompt_template_versions",
        sa.column("id", sa.String),
        sa.column("template_id", sa.String),
        sa.column("version", sa.Integer),
        sa.column("version_label", sa.String),
        sa.column("status", sa.String),
        sa.column("content", sa.Text),
        sa.column("default_temperature", sa.Float),
        sa.column("created_by", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("published_by", sa.String),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("archived_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        templates_table,
        [
            {
                "id": item["template_id"],
                "purpose": "in_situ_narrative",
                "key": item["key"],
                "name": item["name"],
                "description": item["description"],
                "variables_schema_json": SCHEMA_JSON,
                "active_version_id": item["version_id"],
                "created_at": CREATED_AT,
            }
            for item in PROMPTS
        ],
    )
    op.bulk_insert(
        versions_table,
        [
            {
                "id": item["version_id"],
                "template_id": item["template_id"],
                "version": 1,
                "version_label": item["version_label"],
                "status": "published",
                "content": item["content"],
                "default_temperature": 0.3,
                "created_by": "system",
                "created_at": CREATED_AT,
                "published_by": "system",
                "published_at": CREATED_AT,
                "archived_at": None,
            }
            for item in PROMPTS
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_prompt_template_versions_one_published",
        table_name="ai_prompt_template_versions",
    )
    op.drop_index(
        "ix_ai_prompt_template_versions_created_at",
        table_name="ai_prompt_template_versions",
    )
    op.drop_index(
        "ix_ai_prompt_template_versions_status",
        table_name="ai_prompt_template_versions",
    )
    op.drop_index(
        "ix_ai_prompt_template_versions_version_label",
        table_name="ai_prompt_template_versions",
    )
    op.drop_index(
        "ix_ai_prompt_template_versions_template_id",
        table_name="ai_prompt_template_versions",
    )
    op.drop_table("ai_prompt_template_versions")
    op.drop_index("ix_ai_prompt_templates_created_at", table_name="ai_prompt_templates")
    op.drop_index("ix_ai_prompt_templates_key", table_name="ai_prompt_templates")
    op.drop_index("ix_ai_prompt_templates_purpose", table_name="ai_prompt_templates")
    op.drop_table("ai_prompt_templates")
