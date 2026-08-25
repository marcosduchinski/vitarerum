from decimal import Decimal

import pytest

from app.main import app
from app.scientific_return.application.bench_evaluation import (
    BenchEvaluationObservation,
    evaluate_bench,
)
from app.scientific_return.application.bench_export import (
    CSV_COLUMNS,
    export_candidates,
)
from app.scientific_return.domain.bench_models import (
    BenchRuleViolation,
    NormalizedScore,
    derive_batch_status,
)
from app.scientific_return.domain.bench_models import (
    TestBatchStatus as BatchStatus,
)
from app.scientific_return.domain.bench_models import (
    TestItemStatus as ItemStatus,
)
from app.scientific_return.domain.bench_models import (
    TestSubject as Subject,
)
from app.scientific_return.domain.full_agentic_models import AgenticBudget
from app.scientific_return.infrastructure.bench_agentic_runtime import (
    LocalCorpusDocument,
    execute_bench_agentic,
)
from app.scientific_return.presentation import bench_routes


def test_subject_normalizes_whitespace_and_requires_all_fields() -> None:
    subject = Subject("  Maria   Silva ", "  Shell  collection ", " M-01 ")
    assert subject.author == "Maria Silva"
    assert subject.object_name == "Shell collection"
    assert subject.inventory_number == "M-01"
    with pytest.raises(BenchRuleViolation):
        Subject("", "Object", "M-01")


def test_batch_status_covers_all_error_cancel_and_retry_states() -> None:
    assert derive_batch_status([ItemStatus.ERROR]) is BatchStatus.FAILED
    assert (
        derive_batch_status([ItemStatus.COMPLETED, ItemStatus.ERROR])
        is BatchStatus.COMPLETED_WITH_ERRORS
    )
    assert (
        derive_batch_status(
            [ItemStatus.COMPLETED, ItemStatus.CANCELLED],
            cancellation_requested=True,
        )
        is BatchStatus.CANCELLED
    )
    assert (
        derive_batch_status([ItemStatus.RUNNING], cancellation_requested=True)
        is BatchStatus.CANCELLING
    )
    assert derive_batch_status([ItemStatus.PENDING]) is BatchStatus.QUEUED


def test_score_rejects_values_outside_normalized_range() -> None:
    assert NormalizedScore(Decimal("0.50000")).value == Decimal("0.50000")
    with pytest.raises(BenchRuleViolation):
        NormalizedScore(Decimal("1.00001"))


def _document(content: str) -> LocalCorpusDocument:
    return LocalCorpusDocument(
        source_id="source-1",
        revision_id="revision-1",
        name="Source one",
        revision=1,
        locator="https://example.test/source",
        authors=("Maria Silva",),
        content=content,
        content_hash="a" * 64,
    )


async def _run_bench(content: str):  # type: ignore[no-untyped-def]
    return await execute_bench_agentic(
        item_id="item-1",
        attempt_number=1,
        created_by="permission-1",
        subject=Subject("Maria Silva", "Acontias mukwando", "MUHNAC/MB03-001524"),
        documents=(_document(content),),
        reasoner=None,
        budget=AgenticBudget(2, 4, 10, 3, 8),
        worker_id="worker-1",
    )


@pytest.mark.asyncio
async def test_bench_traverses_the_production_autonomous_search_trajectory() -> None:
    outcome = await _run_bench(
        "Study by Maria Silva of Acontias mukwando specimen MUHNAC/MB03-001524."
    )

    kinds = [event.kind.value for event in outcome.operations.events]
    assert "PLAN_CREATED" in kinds
    assert "TOOL_STARTED" in kinds
    assert "ARTICLE_ASSESSED" in kinds
    assert "CANDIDATE_LINKED" in kinds
    # The deterministic floor: author plus object, then the bare inventory code.
    assert outcome.investigation.usage.queries == 2
    assert len(outcome.scientific.candidates) == 1


@pytest.mark.parametrize(
    ("label", "cited_form"),
    [
        ("without institution", "MB03-001524"),
        ("separator", "MB03 001524"),
        ("number padding", "MB03-1524"),
        ("institution alias", "MNHNC:MB03:001524"),
    ],
)
@pytest.mark.asyncio
async def test_shared_grounding_verifies_the_form_the_publication_actually_used(
    label: str, cited_form: str
) -> None:
    content = f"Maria Silva examined Acontias mukwando specimen {cited_form} in 2025."
    outcome = await _run_bench(content)
    analysis = next(iter(outcome.scientific.analyses.values()))

    assert analysis.input_payload["inventoryEvidenceStatus"] == "VERIFIED", label
    forms = analysis.input_payload["groundedInventoryForms"]
    assert isinstance(forms, list)
    assert forms[0]["observedForm"] == cited_form


@pytest.mark.asyncio
async def test_shared_grounding_does_not_verify_missing_inventory() -> None:
    content = "Maria Silva examined Acontias mukwando specimens in 2025."
    outcome = await _run_bench(content)
    analysis = next(iter(outcome.scientific.analyses.values()))

    assert analysis.input_payload["inventoryEvidenceStatus"] == "NOT_OBSERVED"
    assert analysis.input_payload["groundedInventoryForms"] == []


def test_csv_has_auditable_columns_and_neutralizes_formula_injection() -> None:
    row = {
        "itemId": "item-1",
        "attemptNumber": 2,
        "author": "=cmd",
        "objectName": "Object",
        "inventoryNumber": "M-01",
        "rank": 1,
        "score": Decimal("0.70000"),
        "scoreVersion": "ranker-v1",
        "sourceId": "source-1",
        "sourceName": "Source, one",
        "sourceRevision": 3,
        "sourceLocator": "https://example.test",
        "query": '"M-01"',
        "discoveryBasis": "INVENTORY",
        "inventoryEvidenceStatus": "VERIFIED",
        "evidence": "line one\nline two",
    }
    output = export_candidates([row])
    assert output.startswith(",".join(CSV_COLUMNS))
    assert "'=cmd" in output
    assert '"Source, one"' in output
    assert '"line one\nline two"' in output


def test_all_test_bench_http_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    expected = {
        "/api/v1/scientific-return/test-readiness",
        "/api/v1/scientific-return/test-sources",
        "/api/v1/scientific-return/test-sources/{source_id}",
        "/api/v1/scientific-return/test-batches",
        "/api/v1/scientific-return/test-batches/{batch_id}",
        "/api/v1/scientific-return/test-batches/{batch_id}/items",
        "/api/v1/scientific-return/test-batches/{batch_id}/start",
        "/api/v1/scientific-return/test-batches/{batch_id}/candidates",
        "/api/v1/scientific-return/test-batches/{batch_id}/export.csv",
        "/api/v1/scientific-return/internal/test-items/{item_id}/execute",
    }
    assert expected <= set(paths)


def test_evaluation_reports_precision_recall_mrr_and_grounding_separately() -> None:
    metrics = evaluate_bench(
        (
            BenchEvaluationObservation(True, (1,), grounded_candidates=1),
            BenchEvaluationObservation(True, (), rejected_claims=1),
            BenchEvaluationObservation(False, (1,)),
        )
    )
    assert metrics.precision_at_k == pytest.approx(0.5)
    assert metrics.recall_at_k == pytest.approx(0.5)
    assert metrics.mean_reciprocal_rank == pytest.approx(1 / 3)
    assert metrics.grounded_evidence_coverage == pytest.approx(0.5)
    assert metrics.rejected_claim_rate == pytest.approx(0.5)
    assert metrics.zero_result_rate == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_one_failing_item_never_cancels_the_rest_of_the_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A TaskGroup would cancel the siblings on the first exception."""
    executed: list[str] = []

    async def one(item_id: str) -> None:
        if item_id == "boom":
            raise RuntimeError("the item handler let an exception escape")
        executed.append(item_id)

    monkeypatch.setattr(bench_routes, "_execute_one_bench_item", one)

    await bench_routes._execute_bench_background(["boom", "item-b", "item-c"])

    assert executed == ["item-b", "item-c"]
