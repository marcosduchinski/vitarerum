"""CIDOC-CRM mapping's published language (Open Host Service).

The ONLY ``cidoc_crm`` module downstream contexts (e.g. the museum-narrative
KG-RAG pipeline) may import — enforced by import-linter. Exposes building the
CIDOC-CRM JSON-LD for a stored visit and expanding/validating that graph.
Mirrors the ``app.use_of_collections.public`` pattern (lazy infra import).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.cidoc_crm.in_situ_visit_mapping.application.cidoc.reasoning import (
    expand_graph,
    to_graph,
    to_jsonld,
    validate_graph,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.cidoc_crm.in_situ_visit_mapping.presentation.schemas import (
        InSituVisitRecordResponse,
    )

from app.cidoc_crm.in_situ_visit_mapping.application.use_cases import (
    NotInSituVisit,
    ProjectNotFound,
    VisitNotEvidenced,
)


async def export_in_situ_visit_record(
    session: AsyncSession, project_id: str
) -> InSituVisitRecordResponse:
    """Export a collection-use project into a stored in-situ visit record and
    return its published DTO.

    Raises the CIDOC export errors ``ProjectNotFound``, ``NotInSituVisit`` or
    ``VisitNotEvidenced`` unchanged for callers to map at their boundary.
    """
    from app.cidoc_crm.in_situ_visit_mapping.application.use_cases import (
        ExportInSituVisitFromProject,
        ExportInSituVisitInput,
    )
    from app.cidoc_crm.in_situ_visit_mapping.infrastructure.context_acl import (
        UseOfCollectionsExportAdapter,
    )
    from app.cidoc_crm.in_situ_visit_mapping.infrastructure.repositories import (
        SqlAlchemyInSituVisitRecordRepository,
    )
    from app.cidoc_crm.in_situ_visit_mapping.presentation.mappers import (
        record_to_response,
    )
    from app.config import settings
    from app.use_of_collections.public import get_project_export_reader

    repository = SqlAlchemyInSituVisitRecordRepository(session)
    use_case = ExportInSituVisitFromProject(
        UseOfCollectionsExportAdapter(get_project_export_reader(session)),
        repository,
        settings.institution_name,
    )
    record = await use_case.execute(ExportInSituVisitInput(project_id=project_id))
    return record_to_response(record)


async def build_in_situ_visit_cidoc(
    session: AsyncSession, record_id: str
) -> dict[str, Any] | None:
    """Map a stored ``InSituVisitRecord`` to CIDOC-CRM JSON-LD, or ``None`` if
    no record matches ``record_id``."""
    from app.cidoc_crm.in_situ_visit_mapping.application.cidoc.engine import (
        load_mapping_definition,
        map_record_to_cidoc,
    )
    from app.cidoc_crm.in_situ_visit_mapping.domain.models import InSituVisitId
    from app.cidoc_crm.in_situ_visit_mapping.infrastructure.repositories import (
        SqlAlchemyInSituVisitRecordRepository,
    )

    repository = SqlAlchemyInSituVisitRecordRepository(session)
    record = await repository.get_by_id(InSituVisitId(record_id))
    if record is None:
        return None
    return map_record_to_cidoc(record, load_mapping_definition())


async def get_in_situ_visit_record_view(
    session: AsyncSession, record_id: str
) -> InSituVisitRecordResponse | None:
    """Return the presentation DTO for a stored ``InSituVisitRecord`` (with its
    nested children and attachments), or ``None`` if no record matches."""
    from app.cidoc_crm.in_situ_visit_mapping.domain.models import InSituVisitId
    from app.cidoc_crm.in_situ_visit_mapping.infrastructure.repositories import (
        SqlAlchemyInSituVisitRecordRepository,
    )
    from app.cidoc_crm.in_situ_visit_mapping.presentation.mappers import (
        record_to_response,
    )

    repository = SqlAlchemyInSituVisitRecordRepository(session)
    record = await repository.get_by_id(InSituVisitId(record_id))
    if record is None:
        return None
    return record_to_response(record)


def expand_and_validate_cidoc(doc: dict[str, Any]) -> tuple[dict[str, Any], bool, str]:
    """Expand a CIDOC-CRM JSON-LD document (RDFS/OWL-RL closure) and validate it
    against the CIDOC-CRM shapes. Returns (expanded JSON-LD, conforms, report)."""
    graph = expand_graph(doc)
    conforms, report = validate_graph(graph)
    return to_jsonld(graph), conforms, report


def validate_cidoc(doc: dict[str, Any]) -> tuple[bool, str]:
    """Validate a CIDOC-CRM JSON-LD document against the CIDOC-CRM shapes.

    This keeps validation as the semantic gate without returning the expanded
    graph to downstream consumers such as the narrative prompt.
    """
    graph = to_graph(doc)
    return validate_graph(graph)


__all__ = [
    "build_in_situ_visit_cidoc",
    "expand_and_validate_cidoc",
    "export_in_situ_visit_record",
    "get_in_situ_visit_record_view",
    "NotInSituVisit",
    "ProjectNotFound",
    "validate_cidoc",
    "VisitNotEvidenced",
]
