from __future__ import annotations

from app.scientific_return.application.ports import BibliographicSourceCapabilities
from app.scientific_return.domain.enums import SearchIntent, SearchStrategy
from app.scientific_return.domain.full_agentic_models import AgenticSearchSpec
from app.scientific_return.domain.inventory_variants import (
    generate_inventory_query_variants,
)
from app.scientific_return.domain.models import ProjectSnapshotPayload

_SURNAME_PARTICLES = frozenset(
    {"da", "das", "de", "do", "dos", "e", "van", "von", "del", "della"}
)


def bibliographic_surname_hypotheses(full_name: str) -> tuple[str, ...]:
    words = tuple(part.strip(".,") for part in full_name.split() if part.strip(".,"))
    if not words:
        return ()
    last = words[-1]
    hypotheses = [last]
    if len(words) >= 2 and words[-2].casefold() in _SURNAME_PARTICLES:
        hypotheses.insert(0, f"{words[-2]} {last}")
    elif len(words) >= 3 and len(words[-2].rstrip(".")) > 1:
        hypotheses.insert(0, f"{words[-2]} {last}")
    return tuple(dict.fromkeys(hypotheses))


def suggested_inventory_variants(
    snapshot: ProjectSnapshotPayload,
) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    for item in snapshot.consulted_objects:
        variants = generate_inventory_query_variants(item.inventory_number)
        ordered = sorted(
            variants,
            key=lambda variant: (
                variant.kind.value != "WITHOUT_INSTITUTION",
                variant.kind.value == "EXACT",
            ),
        )
        for variant in ordered:
            if variant.kind.value == "SEPARATOR":
                continue
            suggestions.append(
                {
                    "objectId": item.id,
                    "text": variant.text,
                    "kind": variant.kind.value,
                    "basedOn": "RECORDED_NUMBER",
                }
            )
    return suggestions


def discovery_floor(
    snapshot: ProjectSnapshotPayload,
    capabilities: tuple[BibliographicSourceCapabilities, ...],
    limit: int,
) -> tuple[AgenticSearchSpec, ...]:
    """Author plus object, on every source that can answer it.

    This leg used to go to one source — whichever ranked best on declared
    capability — and that made the whole guarantee depend on a single index
    knowing the taxon. Measured over the eight cases with a recorded expected
    publication, no index reaches them all: OpenAlex five, Crossref six, Europe
    PMC five, and each finds something the others miss. **Together they reach
    all eight.** The one publication the thirteen-sample run never surfaced sits
    in Crossref at rank one, on exactly this query, and was never asked for.

    The sources stay ordered by capability so that, under a reservation too
    small for all of them, each object still spends its first query on the index
    most likely to answer precisely.
    """
    if limit <= 0:
        return ()
    surname_hypotheses = bibliographic_surname_hypotheses(snapshot.researcher)
    if not surname_hypotheses:
        return ()
    ordered_sources = [
        source
        for source in sorted(
            capabilities,
            key=lambda item: (
                not item.supports_structured_author,
                not item.searches_indexed_full_text,
                item.name,
            ),
        )
        if source.searches_metadata
    ]
    if not ordered_sources:
        return ()
    surname = surname_hypotheses[0]
    searches = []
    for item in snapshot.consulted_objects[:limit]:
        for source in ordered_sources:
            query = f'"{item.object_name}"'
            # Only an index with an authorship field can be told the surname
            # separately; everywhere else it has to ride inside the query text.
            if not source.supports_structured_author:
                query = f'{query} "{surname}"'
            searches.append(
                AgenticSearchSpec(
                    source=source.name,
                    query=query,
                    author=surname,
                    object_id=item.id,
                    intent=SearchIntent.DISCOVERY,
                    strategy=SearchStrategy.AUTHOR_OBJECT,
                )
            )
    return tuple(searches)


def bare_inventory_query(inventory_number: str) -> str | None:
    """The recorded code without the institution prefix, when there is one.

    Publications cite the bare code far more often than the museum's full
    string, and the planner prompt already prioritises it. Falling back to the
    exact form keeps numbers that carry no prefix usable.
    """
    variants = generate_inventory_query_variants(inventory_number)
    for kind in ("WITHOUT_INSTITUTION", "EXACT"):
        for variant in variants:
            if variant.kind.value == kind:
                return variant.text
    return None


def inventory_floor(
    snapshot: ProjectSnapshotPayload,
    capabilities: tuple[BibliographicSourceCapabilities, ...],
    limit: int,
) -> tuple[AgenticSearchSpec, ...]:
    """One bare-code attempt per object, on a source that can prove the claim.

    The inventory code is the highest-yield signal in this domain, and leaving
    it to the planner means losing it entirely whenever the planner's contract
    fails. Only a source that returns inspectable text is used: on a
    metadata-only index the absence of the code would prove nothing.
    """
    if limit <= 0:
        return ()
    inspectable = sorted(
        (
            item
            for item in capabilities
            if item.searches_indexed_full_text and item.returns_inspectable_full_text
        ),
        key=lambda item: item.name,
    )
    if not inspectable:
        return ()
    source = inspectable[0]
    searches: list[AgenticSearchSpec] = []
    for item in snapshot.consulted_objects[:limit]:
        query = bare_inventory_query(item.inventory_number)
        if not query:
            continue
        searches.append(
            AgenticSearchSpec(
                source=source.name,
                query=f'"{query}"',
                object_id=item.id,
                intent=SearchIntent.INVENTORY_EVIDENCE,
                strategy=SearchStrategy.INVENTORY_QUERY,
            )
        )
    return tuple(searches)


def deterministic_floor(
    snapshot: ProjectSnapshotPayload,
    capabilities: tuple[BibliographicSourceCapabilities, ...],
    reservation: int,
) -> tuple[AgenticSearchSpec, ...]:
    """Both floors, interleaved per object and capped by the shared reservation.

    Interleaving keeps the two strategies represented when the reservation is
    smaller than the number of consulted objects: taking one strategy first
    would spend the whole floor on it and lose the other entirely.

    Within an object the order is best discovery source, then the inventory
    code, then the remaining discovery sources. Discovery runs on several
    indexes now, and grouping them together would let the extra ones push the
    inventory leg past the reservation for every object but the first — trading
    one guarantee for the other rather than keeping both.
    """
    if reservation <= 0:
        return ()
    per_strategy = max(1, reservation // 2)
    by_object: dict[str | None, list[AgenticSearchSpec]] = {}
    order: list[str | None] = []
    discovery = discovery_floor(snapshot, capabilities, per_strategy)
    inventory = inventory_floor(snapshot, capabilities, per_strategy)
    first_discovery: dict[str | None, AgenticSearchSpec] = {}
    for search in discovery:
        first_discovery.setdefault(search.object_id, search)
    ranked = (
        *first_discovery.values(),
        *inventory,
        *(
            search
            for search in discovery
            if first_discovery.get(search.object_id) is not search
        ),
    )
    # Author plus object comes first per object: it is the guarantee the
    # hardening plan asked for, and a reservation smaller than the object count
    # must not spend itself entirely on the inventory code.
    for search in ranked:
        if search.object_id not in by_object:
            by_object[search.object_id] = []
            order.append(search.object_id)
        by_object[search.object_id].append(search)
    interleaved: list[AgenticSearchSpec] = []
    for object_id in order:
        interleaved.extend(by_object[object_id])
    return tuple(interleaved[:reservation])


# Measured on the 12-case fixture (2026-08-25): OpenAlex and Europe PMC return
# every match at rank 1, while Crossref returns its five matches at ranks 1, 2,
# 3, 4 and 7 inside result sets that saturate the limit. Ten keeps a margin
# above the worst useful rank and halves what a metadata-only source can take
# from the shared result budget.
METADATA_ONLY_RESULT_LIMIT = 10
SOURCE_RESULT_CEILING = 20


def source_result_limit(
    capabilities: BibliographicSourceCapabilities | None, max_results: int
) -> int:
    """How many records one query to this source may spend from the budget.

    A source that searches only metadata cannot discriminate on the terms this
    domain sends — taxon names and inventory codes live in article bodies — so
    it answers broadly and ranks weakly. Every record it returns still costs one
    reader call, so it gets a smaller share of the investigation's results.

    The test is ``searches_indexed_full_text``, not the evidence capability:
    OpenAlex returns no inspectable text yet is the most precise source
    measured, and penalising it would be exactly backwards.
    """
    ceiling = min(SOURCE_RESULT_CEILING, max_results)
    if capabilities is not None and not capabilities.searches_indexed_full_text:
        return min(ceiling, METADATA_ONLY_RESULT_LIMIT)
    return ceiling


def search_is_supported(
    search: AgenticSearchSpec,
    capabilities: BibliographicSourceCapabilities,
) -> bool:
    if search.intent is SearchIntent.INVENTORY_EVIDENCE:
        return (
            capabilities.searches_indexed_full_text
            and capabilities.returns_inspectable_full_text
        )
    return capabilities.searches_metadata
