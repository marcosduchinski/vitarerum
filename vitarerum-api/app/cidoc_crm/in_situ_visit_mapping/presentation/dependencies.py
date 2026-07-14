"""Composition root for the In Situ Visit CIDOC mapping inbound adapter.

Wires the SQLAlchemy repository to the two application use cases. Route handlers
depend only on the ``Annotated`` aliases exported here.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.cidoc_crm.in_situ_visit_mapping.application.ports import (
    InSituVisitRecordRepository,
    ProjectExportPort,
)
from app.cidoc_crm.in_situ_visit_mapping.application.use_cases import (
    BuildInSituVisitCidoc,
    ExportInSituVisitFromProject,
    ListInSituVisits,
    RecordInSituVisit,
)
from app.cidoc_crm.in_situ_visit_mapping.infrastructure.context_acl import (
    UseOfCollectionsExportAdapter,
)
from app.cidoc_crm.in_situ_visit_mapping.infrastructure.repositories import (
    SqlAlchemyInSituVisitRecordRepository,
)
from app.config import settings
from app.database import get_async_session
from app.use_of_collections.public import get_project_export_reader

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def get_repository(session: DBSession) -> InSituVisitRecordRepository:
    return SqlAlchemyInSituVisitRecordRepository(session)


Repository = Annotated[InSituVisitRecordRepository, Depends(get_repository)]


def get_export_port(session: DBSession) -> ProjectExportPort:
    return UseOfCollectionsExportAdapter(get_project_export_reader(session))


ExportPort = Annotated[ProjectExportPort, Depends(get_export_port)]


def get_record_use_case(repository: Repository) -> RecordInSituVisit:
    return RecordInSituVisit(repository)


def get_list_use_case(repository: Repository) -> ListInSituVisits:
    return ListInSituVisits(repository)


def get_cidoc_use_case(repository: Repository) -> BuildInSituVisitCidoc:
    return BuildInSituVisitCidoc(repository)


def get_export_use_case(
    export_port: ExportPort, repository: Repository
) -> ExportInSituVisitFromProject:
    return ExportInSituVisitFromProject(
        export_port, repository, settings.institution_name
    )


RecordUseCase = Annotated[RecordInSituVisit, Depends(get_record_use_case)]
ListUseCase = Annotated[ListInSituVisits, Depends(get_list_use_case)]
CidocUseCase = Annotated[BuildInSituVisitCidoc, Depends(get_cidoc_use_case)]
ExportUseCase = Annotated[ExportInSituVisitFromProject, Depends(get_export_use_case)]
