"""Composition root for the Collection Object Index inbound adapters.

Wires the SQLAlchemy repositories/index, the shared file storage, the openpyxl
parser and the system clock.
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
from app.shared.file_storage import build_file_storage

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
    return build_file_storage(settings.data_dir, settings.file_encryption_key)


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
