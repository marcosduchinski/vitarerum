"""The executors the cycle may run, and the registry that resolves them.

The model never calls a tool. It names an action; the policy turns that into an
``AuthorizedExecution`` with the exact queries and sources; the registry finds
the executor registered for that action. A tool that is not registered cannot
run, whatever the model or the configuration says.

Tools do not write. They search, normalise, deduplicate and run the same
deterministic evidence rules the scheduled pipeline uses, then report what those
rules found. Persistence — and the provenance that goes with it — is the
caller's job, which keeps a tool testable against fake sources alone.
"""

from __future__ import annotations

import hashlib
from uuid import uuid4

from app.scientific_return.application.analysis import (
    build_evidences,
    deduplication_key,
    is_actionable,
)
from app.scientific_return.application.ports import (
    AgentTool,
    AgentToolOutcome,
    AgentToolRegistry,
    BibliographicRecord,
    BibliographicSource,
    DiscoveredRecord,
    ToolExecutionContext,
    ToolQueryOutcome,
    UnknownAgentTool,
)
from app.scientific_return.domain.agent_policies import AuthorizedExecution
from app.scientific_return.domain.enums import (
    AgentRecommendedAction,
    InvestigationObjective,
)
from app.scientific_return.domain.models import (
    CandidatePublication,
    CandidatePublicationId,
)


def tool_idempotency_key(
    investigation_id: str,
    iteration_number: int,
    execution: AuthorizedExecution,
) -> str:
    """Stable key for one authorised execution.

    Derived from what will actually run rather than randomly generated, so a
    replayed command produces the same key and finds the previous execution
    instead of repeating an external call.
    """
    basis = "|".join(
        (
            investigation_id,
            str(iteration_number),
            execution.action.value,
            execution.object_id,
            ",".join(variant.text for variant in execution.queries),
            ",".join(execution.sources),
        )
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def as_phrase_query(text: str) -> str:
    """Wrap a variant as an exact phrase, the way the scheduled pipeline does.

    Sending a variant unquoted is not merely less precise, it can change what
    the query means: Europe PMC reads ``MNHNC:MB11:001283`` as field syntax,
    where ``MNHNC`` is a field name, and Crossref treats the parts as loose
    tokens and returns unrelated work. Both were observed against the live
    sources before this was applied.
    """
    return f'"{text.strip()}"'


def _normalized_doi(value: str | None) -> str:
    return (value or "").casefold().removeprefix("https://doi.org/")


def _result_hash(records: tuple[DiscoveredRecord, ...]) -> str:
    keys = sorted(
        f"{item.record.source}|{item.record.source_record_id}|{item.deduplication_key}"
        for item in records
    )
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def _matches(
    record: BibliographicRecord, key: str, candidate: CandidatePublication
) -> bool:
    """Whether a record is the candidate under enrichment.

    Only the deduplication key or a verifiable DOI count. Matching on title
    similarity would let a near-miss attach evidence to the wrong publication.
    """
    if key == candidate.deduplication_key:
        return True
    candidate_doi = _normalized_doi(candidate.doi)
    return bool(candidate_doi) and _normalized_doi(record.doi) == candidate_doi


class InventoryVariantSearchTool:
    """Executes ``SEARCH_INVENTORY_VARIANTS`` over the authorised sources."""

    action = AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS

    def __init__(self, sources: tuple[BibliographicSource, ...]) -> None:
        self._sources = {source.name.upper(): source for source in sources}

    async def execute(
        self, execution: AuthorizedExecution, context: ToolExecutionContext
    ) -> AgentToolOutcome:
        outcomes: list[ToolQueryOutcome] = []
        by_key: dict[str, BibliographicRecord] = {}
        total_results = 0
        errors: list[str] = []

        for source_name in execution.sources:
            source = self._sources.get(source_name.upper())
            if source is None:
                # Configured but not wired: recorded rather than skipped, so a
                # deployment mismatch is visible in the trajectory.
                errors.append(f"{source_name}: no adapter is configured")
                outcomes.append(
                    ToolQueryOutcome(
                        query="",
                        variant_kind="",
                        source=source_name,
                        result_count=0,
                        error="no adapter is configured",
                    )
                )
                continue
            for variant in execution.queries:
                # The audited query is the one actually sent, quoting included.
                sent = as_phrase_query(variant.text)
                try:
                    records = await source.search(sent, execution.result_limit)
                except Exception as exc:
                    message = f"{type(exc).__name__}: {exc}"[:500]
                    errors.append(f"{source_name}: {message}")
                    outcomes.append(
                        ToolQueryOutcome(
                            query=sent,
                            variant_kind=variant.kind.value,
                            source=source_name,
                            result_count=0,
                            error=message,
                        )
                    )
                    continue
                total_results += len(records)
                outcomes.append(
                    ToolQueryOutcome(
                        query=sent,
                        variant_kind=variant.kind.value,
                        source=source_name,
                        result_count=len(records),
                    )
                )
                for record in records:
                    by_key.setdefault(deduplication_key(record), record)

        discovered = self._describe(by_key, context)
        attempted = [item for item in outcomes if item.query]
        unavailable = bool(attempted) and all(item.error for item in attempted)
        return AgentToolOutcome(
            action=self.action,
            queries=tuple(outcomes),
            records=discovered,
            total_results=total_results,
            result_hash=_result_hash(discovered),
            unavailable=unavailable or not attempted,
            error="; ".join(errors)[:2000] or None,
        )

    @staticmethod
    def _describe(
        by_key: dict[str, BibliographicRecord], context: ToolExecutionContext
    ) -> tuple[DiscoveredRecord, ...]:
        candidate = context.candidate
        enriching = context.objective is InvestigationObjective.ENRICH_CANDIDATE
        described: list[DiscoveredRecord] = []
        for key, record in by_key.items():
            matches = bool(candidate) and _matches(record, key, candidate)  # type: ignore[arg-type]
            if enriching and not matches:
                # Enrichment may only touch the candidate under investigation.
                # Everything else found along the way is discarded here rather
                # than left for the caller to filter and possibly forget.
                continue
            candidate_id = (
                candidate.id
                if matches and candidate is not None
                else CandidatePublicationId(str(uuid4()))
            )
            evidences = build_evidences(
                candidate_id, context.snapshot, record, context.now
            )
            described.append(
                DiscoveredRecord(
                    candidate_id=candidate_id,
                    record=record,
                    deduplication_key=key,
                    evidences=tuple(evidences),
                    is_actionable=is_actionable(evidences),
                    matches_candidate=matches,
                )
            )
        return tuple(described)


class InMemoryAgentToolRegistry:
    """Resolves only the tools explicitly registered for this increment."""

    def __init__(self, *tools: AgentTool) -> None:
        self._tools: dict[AgentRecommendedAction, AgentTool] = {
            tool.action: tool for tool in tools
        }

    def resolve(self, action: AgentRecommendedAction) -> AgentTool:
        tool = self._tools.get(action)
        if tool is None:
            raise UnknownAgentTool(f"No tool is registered for {action.value}")
        return tool

    @property
    def registered_actions(self) -> frozenset[AgentRecommendedAction]:
        return frozenset(self._tools)


def build_default_registry(
    sources: tuple[BibliographicSource, ...],
) -> AgentToolRegistry:
    return InMemoryAgentToolRegistry(InventoryVariantSearchTool(sources))
