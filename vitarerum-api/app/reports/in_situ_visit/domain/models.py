"""Domain model for the In-Situ Visit Report context.

An ``InSituVisitReport`` is a thin linkage aggregate: it ties a collection-use
project to the CIDOC-CRM record exported from it and the narrative generated from
that record. It owns no facts of its own — the record and narrative live in their
own contexts — so the cross-context references are kept as plain ids (no FK).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NewType

from app.shared.kernel import PermissionId

InSituVisitReportId = NewType("InSituVisitReportId", str)


@dataclass(slots=True)
class InSituVisitReport:
    """One report tying a project to its exported record and generated narrative.

    Append-only: a fresh report is created on every generation. The
    ``*_id`` references point at aggregates owned by other contexts and are held
    as plain strings (no cross-context foreign keys)."""

    id: InSituVisitReportId
    created_at: datetime
    created_by: PermissionId
    project_id: str
    narrative_id: str
    in_situ_visit_record_id: str

    @classmethod
    def create(
        cls,
        *,
        created_by: PermissionId,
        project_id: str,
        narrative_id: str,
        in_situ_visit_record_id: str,
    ) -> InSituVisitReport:
        """Build a fresh report, assigning the id and stamping ``created_at``."""
        return cls(
            id=InSituVisitReportId(str(uuid.uuid4())),
            created_at=datetime.now(UTC),
            created_by=created_by,
            project_id=project_id,
            narrative_id=narrative_id,
            in_situ_visit_record_id=in_situ_visit_record_id,
        )
