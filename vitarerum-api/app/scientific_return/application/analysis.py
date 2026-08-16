from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable
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


def plan_adaptive_queries(snapshot: ProjectSnapshotPayload) -> tuple[PlannedQuery, ...]:
    """Broaden only the object term after the exact trajectories find nothing."""
    planned: list[PlannedQuery] = []
    for obj in snapshot.consulted_objects:
        genus = obj.object_name.strip().split()[0]
        if genus.casefold() == obj.object_name.strip().casefold():
            continue
        planned.append(
            PlannedQuery(
                QueryType.INVENTORY_OBJECT,
                f"{_query_term(obj.inventory_number)} {_query_term(genus)}",
            )
        )
        planned.append(
            PlannedQuery(
                QueryType.AUTHOR_OBJECT,
                f"{_query_term(snapshot.researcher)} {_query_term(genus)}",
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


def _inventory_variants(value: str) -> tuple[str, ...]:
    compact = _compact_inventory(value)
    collection_code = re.search(r"MB\d{2}[A-Z0-9]*", compact)
    variants = [compact]
    if collection_code and collection_code.group() != compact:
        variants.append(collection_code.group())
    return tuple(variants)


def _metadata_text(record: BibliographicRecord) -> str:
    return " ".join(
        part
        for part in (
            record.title,
            " ".join(record.authors),
            record.abstract or "",
        )
        if part
    )


def _matching_source(
    record: BibliographicRecord,
    value: str,
    *,
    normalizer: Callable[[str], str],
) -> str | None:
    if value in normalizer(_metadata_text(record)):
        return "title_or_abstract"
    if record.indexed_text and value in normalizer(record.indexed_text):
        return record.indexed_text_source or "indexed_text"
    return None


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
    author_match = _author_matches(snapshot.researcher, record.authors)
    evidences: list[CandidateEvidence] = []

    def add(
        evidence_type: EvidenceType,
        strength: EvidenceStrength,
        value: str,
        source_field: str,
        explanation: str,
        object_id: str | None = None,
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
                object_id=object_id,
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
        inventory_source = next(
            (
                source
                for variant in _inventory_variants(obj.inventory_number)
                if (
                    source := _matching_source(
                        record,
                        variant,
                        normalizer=_compact_inventory,
                    )
                )
                is not None
            ),
            None,
        )
        inventory_match = inventory_source is not None
        normalized_object = _plain(obj.object_name)
        exact_object_source = _matching_source(
            record,
            normalized_object,
            normalizer=_plain,
        )
        exact_object_match = exact_object_source is not None
        genus = normalized_object.split()[0] if normalized_object else ""
        genus_source = (
            _matching_source(record, genus, normalizer=_plain)
            if genus and " " in normalized_object
            else None
        )
        genus_match = genus_source is not None
        object_match = exact_object_match or genus_match
        object_source = exact_object_source or genus_source
        if inventory_match:
            add(
                EvidenceType.INVENTORY_NUMBER,
                EvidenceStrength.PRIMARY,
                obj.inventory_number,
                inventory_source or "indexed_text",
                "O registo bibliografico menciona o numero de inventario consultado.",
                obj.id,
            )
        if object_match:
            add(
                EvidenceType.OBJECT_NAME,
                (
                    EvidenceStrength.SUPPORTING
                    if exact_object_match
                    else EvidenceStrength.WEAK
                ),
                obj.object_name,
                object_source or "indexed_text",
                (
                    "O titulo ou resumo menciona o objeto consultado."
                    if exact_object_match
                    else "O titulo ou resumo menciona o genero do taxon consultado."
                ),
                obj.id,
            )
        if author_match and inventory_match:
            add(
                EvidenceType.AUTHOR_INVENTORY,
                EvidenceStrength.PRIMARY,
                f"{snapshot.researcher} | {obj.inventory_number}",
                f"authors+{inventory_source or 'indexed_text'}",
                "Autor e numero de inventario coincidem no mesmo candidato.",
                obj.id,
            )
        if inventory_match and object_match:
            add(
                EvidenceType.INVENTORY_OBJECT,
                EvidenceStrength.PRIMARY,
                f"{obj.inventory_number} | {obj.object_name}",
                "+".join(
                    dict.fromkeys(
                        (
                            inventory_source or "indexed_text",
                            object_source or "indexed_text",
                        )
                    )
                ),
                "Numero de inventario e objeto coincidem no mesmo candidato.",
                obj.id,
            )
        if author_match and object_match:
            add(
                EvidenceType.AUTHOR_OBJECT,
                EvidenceStrength.SUPPORTING,
                (
                    f"{snapshot.researcher} | "
                    f"{obj.object_name if exact_object_match else genus}"
                ),
                f"authors+{object_source or 'indexed_text'}",
                (
                    "Autor e objeto coincidem no mesmo candidato."
                    if exact_object_match
                    else "Autor e genero do taxon coincidem no mesmo candidato."
                ),
                obj.id,
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
