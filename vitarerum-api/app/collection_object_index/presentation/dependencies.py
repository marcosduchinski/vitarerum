"""Composition root for the Collection Object Index inbound adapters.

Wires the SQLAlchemy repositories/index, the shared local-disk file storage,
the openpyxl parser and the system clock. The file storage adapter is reused
from the Use of Collections context at the composition root only (see the
import-linter ignore in pyproject.toml).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.collection_object_index.application.ports import (
    Clock,
    CollectionObjectIndexPort,
    CollectionObjectParserPort,
    CollectionRepository,
    FileStorage,
    SourceDocumentRepository,
)
from app.collection_object_index.infrastructure.clock import SystemClock
from app.collection_object_index.infrastructure.parser_openpyxl import (
    OpenpyxlCollectionObjectParser,
)
from app.collection_object_index.infrastructure.repositories import (
    SqlAlchemyCollectionObjectIndex,
    SqlAlchemyCollectionRepository,
    SqlAlchemySourceDocumentRepository,
)
from app.config import settings
from app.database import get_async_session
from app.use_of_collections.infrastructure.file_storage import LocalDiskFileStorage

DBSession = Annotated[AsyncSession, Depends(get_async_session)]

_clock = SystemClock()
_parser = OpenpyxlCollectionObjectParser()


def get_collection_repository(session: DBSession) -> CollectionRepository:
    return SqlAlchemyCollectionRepository(session)


def get_source_document_repository(session: DBSession) -> SourceDocumentRepository:
    return SqlAlchemySourceDocumentRepository(session)


def get_object_index(session: DBSession) -> CollectionObjectIndexPort:
    return SqlAlchemyCollectionObjectIndex(session)


def get_file_storage() -> FileStorage:
    return LocalDiskFileStorage(settings.data_dir)


def get_parser() -> CollectionObjectParserPort:
    return _parser


def get_clock() -> Clock:
    return _clock


CollectionRepo = Annotated[CollectionRepository, Depends(get_collection_repository)]
SourceDocumentRepo = Annotated[
    SourceDocumentRepository, Depends(get_source_document_repository)
]
ObjectIndex = Annotated[CollectionObjectIndexPort, Depends(get_object_index)]
SourceFileStorage = Annotated[FileStorage, Depends(get_file_storage)]
SourceParser = Annotated[CollectionObjectParserPort, Depends(get_parser)]
IndexClock = Annotated[Clock, Depends(get_clock)]
