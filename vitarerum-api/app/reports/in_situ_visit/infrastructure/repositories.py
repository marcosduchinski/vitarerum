"""SQLAlchemy repository for the in-situ visit report aggregate.

Each report is one linkage row. ``add`` / ``delete`` flush so the row
participates in the route's single end-of-request commit alongside the generated
narrative artifacts.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_narrative.infrastructure.models import GeneratedNarrativeOrm
from app.cidoc_crm.in_situ_visit_mapping.infrastructure.models import (
    InSituVisitRecordOrm,
)
from app.reports.in_situ_visit.application.ports import InSituVisitReportFilters
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
        self,
        page: int,
        size: int,
        filters: InSituVisitReportFilters | None = None,
    ) -> tuple[list[InSituVisitReport], int]:
        criteria = self._list_all_criteria(filters)
        base_from = InSituVisitReportOrm.__table__.outerjoin(
            InSituVisitRecordOrm.__table__,
            InSituVisitRecordOrm.id == InSituVisitReportOrm.in_situ_visit_record_id,
        ).outerjoin(
            GeneratedNarrativeOrm.__table__,
            and_(
                GeneratedNarrativeOrm.id == InSituVisitReportOrm.narrative_id,
                GeneratedNarrativeOrm.record_id
                == InSituVisitReportOrm.in_situ_visit_record_id,
            ),
        )
        count_stmt = select(func.count()).select_from(base_from).where(*criteria)
        total = (await self._session.execute(count_stmt)).scalar_one()
        data_stmt = (
            select(InSituVisitReportOrm)
            .select_from(base_from)
            .where(*criteria)
            .order_by(InSituVisitReportOrm.created_at.desc(), InSituVisitReportOrm.id)
            .offset(page * size)
            .limit(size)
        )
        orms = (await self._session.execute(data_stmt)).scalars().all()
        return [report_to_domain(orm) for orm in orms], total

    async def delete(self, report_id: InSituVisitReportId) -> bool:
        orm = await self._session.get(InSituVisitReportOrm, report_id)
        if orm is None:
            return False
        await self._session.delete(orm)
        await self._session.flush()
        return True

    def _list_all_criteria(self, filters: InSituVisitReportFilters | None) -> list[Any]:
        if filters is None:
            return []

        criteria: list[object] = []
        search = filters.search.strip().lower() if filters.search else ""
        if search:
            pattern = f"%{search}%"
            criteria.append(
                or_(
                    func.lower(InSituVisitReportOrm.id).like(pattern),
                    func.lower(InSituVisitReportOrm.project_id).like(pattern),
                    func.lower(InSituVisitReportOrm.narrative_id).like(pattern),
                    func.lower(InSituVisitReportOrm.in_situ_visit_record_id).like(
                        pattern
                    ),
                    func.lower(InSituVisitRecordOrm.code).like(pattern),
                    func.lower(InSituVisitRecordOrm.visitor_name).like(pattern),
                    func.lower(InSituVisitRecordOrm.place_name).like(pattern),
                    func.lower(InSituVisitRecordOrm.project_title).like(pattern),
                )
            )
        if filters.generated_from:
            criteria.append(InSituVisitReportOrm.created_at >= filters.generated_from)
        if filters.generated_to:
            criteria.append(InSituVisitReportOrm.created_at <= filters.generated_to)
        if filters.visit_from:
            criteria.append(InSituVisitRecordOrm.visit_end_date >= filters.visit_from)
        if filters.visit_to:
            criteria.append(InSituVisitRecordOrm.visit_begin_date <= filters.visit_to)
        if filters.narrative_type:
            criteria.append(
                GeneratedNarrativeOrm.narrative_type == filters.narrative_type
            )
        return criteria
