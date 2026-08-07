"""Composition root for the Document Templates inbound adapters.

Wires the SQLAlchemy repository, the shared file storage and the system clock.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_session
from app.document_templates.application.ports import (
    DocumentTemplateRepository,
    FileStorage,
)
from app.document_templates.infrastructure.clock import SystemClock
from app.document_templates.infrastructure.repositories import (
    SqlAlchemyDocumentTemplateRepository,
)
from app.shared.file_storage import build_file_storage

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

_clock = SystemClock()


def get_repository(session: DBSession) -> DocumentTemplateRepository:
    return SqlAlchemyDocumentTemplateRepository(session)


def get_file_storage() -> FileStorage:
    return build_file_storage(settings.data_dir, settings.file_encryption_key)


def get_clock() -> SystemClock:
    return _clock


TemplateRepo = Annotated[DocumentTemplateRepository, Depends(get_repository)]
TemplateFileStorage = Annotated[FileStorage, Depends(get_file_storage)]
TemplateClock = Annotated[SystemClock, Depends(get_clock)]
