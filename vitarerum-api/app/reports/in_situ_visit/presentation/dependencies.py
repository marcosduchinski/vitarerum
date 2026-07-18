"""Composition root for the in-situ visit report inbound adapter.

Composes this context's repository with adapters that call other contexts only
through their published languages. Route handlers depend only on
``ReportUseCase``.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.reports.in_situ_visit.application.ports import InSituVisitReportRepository
from app.reports.in_situ_visit.application.use_cases import (
    GenerateInSituVisitReport,
    GetInSituVisitReport,
    GetInSituVisitReportAuditTrail,
    GetInSituVisitReportDetail,
    ListAllInSituVisitReportSummaries,
    ListInSituVisitReports,
)
from app.reports.in_situ_visit.infrastructure.readers import (
    CidocRecordExporter,
    CidocRecordReader,
    MuseumNarrativeGenerator,
    MuseumNarrativeReader,
    MuseumNarrativeRevisionReader,
)
from app.reports.in_situ_visit.infrastructure.repositories import (
    SqlAlchemyInSituVisitReportRepository,
)

DBSession = Annotated[AsyncSession, Depends(get_async_session)]


def get_repository(session: DBSession) -> InSituVisitReportRepository:
    return SqlAlchemyInSituVisitReportRepository(session)


Repository = Annotated[InSituVisitReportRepository, Depends(get_repository)]


def get_report_use_case(
    session: DBSession,
    repository: Repository,
) -> GenerateInSituVisitReport:
    return GenerateInSituVisitReport(
        CidocRecordExporter(session),
        MuseumNarrativeGenerator(session),
        repository,
    )


ReportUseCase = Annotated[GenerateInSituVisitReport, Depends(get_report_use_case)]


def get_report_by_id_use_case(repository: Repository) -> GetInSituVisitReport:
    return GetInSituVisitReport(repository)


def get_list_use_case(repository: Repository) -> ListInSituVisitReports:
    return ListInSituVisitReports(repository)


def get_list_all_use_case(
    session: DBSession, repository: Repository
) -> ListAllInSituVisitReportSummaries:
    return ListAllInSituVisitReportSummaries(repository, CidocRecordReader(session))


GetUseCase = Annotated[GetInSituVisitReport, Depends(get_report_by_id_use_case)]
ListUseCase = Annotated[ListInSituVisitReports, Depends(get_list_use_case)]
ListAllUseCase = Annotated[
    ListAllInSituVisitReportSummaries, Depends(get_list_all_use_case)
]


def get_detail_use_case(
    session: DBSession, repository: Repository
) -> GetInSituVisitReportDetail:
    return GetInSituVisitReportDetail(
        repository,
        CidocRecordReader(session),
        MuseumNarrativeReader(session),
    )


DetailUseCase = Annotated[GetInSituVisitReportDetail, Depends(get_detail_use_case)]


def get_audit_trail_use_case(
    session: DBSession, repository: Repository
) -> GetInSituVisitReportAuditTrail:
    return GetInSituVisitReportAuditTrail(
        repository,
        CidocRecordReader(session),
        MuseumNarrativeReader(session),
        MuseumNarrativeRevisionReader(session),
    )


AuditTrailUseCase = Annotated[
    GetInSituVisitReportAuditTrail, Depends(get_audit_trail_use_case)
]
