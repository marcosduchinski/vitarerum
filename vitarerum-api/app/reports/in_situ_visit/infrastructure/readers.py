"""Adapters that call other contexts through their published languages.

These implement the application's ports by delegating to
``app.cidoc_crm.public`` and ``app.ai.museum_narrative.public`` (the only doors
into those contexts). The OHS imports are function-level, mirroring the lazy
composition used by the public modules themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.kernel import PermissionId

if TYPE_CHECKING:
    from app.ai.museum_narrative.presentation.schemas import (
        PaginatedNarrativeRevisionsResponse,
        StoredNarrativeResponse,
    )
    from app.cidoc_crm.in_situ_visit_mapping.presentation.schemas import (
        InSituVisitRecordResponse,
    )


class CidocRecordReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, record_id: str) -> InSituVisitRecordResponse | None:
        from app.cidoc_crm.public import get_in_situ_visit_record_view

        return await get_in_situ_visit_record_view(self._session, record_id)


class CidocRecordExporter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def export(self, project_id: str) -> InSituVisitRecordResponse:
        from app.cidoc_crm.public import export_in_situ_visit_record

        return await export_in_situ_visit_record(self._session, project_id)


class MuseumNarrativeReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, record_id: str, narrative_id: str
    ) -> StoredNarrativeResponse | None:
        from app.ai.museum_narrative.public import get_narrative_view

        return await get_narrative_view(self._session, record_id, narrative_id)


class MuseumNarrativeDeleter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def delete(self, record_id: str, narrative_id: str) -> bool:
        from app.ai.museum_narrative.public import delete_narrative

        return await delete_narrative(self._session, record_id, narrative_id)


class ExternalPublicationRevoker:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def revoke_for_report(self, report_id: str, revoked_by: PermissionId) -> int:
        from app.external_publications.public import (
            ExternalPublicationResourceType,
            revoke_publications_for_resource,
        )

        return await revoke_publications_for_resource(
            self._session,
            resource_type=ExternalPublicationResourceType.IN_SITU_VISIT_REPORT,
            resource_id=report_id,
            revoked_by=revoked_by,
        )


class MuseumNarrativeRevisionReader:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self, record_id: str, narrative_id: str, page: int, size: int
    ) -> PaginatedNarrativeRevisionsResponse | None:
        from app.ai.museum_narrative.public import list_narrative_revisions

        return await list_narrative_revisions(
            self._session, record_id, narrative_id, page, size
        )


class MuseumNarrativeGenerator:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def generate(
        self,
        record_id: str,
        *,
        narrative_type: str | None,
        target_language: str,
        creativity_temperature: float,
    ) -> StoredNarrativeResponse:
        from app.ai.museum_narrative.public import (
            NarrativeGenerationOptions,
            generate_narrative,
        )

        return await generate_narrative(
            self._session,
            record_id,
            NarrativeGenerationOptions(
                narrative_type=narrative_type,
                target_language=target_language,
                creativity_temperature=creativity_temperature,
            ),
        )
