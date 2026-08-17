from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scientific_return.application.evaluation import (
    BaselineStatus,
    EvaluationCase,
    ExpectedGap,
    load_evaluation_cases,
    load_evaluation_fixture,
)
from app.scientific_return.domain.inventory_variants import (
    comparison_key,
    generate_inventory_query_variants,
)

_ORIGINAL_CASE_IDS = {
    "rhoptropus-2025",
    "acontias-2023",
    "pachydactylus-2025",
    "serra-da-neve-checklist-2024",
    "sao-tome-barcode-2023",
}


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _case_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "caseId": "example-2026",
        "author": "Example Researcher",
        "inventoryNumber": "MUHNAC/MB03-001522",
        "objectName": "Example taxon",
        "expectedTitle": "An example article",
        "expectedDoi": "10.0000/example",
        "baselineStatus": "UNVERIFIED",
        "expectedGap": "INVENTORY_FORMAT",
        "citedInventoryForms": ["MB03-001522"],
        "notes": "Example case.",
    }
    payload.update(overrides)
    return payload


def test_the_shipped_fixture_loads() -> None:
    fixture = load_evaluation_fixture()

    assert fixture.version
    assert len(fixture.cases) >= len(_ORIGINAL_CASE_IDS)
    assert all(isinstance(case, EvaluationCase) for case in fixture.cases)


def test_the_original_cases_survive_the_extraction() -> None:
    """The five documented baseline cases must not be lost in the move to disk.

    They must also stay RESOLVED: the promotion gate forbids losing a case the
    baseline already recovered.
    """
    cases = {case.case_id: case for case in load_evaluation_cases()}

    assert _ORIGINAL_CASE_IDS <= set(cases)
    for case_id in _ORIGINAL_CASE_IDS:
        assert cases[case_id].baseline_status is BaselineStatus.RESOLVED


def test_the_fixture_separates_discovery_targets_from_enrichment_targets() -> None:
    cases = load_evaluation_cases()
    discovery = [
        case for case in cases if case.baseline_status is BaselineStatus.GAP
    ]
    enrichment = [
        case
        for case in cases
        if case.baseline_status is BaselineStatus.RESOLVED
        and case.baseline_inventory_evidence is False
    ]

    assert discovery, "E1 needs at least one DISCOVER_CANDIDATE target"
    assert enrichment, "E1 needs at least one ENRICH_CANDIDATE target"


def test_the_fixture_adds_cases_the_baseline_has_not_resolved() -> None:
    """A saturated fixture cannot demonstrate the agentic cycle."""
    cases = load_evaluation_cases()
    pending = [
        case for case in cases if case.baseline_status is not BaselineStatus.RESOLVED
    ]

    assert pending, "the fixture must carry cases beyond the saturated baseline"
    assert any(case.expected_gap is ExpectedGap.INVENTORY_FORMAT for case in pending)


def test_every_declared_gap_records_the_published_evidence() -> None:
    for case in load_evaluation_cases():
        if case.expected_gap in {
            ExpectedGap.INVENTORY_FORMAT,
            ExpectedGap.INSTITUTIONAL_ACRONYM,
        }:
            assert case.cited_inventory_forms, (
                f"{case.case_id} declares a gap without citing the published form"
            )


def test_declared_inventory_gaps_are_reachable_by_the_variant_generator() -> None:
    """The declaration and the generator must agree, or a gate reads a fiction.

    A case declared as an inventory-format gap is only meaningful if some form
    actually printed in the article is one the generator would ask for.
    """
    closable = {ExpectedGap.INVENTORY_FORMAT, ExpectedGap.INSTITUTIONAL_ACRONYM}
    for case in load_evaluation_cases():
        if case.expected_gap not in closable:
            continue
        variants = {
            comparison_key(variant.text)
            for variant in generate_inventory_query_variants(case.inventory_number)
        }
        cited = {comparison_key(form) for form in case.cited_inventory_forms}
        assert variants & cited, (
            f"{case.case_id}: no generated variant matches any cited form "
            f"{sorted(case.cited_inventory_forms)}"
        )


def test_declared_gaps_are_reachable_within_the_configured_query_budget() -> None:
    """Reachable in principle is not enough when only four queries are affordable.

    The deterministic pipeline has already spent the exact recorded form, so the
    agentic iteration starts from that and must hit a printed form inside its
    budget. A variant ranked seventh is never asked for.
    """
    budget = 4
    closable = {ExpectedGap.INVENTORY_FORMAT, ExpectedGap.INSTITUTIONAL_ACRONYM}
    for case in load_evaluation_cases():
        if case.expected_gap not in closable:
            continue
        affordable = {
            comparison_key(variant.text)
            for variant in generate_inventory_query_variants(
                case.inventory_number,
                already_tried=(f'"{case.inventory_number}"',),
                limit=budget,
            )
        }
        cited = {comparison_key(form) for form in case.cited_inventory_forms}
        assert affordable & cited, (
            f"{case.case_id}: no form printed in the article is among the first "
            f"{budget} untried variants"
        )


def test_the_recorded_form_alone_does_not_close_a_declared_gap() -> None:
    """If the exact form were enough, the deterministic pipeline would suffice."""
    for case in load_evaluation_cases():
        if case.expected_gap is not ExpectedGap.INVENTORY_FORMAT:
            continue
        cited = {comparison_key(form) for form in case.cited_inventory_forms}
        assert comparison_key(case.inventory_number) not in cited


def test_unmapped_papers_are_documented() -> None:
    fixture = load_evaluation_fixture()

    assert fixture.unmapped_papers
    for paper in fixture.unmapped_papers:
        assert paper.reference and paper.expected_doi and paper.reason


def test_a_fully_resolved_case_may_not_declare_a_gap(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {
            "version": "test",
            "cases": [
                _case_payload(
                    baselineStatus="RESOLVED", baselineInventoryEvidence=True
                )
            ],
        },
    )

    with pytest.raises(ValueError, match="cannot also declare a gap"):
        load_evaluation_fixture(path)


def test_a_resolved_case_without_inventory_evidence_may_declare_a_gap(
    tmp_path: Path,
) -> None:
    """This is the enrichment target: in the queue, but with no inventory proof."""
    path = _write(
        tmp_path,
        {
            "version": "test",
            "cases": [
                _case_payload(
                    baselineStatus="RESOLVED", baselineInventoryEvidence=False
                )
            ],
        },
    )

    case = load_evaluation_fixture(path).cases[0]

    assert case.baseline_status is BaselineStatus.RESOLVED
    assert case.baseline_inventory_evidence is False


def test_a_gap_case_must_state_its_cause(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {
            "version": "test",
            "cases": [
                _case_payload(
                    baselineStatus="GAP",
                    baselineInventoryEvidence=False,
                    expectedGap="NONE",
                )
            ],
        },
    )

    with pytest.raises(ValueError, match="must declare why it is a gap"):
        load_evaluation_fixture(path)


def test_an_unverified_case_may_not_claim_a_measurement(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {
            "version": "test",
            "cases": [_case_payload(baselineInventoryEvidence=False)],
        },
    )

    with pytest.raises(ValueError, match="baselineInventoryEvidence"):
        load_evaluation_fixture(path)


def test_duplicated_case_ids_are_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"version": "test", "cases": [_case_payload(), _case_payload()]},
    )

    with pytest.raises(ValueError, match="Duplicated case ids"):
        load_evaluation_fixture(path)


def test_an_unsupported_status_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        {"version": "test", "cases": [_case_payload(baselineStatus="MAYBE")]},
    )

    with pytest.raises(ValueError, match="unsupported enum"):
        load_evaluation_fixture(path)


def test_an_empty_fixture_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, {"version": "test", "cases": []})

    with pytest.raises(ValueError, match="at least one case"):
        load_evaluation_fixture(path)


def test_a_missing_field_is_rejected(tmp_path: Path) -> None:
    payload = _case_payload()
    del payload["objectName"]
    path = _write(tmp_path, {"version": "test", "cases": [payload]})

    with pytest.raises(ValueError, match="objectName"):
        load_evaluation_fixture(path)


def test_a_case_builds_a_single_object_snapshot() -> None:
    case = load_evaluation_cases()[0]
    snapshot = case.snapshot()

    assert snapshot.researcher == case.author
    assert len(snapshot.consulted_objects) == 1
    assert snapshot.consulted_objects[0].inventory_number == case.inventory_number
