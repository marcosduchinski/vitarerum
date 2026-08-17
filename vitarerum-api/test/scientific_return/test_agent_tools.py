from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from app.scientific_return.application.agent_tools import (
    InMemoryAgentToolRegistry,
    InventoryVariantSearchTool,
    as_phrase_query,
    build_default_registry,
    tool_idempotency_key,
)
from app.scientific_return.application.ports import (
    BibliographicRecord,
    ToolExecutionContext,
    UnknownAgentTool,
)
from app.scientific_return.domain.agent_policies import AuthorizedExecution
from app.scientific_return.domain.enums import (
    AgentRecommendedAction,
    CandidateStatus,
    EvidenceType,
    InventoryVariantKind,
    InvestigationObjective,
)
from app.scientific_return.domain.inventory_variants import InventoryQueryVariant
from app.scientific_return.domain.models import (
    CandidatePublication,
    CandidatePublicationId,
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
    ScientificReturnRunId,
    ScientificReturnWatchId,
)

_NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
_SEARCH = AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS

_SNAPSHOT = ProjectSnapshotPayload(
    project_id="project-1",
    project_reference="PRJ-1",
    researcher="Rita P. Eusébio",
    consulted_objects=(
        ConsultedObjectSnapshot(
            id="object-1",
            inventory_number="MUHNAC/MB11-001283",
            object_name="Trichoniscoides machadoi",
        ),
    ),
)


def _record(
    *,
    source: str = "EUROPE_PMC",
    record_id: str = "PMC1",
    title: str = "Terrestrial isopods from Portugal",
    doi: str | None = "10.3897/subtbiol.53.163632",
    indexed_text: str | None = None,
) -> BibliographicRecord:
    return BibliographicRecord(
        source=source,
        source_record_id=record_id,
        title=title,
        authors=("Rita P. Eusébio",),
        publication_date="2025",
        abstract="A survey of Oniscidea.",
        url=None,
        doi=doi,
        raw_metadata_hash=hashlib.sha256(record_id.encode()).hexdigest(),
        indexed_text=indexed_text,
        indexed_text_source="full_text" if indexed_text else None,
    )


class _Source:
    def __init__(self, name: str, *, results: list[BibliographicRecord] | None = None,
                 error: Exception | None = None) -> None:
        self.name = name
        self._results = results or []
        self._error = error
        self.queries: list[tuple[str, int]] = []

    async def search(self, query: str, limit: int) -> list[BibliographicRecord]:
        self.queries.append((query, limit))
        if self._error is not None:
            raise self._error
        return list(self._results)


def _execution(
    *, queries: int = 2, sources: tuple[str, ...] = ("EUROPE_PMC",)
) -> AuthorizedExecution:
    variants = (
        InventoryQueryVariant("MB11-001283", InventoryVariantKind.WITHOUT_INSTITUTION),
        InventoryQueryVariant(
            "MNHNC:MB11:001283", InventoryVariantKind.INSTITUTION_ALIAS
        ),
        InventoryQueryVariant("MB11-1283", InventoryVariantKind.NUMBER_PADDING),
    )[:queries]
    return AuthorizedExecution(
        action=_SEARCH,
        object_id="object-1",
        queries=variants,
        sources=sources,
        result_limit=10,
    )


def _context(**overrides: object) -> ToolExecutionContext:
    values: dict[str, object] = {
        "objective": InvestigationObjective.DISCOVER_CANDIDATE,
        "snapshot": _SNAPSHOT,
        "now": _NOW,
    }
    values.update(overrides)
    return ToolExecutionContext(**values)  # type: ignore[arg-type]


def _candidate(
    *, dedup: str = "doi:10.3897/subtbiol.53.163632", doi: str | None = None
) -> CandidatePublication:
    return CandidatePublication(
        id=CandidatePublicationId("cand-1"),
        watch_id=ScientificReturnWatchId("watch-1"),
        first_seen_run_id=ScientificReturnRunId("run-1"),
        source="CROSSREF",
        source_record_id="rec-1",
        deduplication_key=dedup,
        title="Terrestrial isopods from Portugal",
        authors=("Rita P. Eusébio",),
        publication_date="2025",
        abstract=None,
        url=None,
        raw_metadata_hash="h",
        created_at=_NOW,
        doi=doi,
        status=CandidateStatus.PENDING,
    )


# --- execution ---------------------------------------------------------------


async def test_every_authorised_query_reaches_every_authorised_source() -> None:
    europe = _Source("EUROPE_PMC", results=[_record()])
    crossref = _Source("CROSSREF", results=[])
    tool = InventoryVariantSearchTool((europe, crossref))

    await tool.execute(
        _execution(queries=2, sources=("EUROPE_PMC", "CROSSREF")), _context()
    )

    # Quoted: an unquoted colon is read as field syntax by Europe PMC.
    assert [q for q, _ in europe.queries] == [
        '"MB11-001283"',
        '"MNHNC:MB11:001283"',
    ]
    assert [q for q, _ in crossref.queries] == [
        '"MB11-001283"',
        '"MNHNC:MB11:001283"',
    ]


def test_the_tool_cannot_widen_the_authorised_result_limit() -> None:
    execution = _execution()

    assert execution.result_limit == 10


async def test_the_authorised_result_limit_is_passed_through() -> None:
    source = _Source("EUROPE_PMC", results=[])
    await InventoryVariantSearchTool((source,)).execute(_execution(), _context())

    assert {limit for _, limit in source.queries} == {10}


async def test_each_query_is_audited_with_its_variant_kind() -> None:
    source = _Source("EUROPE_PMC", results=[_record()])
    outcome = await InventoryVariantSearchTool((source,)).execute(
        _execution(queries=2), _context()
    )

    kinds = {item.variant_kind for item in outcome.queries}
    assert kinds == {"WITHOUT_INSTITUTION", "INSTITUTION_ALIAS"}
    assert all(item.result_count == 1 for item in outcome.queries)


async def test_records_are_deduplicated_across_queries_and_sources() -> None:
    same = _record()
    tool = InventoryVariantSearchTool(
        (_Source("EUROPE_PMC", results=[same]), _Source("CROSSREF", results=[same]))
    )

    outcome = await tool.execute(
        _execution(queries=2, sources=("EUROPE_PMC", "CROSSREF")), _context()
    )

    assert len(outcome.records) == 1
    assert outcome.total_results == 4


# --- evidence and the actionable gate ----------------------------------------


async def test_the_deterministic_evidence_rules_decide_what_is_actionable() -> None:
    """The tool reports what the rules found; it does not judge for itself."""
    with_inventory = _record(
        record_id="PMC-hit",
        indexed_text="Material examined: MNHNC:MB11:001283, Portugal.",
    )
    tool = InventoryVariantSearchTool(
        (_Source("EUROPE_PMC", results=[with_inventory]),)
    )

    outcome = await tool.execute(_execution(queries=1), _context())

    record = outcome.records[0]
    assert record.is_actionable
    assert EvidenceType.INVENTORY_NUMBER in {item.type for item in record.evidences}


async def test_a_record_without_any_signal_is_not_actionable() -> None:
    unrelated = BibliographicRecord(
        source="EUROPE_PMC",
        source_record_id="PMC-miss",
        title="An unrelated study of soil chemistry",
        authors=("Someone Else",),
        publication_date="2025",
        abstract="Nothing to do with the consulted specimen.",
        url=None,
        doi="10.0000/unrelated",
        raw_metadata_hash="h",
    )
    tool = InventoryVariantSearchTool((_Source("EUROPE_PMC", results=[unrelated]),))

    outcome = await tool.execute(_execution(queries=1), _context())

    assert outcome.records[0].is_actionable is False
    assert outcome.actionable_records == ()


async def test_nothing_is_persisted_by_the_tool() -> None:
    """The tool has no repository, which is what keeps it honest."""
    tool = InventoryVariantSearchTool((_Source("EUROPE_PMC", results=[_record()]),))
    outcome = await tool.execute(_execution(queries=1), _context())

    assert outcome.records[0].candidate_id
    assert not hasattr(tool, "_repository")


# --- enrichment --------------------------------------------------------------


async def test_enrichment_keeps_only_the_candidate_under_investigation() -> None:
    match = _record(record_id="PMC-match")
    other = _record(record_id="PMC-other", doi="10.0000/something-else")
    tool = InventoryVariantSearchTool(
        (_Source("EUROPE_PMC", results=[match, other]),)
    )

    outcome = await tool.execute(
        _execution(queries=1),
        _context(
            objective=InvestigationObjective.ENRICH_CANDIDATE,
            candidate=_candidate(),
        ),
    )

    assert len(outcome.records) == 1
    assert outcome.records[0].matches_candidate
    assert outcome.records[0].candidate_id == "cand-1"


async def test_enrichment_matches_on_a_verifiable_doi() -> None:
    tool = InventoryVariantSearchTool((_Source("EUROPE_PMC", results=[_record()]),))

    outcome = await tool.execute(
        _execution(queries=1),
        _context(
            objective=InvestigationObjective.ENRICH_CANDIDATE,
            candidate=_candidate(
                dedup="metadata:other", doi="https://doi.org/10.3897/subtbiol.53.163632"
            ),
        ),
    )

    assert len(outcome.records) == 1
    assert outcome.records[0].candidate_id == "cand-1"


async def test_enrichment_will_not_attach_evidence_to_a_near_miss() -> None:
    """A similar title is not the same publication."""
    near = _record(record_id="PMC-near", doi="10.0000/near-miss")
    tool = InventoryVariantSearchTool((_Source("EUROPE_PMC", results=[near]),))

    outcome = await tool.execute(
        _execution(queries=1),
        _context(
            objective=InvestigationObjective.ENRICH_CANDIDATE,
            candidate=_candidate(dedup="doi:10.3897/subtbiol.53.163632"),
        ),
    )

    assert outcome.records == ()


async def test_discovery_keeps_everything_it_found() -> None:
    tool = InventoryVariantSearchTool(
        (_Source("EUROPE_PMC", results=[_record(record_id="a"),
                                        _record(record_id="b", doi="10.0/b")]),)
    )

    outcome = await tool.execute(_execution(queries=1), _context())

    assert len(outcome.records) == 2


# --- failure -----------------------------------------------------------------


async def test_a_failing_source_is_audited_without_losing_the_others() -> None:
    tool = InventoryVariantSearchTool(
        (
            _Source("EUROPE_PMC", error=RuntimeError("503")),
            _Source("CROSSREF", results=[_record(source="CROSSREF")]),
        )
    )

    outcome = await tool.execute(
        _execution(queries=1, sources=("EUROPE_PMC", "CROSSREF")), _context()
    )

    assert outcome.unavailable is False
    assert outcome.error is not None and "503" in outcome.error
    assert len(outcome.records) == 1


async def test_every_source_failing_reports_the_tool_as_unavailable() -> None:
    tool = InventoryVariantSearchTool(
        (_Source("EUROPE_PMC", error=TimeoutError("timed out")),)
    )

    outcome = await tool.execute(_execution(queries=2), _context())

    assert outcome.unavailable
    assert outcome.total_results == 0
    assert len(outcome.queries) == 2


async def test_a_source_without_an_adapter_is_reported_not_skipped() -> None:
    tool = InventoryVariantSearchTool((_Source("CROSSREF", results=[]),))

    outcome = await tool.execute(
        _execution(queries=1, sources=("EUROPE_PMC",)), _context()
    )

    assert outcome.unavailable
    assert outcome.error is not None and "no adapter" in outcome.error


# --- reproducibility ---------------------------------------------------------


async def test_the_result_hash_is_stable_for_the_same_findings() -> None:
    tool = InventoryVariantSearchTool((_Source("EUROPE_PMC", results=[_record()]),))

    first = await tool.execute(_execution(queries=1), _context())
    second = await tool.execute(_execution(queries=1), _context())

    assert first.result_hash == second.result_hash
    assert first.result_hash != ""


async def test_the_result_hash_changes_with_the_findings() -> None:
    one = InventoryVariantSearchTool((_Source("E", results=[_record()]),))
    two = InventoryVariantSearchTool(
        (_Source("E", results=[_record(), _record(record_id="b", doi="10.0/b")]),)
    )

    a = await one.execute(_execution(queries=1, sources=("E",)), _context())
    b = await two.execute(_execution(queries=1, sources=("E",)), _context())

    assert a.result_hash != b.result_hash


def test_the_idempotency_key_is_derived_from_what_will_run() -> None:
    key = tool_idempotency_key("inv-1", 1, _execution())

    assert key == tool_idempotency_key("inv-1", 1, _execution())
    assert key != tool_idempotency_key("inv-1", 2, _execution())
    assert key != tool_idempotency_key("inv-2", 1, _execution())
    assert key != tool_idempotency_key("inv-1", 1, _execution(queries=3))


# --- registry ----------------------------------------------------------------


def test_the_registry_resolves_a_registered_tool() -> None:
    registry = build_default_registry((_Source("CROSSREF"),))

    assert registry.resolve(_SEARCH).action is _SEARCH


@pytest.mark.parametrize(
    "action",
    [
        AgentRecommendedAction.SEARCH_AUTHOR_VARIANTS,
        AgentRecommendedAction.SEARCH_TAXON_VARIANTS,
        AgentRecommendedAction.SEARCH_FULL_TEXT,
        AgentRecommendedAction.DEPRIORITIZE,
    ],
)
def test_an_unregistered_action_cannot_be_resolved(
    action: AgentRecommendedAction,
) -> None:
    """Configuration cannot conjure an executor that was never written."""
    registry = build_default_registry((_Source("CROSSREF"),))

    with pytest.raises(UnknownAgentTool, match=action.value):
        registry.resolve(action)


def test_the_registry_reports_what_it_holds() -> None:
    registry = InMemoryAgentToolRegistry(
        InventoryVariantSearchTool((_Source("CROSSREF"),))
    )

    assert registry.registered_actions == frozenset({_SEARCH})


def test_a_variant_is_sent_as_an_exact_phrase() -> None:
    """Observed live: unquoted colons become field syntax and hyphens loose tokens."""
    assert as_phrase_query("MNHNC:MB11:001283") == '"MNHNC:MB11:001283"'
    assert as_phrase_query("  MB11-001283  ") == '"MB11-001283"'


async def test_the_audited_query_is_the_one_actually_sent() -> None:
    source = _Source("EUROPE_PMC", results=[])
    outcome = await InventoryVariantSearchTool((source,)).execute(
        _execution(queries=1), _context()
    )

    assert outcome.queries[0].query == '"MB11-001283"'
    assert outcome.queries[0].query == source.queries[0][0]
