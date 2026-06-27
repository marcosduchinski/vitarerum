"""SQLAlchemy repository for the in-situ visit report aggregate.

Append-only: each report is one row. ``add`` flushes so the row participates in
the route's single end-of-request commit alongside the exported record and the
generated narrative.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.reports.in_situ_visit.domain.models import (
    InSituVisitReport,
    InSituVisitReportId,
)
from app.reports.in_situ_visit.infrastructure.models import InSituVisitReportOrm
from app.shared.kernel import PermissionId


def report_to_orm(report: InSituVisitReport) -> InSituVisitReportOrm:
    return InSituVisitReportOrm(
        id=report.id,
        created_at=report.created_at,
        created_by=report.created_by,
        project_id=report.project_id,
        narrative_id=report.narrative_id,
        in_situ_visit_record_id=report.in_situ_visit_record_id,
    )


def report_to_domain(orm: InSituVisitReportOrm) -> InSituVisitReport:
    return InSituVisitReport(
        id=InSituVisitReportId(orm.id),
        created_at=orm.created_at,
        created_by=PermissionId(orm.created_by),
        project_id=orm.project_id,
        narrative_id=orm.narrative_id,
        in_situ_visit_record_id=orm.in_situ_visit_record_id,
    )


class SqlAlchemyInSituVisitReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, report: InSituVisitReport) -> None:
        self._session.add(report_to_orm(report))
        await self._session.flush()

    async def get_by_id(
        self, report_id: InSituVisitReportId
    ) -> InSituVisitReport | None:
        stmt = select(InSituVisitReportOrm).where(InSituVisitReportOrm.id == report_id)
        orm = (await self._session.execute(stmt)).scalar_one_or_none()
        return report_to_domain(orm) if orm else None

    async def list_by_project(
        self, project_id: str, page: int, size: int
    ) -> tuple[list[InSituVisitReport], int]:
        count_stmt = (
            select(func.count())
            .select_from(InSituVisitReportOrm)
            .where(InSituVisitReportOrm.project_id == project_id)
        )
        total = (await self._session.execute(count_stmt)).scalar_one()
        data_stmt = (
            select(InSituVisitReportOrm)
            .where(InSituVisitReportOrm.project_id == project_id)
            .order_by(InSituVisitReportOrm.created_at.desc())
            .offset(page * size)
            .limit(size)
        )
        orms = (await self._session.execute(data_stmt)).scalars().all()
        return [report_to_domain(orm) for orm in orms], total

    async def list_all(
        self, page: int, size: int
    ) -> tuple[list[InSituVisitReport], int]:
        count_stmt = select(func.count()).select_from(InSituVisitReportOrm)
        total = (await self._session.execute(count_stmt)).scalar_one()
        data_stmt = (
            select(InSituVisitReportOrm)
            .order_by(InSituVisitReportOrm.created_at.desc())
            .offset(page * size)
            .limit(size)
        )
        orms = (await self._session.execute(data_stmt)).scalars().all()
        return [report_to_domain(orm) for orm in orms], total
