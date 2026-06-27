"""RDF reasoning + SHACL validation for the CIDOC-CRM graph (KG-RAG Phase 2).

Library-only (rdflib / owlrl / pyshacl) — no FastAPI/SQLAlchemy, so it stays
within the application layer's purity contract. Expands the JSON-LD with RDFS/
OWL-RL closure (subclass inheritance, transitive properties), then validates it
against the bundled CIDOC-CRM domain/range shapes.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from rdflib import Graph

_PACKAGE = "app.cidoc_crm.in_situ_visit_mapping.application.cidoc"
_SHAPES = "shapes/in_situ_visit_shapes.ttl"
_HIERARCHY = "shapes/crm_hierarchy.ttl"


def _load_ttl(filename: str) -> Graph:
    text = resources.files(_PACKAGE).joinpath(filename).read_text(encoding="utf-8")
    return Graph().parse(data=text, format="turtle")


def to_graph(doc: dict[str, Any]) -> Graph:
    """Parse a JSON-LD document into an RDF graph."""
    return Graph().parse(data=json.dumps(doc), format="json-ld")


def expand_graph(doc: dict[str, Any]) -> Graph:
    """Parse the JSON-LD and apply RDFS/OWL-RL closure using the bundled CRM
    class hierarchy (materialises subclass/transitive inferences)."""
    from owlrl import DeductiveClosure, RDFS_Semantics

    graph = to_graph(doc)
    graph += _load_ttl(_HIERARCHY)
    DeductiveClosure(RDFS_Semantics).expand(graph)
    return graph


def validate_graph(graph: Graph) -> tuple[bool, str]:
    """Validate a (preferably expanded) graph against the CIDOC-CRM shapes."""
    from pyshacl import validate

    conforms, _, report = validate(
        graph,
        shacl_graph=_load_ttl(_SHAPES),
        ont_graph=_load_ttl(_HIERARCHY),
        inference="rdfs",
    )
    return bool(conforms), str(report)


def to_jsonld(graph: Graph) -> dict[str, Any]:
    """Serialise an RDF graph back to a JSON-LD document (for the LLM payload)."""
    data: Any = json.loads(graph.serialize(format="json-ld"))
    return {"@graph": data} if isinstance(data, list) else data
