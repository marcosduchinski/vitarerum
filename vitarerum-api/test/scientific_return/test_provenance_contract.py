"""The HTTP contract for full-agentic provenance.

The application layer produced these fields all along while the presentation
layer silently dropped them, and nothing failed: every other test asserts the
persisted analysis payload, and the frontend specs mock the API. These tests
assert the wire format itself, so the queue cannot lose provenance again
without the suite going red.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.identity.public import Actor, GroupName, PermissionId
from app.main import app
from app.scientific_return.application.ports import CandidateReviewItem
from app.scientific_return.domain.enums import (
    AgentConfidence,
    CandidateStatus,
    DecisionType,
    EvidenceSourceField,
    InventoryEvidenceStatus,
)
from app.scientific_return.domain.full_agentic_models import (
    CandidateDecisionContext,
    GroundedInventoryForm,
)
from app.scientific_return.domain.models import (
    CandidateDecision,
    CandidateDecisionId,
    CandidatePublication,
    CandidatePublicationId,
    ScientificReturnRunId,
    ScientificReturnWatchId,
)
from app.scientific_return.presentation.dependencies import (
    get_full_agentic_configuration,
    get_full_agentic_starter,
    get_repository,
)
from app.shared.dependencies import get_caller_permission

_STAFF = Actor(
    id=PermissionId("perm-staff"),
    group=GroupName.CURATORIAL,
    email="curator@museum.pt",
)
_NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _candidate() -> CandidatePublication:
    return CandidatePublication(
        id=CandidatePublicationId("candidate-1"),
        watch_id=ScientificReturnWatchId("watch-1"),
        first_seen_run_id=ScientificReturnRunId("run-1"),
        source="EUROPE_PMC",
        source_record_id="PMC1",
        title="A revision of Acontias",
        authors=("Maria Silva",),
        publication_date="2026",
        abstract=None,
        url=None,
        doi="10.1/example",
        raw_metadata_hash="hash",
        deduplication_key="doi:10.1/example",
        status=CandidateStatus.PENDING,
        created_at=_NOW,
    )


class _Repository:
    """Only the two reads the provenance contract depends on."""

    async def list_candidate_queue(
        self,
        candidate_status: object,
        project_id: object,
        source: object,
        evidence_strength: object,
        page: int,
        size: int,
    ) -> tuple[list[CandidateReviewItem], int]:
        return (
            [
                CandidateReviewItem(
                    project_id="project-1",
                    candidate=_candidate(),
                    discovery_basis="AUTHOR_OBJECT",
                    search_intent="DISCOVERY",
                    search_strategy="AUTHOR_OBJECT",
                    inventory_evidence_status="VERIFIED",
                    grounded_inventory_forms=(
                        {
                            "observedForm": "MB04-001066",
                            "sourceField": "ABSTRACT",
                            "sourceLocator": None,
                        },
                    ),
                    grounded_passages=(
                        "Specimen MB04-001066 was examined for this revision.",
                    ),
                    rejected_passage_count=1,
                    rejected_inventory_form_count=2,
                )
            ],
            1,
        )

    async def list_decisions(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateDecision]:
        return [
            CandidateDecision(
                id=CandidateDecisionId("decision-1"),
                candidate_id=candidate_id,
                decision=DecisionType.CONFIRM,
                justification="Observed in the abstract",
                decided_by=PermissionId("perm-staff"),
                decided_at=_NOW,
                evidence_snapshot=(),
                correction=None,
                decision_context=CandidateDecisionContext(
                    version=1,
                    passages=("Specimen MB04-001066 was examined.",),
                    inventory_forms=("MB04-001066",),
                    queries=('"Acontias" "Silva"',),
                    sources=("EUROPE_PMC",),
                    explanation="The inventory number is cited literally",
                    confidence=AgentConfidence.HIGH,
                    contradictions=(),
                    knowledge_item_ids=(),
                    discovery_basis="AUTHOR_OBJECT",
                    search_intent="DISCOVERY",
                    search_strategy="AUTHOR_OBJECT",
                    inventory_evidence_status=InventoryEvidenceStatus.VERIFIED,
                    grounded_inventory_forms=(
                        GroundedInventoryForm(
                            observed_form="MB04-001066",
                            source_field=EvidenceSourceField.ABSTRACT,
                            source_locator=None,
                        ),
                    ),
                ),
            )
        ]


@asynccontextmanager
async def _client(
    overrides: dict[Callable[..., object], object] | None = None,
) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_caller_permission] = lambda: _STAFF
    for dependency, value in (overrides or {}).items():
        app.dependency_overrides[dependency] = lambda value=value: value
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


async def test_the_queue_exposes_the_provenance_of_every_candidate() -> None:
    async with _client({get_repository: _Repository()}) as client:
        response = await client.get("/api/v1/scientific-return/candidates")

    assert response.status_code == 200
    item = response.json()["content"][0]
    assert item["discoveryBasis"] == "AUTHOR_OBJECT"
    assert item["searchIntent"] == "DISCOVERY"
    assert item["searchStrategy"] == "AUTHOR_OBJECT"
    assert item["inventoryEvidenceStatus"] == "VERIFIED"
    assert item["groundedInventoryForms"] == [
        {
            "observedForm": "MB04-001066",
            "sourceField": "ABSTRACT",
            "sourceLocator": None,
        }
    ]
    assert item["groundedPassages"] == [
        "Specimen MB04-001066 was examined for this revision."
    ]
    assert item["rejectedPassageCount"] == 1
    assert item["rejectedInventoryFormCount"] == 2


async def test_the_decision_snapshot_keeps_what_the_curator_was_shown() -> None:
    async with _client({get_repository: _Repository()}) as client:
        response = await client.get(
            "/api/v1/scientific-return/candidates/candidate-1/decisions"
        )

    assert response.status_code == 200
    context = response.json()[0]["decisionContext"]
    assert context["discoveryBasis"] == "AUTHOR_OBJECT"
    assert context["searchIntent"] == "DISCOVERY"
    assert context["searchStrategy"] == "AUTHOR_OBJECT"
    assert context["inventoryEvidenceStatus"] == "VERIFIED"
    assert context["groundedInventoryForms"] == [
        {
            "observedForm": "MB04-001066",
            "sourceField": "ABSTRACT",
            "sourceLocator": None,
        }
    ]


async def test_readiness_reports_operational_sources_without_credentials() -> None:
    from app.scientific_return.application.full_agentic import (
        FullAgenticConfiguration,
    )
    from app.scientific_return.domain.full_agentic_models import AgenticBudget

    configuration = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("CROSSREF", "EUROPE_PMC"),
        budget=AgenticBudget(1, 1, 1, 1, 1),
        operational_sources=("CROSSREF", "EUROPE_PMC"),
        evidence_sources=("EUROPE_PMC",),
    )

    async with _client({get_full_agentic_configuration: configuration}) as client:
        response = await client.get("/api/v1/scientific-return/full-agentic-readiness")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "enabled": True,
        "requestedSources": ["CROSSREF", "EUROPE_PMC"],
        "operationalSources": ["CROSSREF", "EUROPE_PMC"],
        "unavailableSources": [],
        "inspectableEvidenceSources": ["EUROPE_PMC"],
        "configurationValid": True,
        "message": None,
    }


async def test_readiness_reports_a_source_that_is_requested_but_not_operational() -> (
    None
):
    from app.scientific_return.application.full_agentic import (
        FullAgenticConfiguration,
    )
    from app.scientific_return.domain.full_agentic_models import AgenticBudget

    configuration = FullAgenticConfiguration(
        enabled=True,
        allowed_sources=("CROSSREF", "EUROPE_PMC"),
        budget=AgenticBudget(1, 1, 1, 1, 1),
        operational_sources=("CROSSREF",),
        evidence_sources=(),
    )

    async with _client({get_full_agentic_configuration: configuration}) as client:
        response = await client.get("/api/v1/scientific-return/full-agentic-readiness")

    body = response.json()
    assert body["unavailableSources"] == ["EUROPE_PMC"]
    assert body["inspectableEvidenceSources"] == []
    assert body["configurationValid"] is False
    assert "inspectable inventory text" in body["message"]


async def test_an_impossible_source_configuration_is_refused_before_enqueue() -> None:
    """No work may be queued that no operational adapter could ever perform."""
    from app.scientific_return.application.full_agentic import (
        FullAgenticSourceConfigurationInvalid,
    )

    class _Starter:
        async def execute(self, data: object) -> None:
            raise FullAgenticSourceConfigurationInvalid(
                "No operational source can return inspectable inventory text"
            )

    async with _client({get_full_agentic_starter: _Starter()}) as client:
        response = await client.post(
            "/api/v1/scientific-return/watches/watch-1/full-agentic-investigations",
            json={"objective": "DISCOVER_CANDIDATE"},
            headers={"Idempotency-Key": "contract-key"},
        )

    assert response.status_code == 503
    assert response.json()["error"] == "FULL_AGENTIC_SOURCE_CONFIGURATION_INVALID"
