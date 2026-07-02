"""Composition root for the Document Templates inbound adapters.

Wires the SQLAlchemy repository, the shared local-disk file storage and the
system clock. The file storage is reused from the Use of Collections context at
the composition root only (see the import-linter ignore in pyproject.toml).
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
from app.use_of_collections.infrastructure.file_storage import LocalDiskFileStorage

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

_clock = SystemClock()


def get_repository(session: DBSession) -> DocumentTemplateRepository:
    return SqlAlchemyDocumentTemplateRepository(session)


def get_file_storage() -> FileStorage:
    return LocalDiskFileStorage(settings.data_dir)


def get_clock() -> SystemClock:
    return _clock


TemplateRepo = Annotated[DocumentTemplateRepository, Depends(get_repository)]
TemplateFileStorage = Annotated[FileStorage, Depends(get_file_storage)]
TemplateClock = Annotated[SystemClock, Depends(get_clock)]
