"""Use of Collections' published language (Open Host Service).

This is the ONLY ``use_of_collections`` module downstream contexts (CIDOC-CRM
mapping) may import — enforced by import-linter. It exposes the read-only project
export view and the composition factory for the SQLAlchemy reader. Mirrors the
``app.identity.public`` pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.use_of_collections.application.context_views import (
    ExportAttachmentView,
    ExportEntryView,
    ExportObjectView,
    ProjectExportReader,
    ProjectExportView,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def get_project_export_reader(session: AsyncSession) -> ProjectExportReader:
    """Default composition hook: the SQLAlchemy-backed ProjectExportReader."""
    from app.use_of_collections.infrastructure.repositories import (
        SqlAlchemyProjectExportReader,
    )

    return SqlAlchemyProjectExportReader(session)


__all__ = [
    "ExportAttachmentView",
    "ExportEntryView",
    "ExportObjectView",
    "ProjectExportReader",
    "ProjectExportView",
    "get_project_export_reader",
]
