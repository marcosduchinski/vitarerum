"""User Request's published language (Open Host Service).

This is the ONLY ``use_of_collections`` module downstream contexts (ProposalChat)
may import — enforced by import-linter. It exposes the read-only triage context
view, its typed read errors, and the composition factory for the SQLAlchemy
reader. Mirrors the ``app.identity.public`` pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.use_of_collections.application.context_views import (
    ConversationNotFound,
    ExportAttachmentView,
    ExportEntryView,
    ExportObjectView,
    FocusMessageView,
    MessageNotFound,
    ProjectExportReader,
    ProjectExportView,
    ProposalContextReader,
    ProposalContextView,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def get_proposal_context_reader(session: AsyncSession) -> ProposalContextReader:
    """Default composition hook: the SQLAlchemy-backed ProposalContextReader."""
    from app.use_of_collections.infrastructure.repositories import (
        SqlAlchemyProposalContextReader,
    )

    return SqlAlchemyProposalContextReader(session)


def get_project_export_reader(session: AsyncSession) -> ProjectExportReader:
    """Default composition hook: the SQLAlchemy-backed ProjectExportReader."""
    from app.use_of_collections.infrastructure.repositories import (
        SqlAlchemyProjectExportReader,
    )

    return SqlAlchemyProjectExportReader(session)


__all__ = [
    "ConversationNotFound",
    "ExportAttachmentView",
    "ExportEntryView",
    "ExportObjectView",
    "FocusMessageView",
    "MessageNotFound",
    "ProjectExportReader",
    "ProjectExportView",
    "ProposalContextReader",
    "ProposalContextView",
    "get_project_export_reader",
    "get_proposal_context_reader",
]
