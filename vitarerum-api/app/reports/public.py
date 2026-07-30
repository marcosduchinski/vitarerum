"""Reports published language for downstream contexts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import column, func, or_, select, table

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True)
class PublishedNarrativeView:
    id: str
    text: str


@dataclass(slots=True)
class PublishedInSituVisitCidocView:
    record_id: str
    json_ld: dict[str, Any] | None
    conforms: bool | None
    mapping_version: str | None
    crm_version: str | None


@dataclass(slots=True)
class PublishedInSituVisitReportView:
    id: str
    project_id: str
    created_at: datetime
    code: str | None
    visitor_name: str | None
    place_name: str | None
    visit_begin_date: date | None
    visit_end_date: date | None
    narrative: PublishedNarrativeView | None
    cidoc: PublishedInSituVisitCidocView


@dataclass(slots=True)
class PublishableInSituVisitReportView:
    id: str
    reference: str | None
    title: str | None
    status: str | None
    subtitle: str | None = None


class PublishedInSituVisitReportReader:
    def __init__(self, session: AsyncSession) -> None:
        from app.reports.in_situ_visit.infrastructure.readers import (
            CidocRecordReader,
            MuseumNarrativeReader,
        )
        from app.reports.in_situ_visit.infrastructure.repositories import (
            SqlAlchemyInSituVisitReportRepository,
        )

        self._session = session
        self._repo = SqlAlchemyInSituVisitReportRepository(session)
        self._record_reader = CidocRecordReader(session)
        self._narrative_reader = MuseumNarrativeReader(session)

    async def get(self, report_id: str) -> PublishedInSituVisitReportView | None:
        from app.reports.in_situ_visit.domain.models import InSituVisitReportId

        report = await self._repo.get_by_id(InSituVisitReportId(report_id))
        if report is None:
            return None
        record = await self._record_reader.get(report.in_situ_visit_record_id)
        narrative = await self._narrative_reader.get(
            report.in_situ_visit_record_id,
            report.narrative_id,
        )
        if record is None:
            return None
        json_ld = _json_ld_from_narrative_snapshot(narrative)
        return PublishedInSituVisitReportView(
            id=report.id,
            project_id=report.project_id,
            created_at=report.created_at,
            code=record.code,
            visitor_name=record.visitorName,
            place_name=record.placeName,
            visit_begin_date=record.visitBeginDate,
            visit_end_date=record.visitEndDate,
            narrative=(
                PublishedNarrativeView(
                    id=narrative.narrative_id,
                    text=narrative.data.narrative,
                )
                if narrative is not None
                else None
            ),
            cidoc=PublishedInSituVisitCidocView(
                record_id=report.in_situ_visit_record_id,
                json_ld=json_ld,
                conforms=(
                    narrative.facts_snapshot.cidoc_conforms
                    if narrative is not None and narrative.facts_snapshot is not None
                    else None
                ),
                mapping_version=record.mappingVersion,
                crm_version=record.crmVersion,
            ),
        )

    async def get_json_ld(self, report_id: str) -> dict[str, Any] | None:
        report = await self.get(report_id)
        if report is None:
            return None
        if report.cidoc.json_ld is not None:
            return report.cidoc.json_ld
        from app.cidoc_crm.public import build_in_situ_visit_cidoc

        return await build_in_situ_visit_cidoc(self._session, report.cidoc.record_id)

    async def list_publishable(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableInSituVisitReportView], int]:
        base_stmt = _publishable_reports_stmt(q)
        total = (
            await self._session.execute(
                select(func.count()).select_from(base_stmt.subquery())
            )
        ).scalar_one()
        data_stmt = (
            base_stmt.order_by(_REPORTS.c.created_at.desc(), _REPORTS.c.id.asc())
            .offset(page * size)
            .limit(size)
        )
        rows = (await self._session.execute(data_stmt)).all()
        return [
            PublishableInSituVisitReportView(
                id=row.report_id,
                reference=row.code,
                title=row.visitor_name,
                status="CIDOC_CONFORMANT",
                subtitle=row.place_name,
            )
            for row in rows
        ], total


def _json_ld_from_narrative_snapshot(narrative: Any | None) -> dict[str, Any] | None:
    if narrative is None or narrative.facts_snapshot is None:
        return None
    raw = narrative.facts_snapshot.cidoc_document_json
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


# This published-language query deliberately uses physical table/column names
# instead of the neighboring CIDOC/narrative ORMs. The picker needs a paginated,
# searchable, CIDOC-conformant report list; composing the existing public
# readers would reintroduce a full scan plus N+1 queries on every search term.
# Keep these names in sync with the three source ORMs when their schemas change:
# InSituVisitReportOrm, InSituVisitRecordOrm, GeneratedNarrativeOrm, and
# NarrativeFactSnapshotOrm.
_REPORTS = table(
    "in_situ_visit_reports",
    column("id"),
    column("created_at"),
    column("project_id"),
    column("narrative_id"),
    column("in_situ_visit_record_id"),
)
_RECORDS = table(
    "in_situ_visit_records",
    column("id"),
    column("code"),
    column("visitor_name"),
    column("place_name"),
)
_NARRATIVES = table(
    "generated_narratives",
    column("id"),
    column("facts_snapshot_id"),
)
_SNAPSHOTS = table(
    "narrative_fact_snapshots",
    column("id"),
    column("cidoc_conforms"),
)


def _publishable_reports_stmt(q: str | None) -> Any:
    stmt = (
        select(
            _REPORTS.c.id.label("report_id"),
            _REPORTS.c.created_at,
            _RECORDS.c.code,
            _RECORDS.c.visitor_name,
            _RECORDS.c.place_name,
        )
        .select_from(
            _REPORTS.join(
                _RECORDS,
                _RECORDS.c.id == _REPORTS.c.in_situ_visit_record_id,
            )
            .join(_NARRATIVES, _NARRATIVES.c.id == _REPORTS.c.narrative_id)
            .join(_SNAPSHOTS, _SNAPSHOTS.c.id == _NARRATIVES.c.facts_snapshot_id)
        )
        .where(_SNAPSHOTS.c.cidoc_conforms.is_(True))
    )
    if not q:
        return stmt
    pattern = f"%{q}%"
    return stmt.where(
        or_(
            _REPORTS.c.id.ilike(pattern),
            _REPORTS.c.project_id.ilike(pattern),
            _REPORTS.c.in_situ_visit_record_id.ilike(pattern),
            _RECORDS.c.code.ilike(pattern),
            _RECORDS.c.visitor_name.ilike(pattern),
            _RECORDS.c.place_name.ilike(pattern),
        )
    )


def get_published_in_situ_visit_report_reader(
    session: AsyncSession,
) -> PublishedInSituVisitReportReader:
    return PublishedInSituVisitReportReader(session)


__all__ = [
    "PublishedInSituVisitCidocView",
    "PublishedInSituVisitReportReader",
    "PublishedInSituVisitReportView",
    "PublishedNarrativeView",
    "PublishableInSituVisitReportView",
    "get_published_in_situ_visit_report_reader",
]
