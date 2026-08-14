from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_session
from app.identity.public import get_permission_reader
from app.scientific_return.application.ports import (
    BibliographicSource,
    ConfirmedPublicationWriter,
    ProjectSnapshotProvider,
    ScientificReturnRepository,
)
from app.scientific_return.infrastructure.acls import (
    UseOfCollectionsProjectSnapshotProvider,
    UseOfCollectionsPublicationWriter,
)
from app.scientific_return.infrastructure.crossref import CrossrefBibliographicSource
from app.scientific_return.infrastructure.repositories import (
    SqlAlchemyScientificReturnRepository,
)
from app.shared.field_encryption import FieldEncryptor
from app.use_of_collections.public import (
    get_published_publication_entry_writer,
    get_published_use_of_collections_reader,
)

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def _field_encryptor() -> FieldEncryptor:
    return FieldEncryptor.from_base64(settings.db_field_encryption_key)


def get_repository(session: DBSession) -> ScientificReturnRepository:
    return SqlAlchemyScientificReturnRepository(session, _field_encryptor())


def get_project_provider(session: DBSession) -> ProjectSnapshotProvider:
    return UseOfCollectionsProjectSnapshotProvider(
        get_published_use_of_collections_reader(session),
        get_permission_reader(session),
    )


def get_publication_writer(session: DBSession) -> ConfirmedPublicationWriter:
    return UseOfCollectionsPublicationWriter(
        get_published_publication_entry_writer(session)
    )


def get_bibliographic_sources() -> tuple[BibliographicSource, ...]:
    return (
        CrossrefBibliographicSource(
            base_url=settings.crossref_base_url,
            timeout_seconds=settings.crossref_timeout_seconds,
            mailto=settings.crossref_mailto or None,
            max_retries=settings.crossref_max_retries,
            retry_base_seconds=settings.crossref_retry_base_seconds,
            min_interval_seconds=settings.crossref_min_interval_seconds,
        ),
    )


def get_result_limit() -> int:
    return settings.scientific_return_result_limit


def get_max_queries() -> int:
    return settings.scientific_return_max_queries_per_run


Repository = Annotated[ScientificReturnRepository, Depends(get_repository)]
ProjectProvider = Annotated[ProjectSnapshotProvider, Depends(get_project_provider)]
PublicationWriter = Annotated[
    ConfirmedPublicationWriter, Depends(get_publication_writer)
]
BibliographicSources = Annotated[
    tuple[BibliographicSource, ...], Depends(get_bibliographic_sources)
]
ResultLimit = Annotated[int, Depends(get_result_limit)]
MaxQueries = Annotated[int, Depends(get_max_queries)]
