from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.scientific_return.application.ports import BibliographicRecord
from app.scientific_return.domain.enums import (
    EvidenceStrength,
    EvidenceType,
    QueryType,
)
from app.scientific_return.domain.models import (
    CandidateEvidence,
    CandidateEvidenceId,
    CandidatePublicationId,
    ProjectSnapshotPayload,
)


@dataclass(frozen=True, slots=True)
class PlannedQuery:
    query_type: QueryType
    text: str


def _query_term(value: str) -> str:
    return f'"{value.strip()}"'


def plan_queries(snapshot: ProjectSnapshotPayload) -> tuple[PlannedQuery, ...]:
    planned: list[PlannedQuery] = []
    for obj in snapshot.consulted_objects:
        inventory = obj.inventory_number.strip()
        object_name = obj.object_name.strip()
        researcher = snapshot.researcher.strip()
        planned.append(PlannedQuery(QueryType.INVENTORY, _query_term(inventory)))
        planned.append(
            PlannedQuery(
                QueryType.AUTHOR_INVENTORY,
                f"{_query_term(researcher)} {_query_term(inventory)}",
            )
        )
        planned.append(
            PlannedQuery(
                QueryType.INVENTORY_OBJECT,
                f"{_query_term(inventory)} {_query_term(object_name)}",
            )
        )
        planned.append(
            PlannedQuery(
                QueryType.AUTHOR_OBJECT,
                f"{_query_term(researcher)} {_query_term(object_name)}",
            )
        )
    return tuple(dict.fromkeys(planned))


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^\w]+", " ", value.casefold())
    return re.sub(r"\s+", " ", value).strip()


def _compact_inventory(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]", "", value.upper())
    normalized = normalized.replace("MUNHAC", "MUHNAC")
    return re.sub(r"(MB\d{2})\1", r"\1", normalized)


def _record_text(record: BibliographicRecord) -> str:
    return " ".join(
        part
        for part in (
            record.title,
            " ".join(record.authors),
            record.abstract or "",
        )
        if part
    )


def _author_matches(researcher: str, authors: tuple[str, ...]) -> bool:
    researcher_tokens = set(_plain(researcher).split())
    if not researcher_tokens:
        return False
    return any(researcher_tokens <= set(_plain(author).split()) for author in authors)


def build_evidences(
    candidate_id: CandidatePublicationId,
    snapshot: ProjectSnapshotPayload,
    record: BibliographicRecord,
    created_at: datetime,
) -> list[CandidateEvidence]:
    text = _record_text(record)
    plain_text = _plain(text)
    compact_text = _compact_inventory(text)
    author_match = _author_matches(snapshot.researcher, record.authors)
    evidences: list[CandidateEvidence] = []

    def add(
        evidence_type: EvidenceType,
        strength: EvidenceStrength,
        value: str,
        source_field: str,
        explanation: str,
    ) -> None:
        evidences.append(
            CandidateEvidence(
                id=CandidateEvidenceId(str(uuid4())),
                candidate_id=candidate_id,
                type=evidence_type,
                strength=strength,
                value=value,
                source_field=source_field,
                explanation=explanation,
                created_at=created_at,
            )
        )

    if author_match:
        add(
            EvidenceType.AUTHOR,
            EvidenceStrength.SUPPORTING,
            snapshot.researcher,
            "authors",
            "A lista de autores coincide com o investigador do projeto.",
        )

    for obj in snapshot.consulted_objects:
        inventory_match = _compact_inventory(obj.inventory_number) in compact_text
        object_match = _plain(obj.object_name) in plain_text
        if inventory_match:
            add(
                EvidenceType.INVENTORY_NUMBER,
                EvidenceStrength.PRIMARY,
                obj.inventory_number,
                "title_or_abstract",
                "O registo bibliografico menciona o numero de inventario consultado.",
            )
        if object_match:
            add(
                EvidenceType.OBJECT_NAME,
                EvidenceStrength.SUPPORTING,
                obj.object_name,
                "title_or_abstract",
                "O titulo ou resumo menciona o objeto consultado.",
            )
        if author_match and inventory_match:
            add(
                EvidenceType.AUTHOR_INVENTORY,
                EvidenceStrength.PRIMARY,
                f"{snapshot.researcher} | {obj.inventory_number}",
                "authors+title_or_abstract",
                "Autor e numero de inventario coincidem no mesmo candidato.",
            )
        if inventory_match and object_match:
            add(
                EvidenceType.INVENTORY_OBJECT,
                EvidenceStrength.PRIMARY,
                f"{obj.inventory_number} | {obj.object_name}",
                "title_or_abstract",
                "Numero de inventario e objeto coincidem no mesmo candidato.",
            )
        if author_match and object_match:
            add(
                EvidenceType.AUTHOR_OBJECT,
                EvidenceStrength.SUPPORTING,
                f"{snapshot.researcher} | {obj.object_name}",
                "authors+title_or_abstract",
                "Autor e objeto coincidem no mesmo candidato.",
            )
    return evidences


def deduplication_key(record: BibliographicRecord) -> str:
    if record.doi:
        return f"doi:{record.doi.casefold().removeprefix('https://doi.org/')}"
    first_author = _plain(record.authors[0]) if record.authors else ""
    basis = f"{_plain(record.title)}|{record.publication_date or ''}|{first_author}"
    return f"metadata:{hashlib.sha256(basis.encode()).hexdigest()}"


def is_actionable(evidences: list[CandidateEvidence]) -> bool:
    types = {evidence.type for evidence in evidences}
    return bool(
        types
        & {
            EvidenceType.INVENTORY_NUMBER,
            EvidenceType.AUTHOR_INVENTORY,
            EvidenceType.INVENTORY_OBJECT,
            EvidenceType.AUTHOR_OBJECT,
        }
    )
