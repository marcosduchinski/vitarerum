"""Validate the generated CIDOC-CRM JSON-LD as real RDF.

Two layers, exercised through the cidoc_crm reasoning helpers / public OHS:
  1. rdflib parses the document → proves it is valid JSON-LD/RDF and every term
     resolves to a real ``crm:`` IRI (would have caught the P170i typo).
  2. pyshacl validates the (expanded) graph against the bundled CIDOC-CRM
     domain/range shapes + class hierarchy.
"""

from datetime import date

from rdflib import URIRef

from app.cidoc_crm.in_situ_visit_mapping.application.cidoc import reasoning
from app.cidoc_crm.in_situ_visit_mapping.application.cidoc.engine import (
    map_record_to_cidoc,
)
from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    AttachmentData,
    ChildData,
    InSituVisitRecord,
)
from app.cidoc_crm.public import expand_and_validate_cidoc

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


def _doc() -> dict:
    return map_record_to_cidoc(_sample_record())


def test_document_is_valid_rdf_with_resolved_terms() -> None:
    graph = reasoning.to_graph(_doc())
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


def test_shapes_reject_a_domain_range_violation() -> None:
    # Sanity check that the shapes actually bite: point P14_carried_out_by (range
    # E39 Actor) at the Time-Span node, which is not an Actor.
    graph = reasoning.to_graph(_doc())
    p14 = URIRef(CRM + "P14_carried_out_by")
    visit = next(graph.subjects(p14, None))
    timespan = next(graph.objects(visit, URIRef(CRM + "P4_has_time-span")))
    graph.add((visit, p14, timespan))
    conforms, _report = reasoning.validate_graph(graph)
    assert conforms is False
