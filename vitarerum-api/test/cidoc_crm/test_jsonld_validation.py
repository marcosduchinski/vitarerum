"""Validate the generated CIDOC-CRM JSON-LD as real RDF.

Two layers, exercised through the cidoc_crm reasoning helpers / public OHS:
  1. rdflib parses the document → proves it is valid JSON-LD/RDF and every term
     resolves to a real ``crm:`` IRI (would have caught the P170i typo).
  2. pyshacl validates the (expanded) graph against the bundled CIDOC-CRM
     domain/range shapes + class hierarchy.
"""

from datetime import UTC, date, datetime

from rdflib import URIRef

from app.cidoc_crm import public as cidoc_public
from app.cidoc_crm.in_situ_visit_mapping.application.cidoc import reasoning
from app.cidoc_crm.in_situ_visit_mapping.application.cidoc.engine import (
    map_record_to_cidoc,
)
from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    AttachmentData,
    ChildData,
    InSituVisitRecord,
)
from app.cidoc_crm.public import expand_and_validate_cidoc, validate_cidoc

CRM = "http://www.cidoc-crm.org/cidoc-crm/"


def _sample_record() -> InSituVisitRecord:
    return InSituVisitRecord.create(
        code="VS-1",
        visit_begin_date=date(2026, 1, 1),
        visit_end_date=date(2026, 1, 2),
        visitor_name="Ana",
        place_name="Museu",
        requested_objects=[ChildData("XL01", "lupus", 1)],
        in_situ_occurrences=[
            ChildData("OC1", "occ", 0, [AttachmentData("A1", "foto", "foto.jpg", 0)])
        ],
        in_situ_logs=[ChildData("LOG1", "log", 0)],
        in_situ_publications=[ChildData("P1", "desc", 0)],
    )


def _evidenced_record() -> InSituVisitRecord:
    return InSituVisitRecord.create(
        code="VS-1",
        visit_begin_date=date(2026, 1, 1),
        visit_end_date=date(2026, 1, 2),
        visitor_name="Ana",
        place_name="Museu",
        execution_occurred_at=datetime(2026, 1, 2, 17, 0, tzinfo=UTC),
        requested_objects=[ChildData("XL01", "lupus", 1)],
    )


def _doc() -> dict:
    return map_record_to_cidoc(_sample_record())


def _evidenced_doc() -> dict:
    return map_record_to_cidoc(_evidenced_record())


def test_document_is_valid_rdf_with_resolved_terms() -> None:
    graph = reasoning.to_graph(_evidenced_doc())
    assert len(graph) > 0
    # Every IRI resolved through the context — nothing left as a compact "crm:…".
    compact = [
        n
        for triple in graph
        for n in triple
        if isinstance(n, URIRef) and str(n).startswith("crm:")
    ]
    assert compact == []
    # The corrected time-span predicate resolves to the real CRM IRI.
    assert (
        len(list(graph.triples((None, URIRef(CRM + "P170i_time_is_defined_by"), None))))
        == 1
    )


def test_generated_graph_conforms_to_crm_shapes() -> None:
    _expanded, conforms, _report = expand_and_validate_cidoc(_doc())
    assert conforms is True


def test_validate_cidoc_reports_conformance_without_returning_expanded_graph() -> None:
    conforms, _report = validate_cidoc(_doc())
    assert conforms is True


def test_validate_cidoc_does_not_materialise_expanded_graph(monkeypatch) -> None:
    doc = _doc()
    parsed_graph = object()
    calls: list[str] = []

    def to_graph(candidate: dict) -> object:
        assert candidate is doc
        calls.append("to_graph")
        return parsed_graph

    def expand_graph(_candidate: dict) -> object:
        raise AssertionError("validate_cidoc must not materialise inferred graph")

    def validate_graph(candidate: object) -> tuple[bool, str]:
        assert candidate is parsed_graph
        calls.append("validate_graph")
        return True, "ok"

    monkeypatch.setattr(cidoc_public, "to_graph", to_graph)
    monkeypatch.setattr(cidoc_public, "expand_graph", expand_graph)
    monkeypatch.setattr(cidoc_public, "validate_graph", validate_graph)

    assert cidoc_public.validate_cidoc(doc) == (True, "ok")
    assert calls == ["to_graph", "validate_graph"]


def test_shapes_reject_a_domain_range_violation() -> None:
    # Sanity check that the shapes actually bite: point P14_carried_out_by (range
    # E39 Actor) at the Time-Span node, which is not an Actor.
    graph = reasoning.to_graph(_evidenced_doc())
    p14 = URIRef(CRM + "P14_carried_out_by")
    visit = next(graph.subjects(p14, None))
    timespan = next(graph.objects(visit, URIRef(CRM + "P4_has_time-span")))
    graph.add((visit, p14, timespan))
    conforms, _report = reasoning.validate_graph(graph)
    assert conforms is False
