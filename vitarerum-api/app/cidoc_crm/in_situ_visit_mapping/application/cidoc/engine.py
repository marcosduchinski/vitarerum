"""Config-driven CIDOC-CRM JSON-LD mapper for the InSituVisitRecord aggregate.

Framework-free (no FastAPI/SQLAlchemy). Targets the stable CIDOC-CRM 7.1.3 release (see
docs/cidoc_crm_version_7.1.3.docx): the visit time-span is declared via
``P170i_time_is_defined_by`` → an E61 Time Primitive literal (7.1.3 models declared
intervals with P170, not P82a/P82b). The official 7.1.3 JSON-LD context is bundled
(``cidoc_context_7.1.3.jsonld``) and inlined so each response is self-contained.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date
from importlib import resources
from typing import Any

from app.cidoc_crm.in_situ_visit_mapping.domain.models import InSituVisitRecord

_PACKAGE = "app.cidoc_crm.in_situ_visit_mapping.application.cidoc"
_MAPPING_FILE = "in_situ_visit_to_cidoc.json"
_CONTEXT_FILE = "cidoc_context_7.1.3.jsonld"

# Project-local prefixes layered on top of the official CIDOC-CRM 7.1.3 context
# (which already defines ``crm`` and every E/P term). Inlining the full context
# makes each response self-contained and offline-correct.
_LOCAL_PREFIXES = {
    "ex": "http://example.org/museum/",
    "dcterms": "http://purl.org/dc/terms/",
    "schema": "https://schema.org/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}


def _read_package_json(filename: str) -> dict[str, Any]:
    text = resources.files(_PACKAGE).joinpath(filename).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def load_mapping_definition() -> dict[str, Any]:
    """Load the bundled mapping JSON via importlib.resources (package data)."""
    return _read_package_json(_MAPPING_FILE)


def build_crm_context() -> dict[str, Any]:
    """The JSON-LD ``@context``: the bundled official 7.1.3 term map merged with
    the project-local prefixes."""
    official = _read_package_json(_CONTEXT_FILE)["@context"]
    return {**official, **_LOCAL_PREFIXES}


# ── primitives (ported) ────────────────────────────────────────────────────────


def normalize_identifier(value: str) -> str:
    if not value:
        return "unknown"
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return cleaned or "unknown"


def reference(node_id: str) -> dict[str, str]:
    return {"@id": node_id}


def make_labelled_node(
    node_id: str, node_type: str, label: str, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    node: dict[str, Any] = {"@id": node_id, "@type": node_type, "rdfs:label": label}
    if extra:
        node.update(extra)
    return node


def _set_predicate_value(node: dict[str, Any], predicate: str, value: Any) -> None:
    if predicate in node:
        current = node[predicate]
        if isinstance(current, list):
            current.append(value)
        else:
            node[predicate] = [current, value]
    else:
        node[predicate] = value


def _format(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _source_value(scope: Any, extras: dict[str, Any], field: str) -> Any:
    if field in extras:
        return extras[field]
    return getattr(scope, field)


def _resolve(scope: Any, extras: dict[str, Any], expression: str) -> str:
    """Resolve ``{field}``, ``{field|slug}``, ``{field|fallback}`` placeholders."""
    resolved = expression
    for match in re.finditer(r"{([^{}]+)}", expression):
        parts = match.group(1).split("|")
        value = _source_value(scope, extras, parts[0])
        if len(parts) > 1:
            modifier = parts[1]
            if modifier == "slug":
                value = normalize_identifier(_format(value))
            elif value in (None, ""):
                value = _source_value(scope, extras, modifier)
        if value is None:
            value = ""
        resolved = resolved.replace(match.group(0), _format(value))
    return resolved


def _should_generate(
    scope: Any, extras: dict[str, Any], definition: dict[str, Any]
) -> bool:
    when = definition.get("when")
    if when is None:
        return True
    value = _source_value(scope, extras, when["field"])
    policy = when.get("policy", "non_empty")
    if policy == "always":
        return True
    if policy == "non_null":
        return value is not None
    if policy == "non_empty":
        return value is not None and str(value).strip() != ""
    if policy == "truthy":
        return bool(value)
    raise ValueError(f"Unknown when policy: {policy}")


# ── value policies for field_mappings ──────────────────────────────────────────


def _policy_value(
    scope: Any, extras: dict[str, Any], field_mapping: dict[str, Any]
) -> Any:
    policy = field_mapping["value_policy"]
    if policy == "note_literal":
        return _source_value(scope, extras, field_mapping["source_field"])
    if policy == "declared_interval":
        begin = _format(_source_value(scope, extras, field_mapping["begin_field"]))
        end = _format(_source_value(scope, extras, field_mapping["end_field"]))
        return f"{begin}/{end}"
    raise ValueError(f"Unsupported value policy: {policy}")


def _apply_field_mappings(
    scope: Any,
    extras: dict[str, Any],
    node: dict[str, Any],
    field_mappings: list[dict[str, Any]],
) -> None:
    for fm in field_mappings:
        if not _should_generate(scope, extras, fm):
            continue
        value = _policy_value(scope, extras, fm)
        if value is None or (isinstance(value, str) and value == ""):
            continue
        _set_predicate_value(node, fm["predicate"], value)


# ── scalar singletons, vocabularies, links (ported) ────────────────────────────


def _build_scalar_nodes(
    record: InSituVisitRecord, mapping: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, dict[str, Any]]]:
    graph: list[dict[str, Any]] = []
    node_ids: dict[str, str] = {}
    nodes_by_key: dict[str, dict[str, Any]] = {}
    extras: dict[str, Any] = {}
    for definition in mapping["nodes"]:
        if not _should_generate(record, extras, definition):
            continue
        node_id = _resolve(record, extras, definition["id_template"])
        node = make_labelled_node(
            node_id=node_id,
            node_type=definition["type"],
            label=_resolve(record, extras, definition["label_template"]),
        )
        _apply_field_mappings(
            record, extras, node, definition.get("field_mappings", [])
        )
        node_ids[definition["key"]] = node_id
        nodes_by_key[definition["key"]] = node
        graph.append(node)
    return graph, node_ids, nodes_by_key


def _build_vocab_nodes(
    mapping: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    nodes: list[dict[str, Any]] = []
    vocab_ids: dict[str, str] = {}
    for vocab in mapping.get("vocabularies", []):
        nodes.append(make_labelled_node(vocab["id"], vocab["type"], vocab["label"]))
        vocab_ids[vocab["key"]] = vocab["id"]
    return nodes, vocab_ids


def _apply_links(
    mapping: dict[str, Any],
    node_ids: dict[str, str],
    nodes_by_key: dict[str, dict[str, Any]],
    vocab_ids: dict[str, str],
) -> None:
    for link in mapping.get("links", []):
        subject = nodes_by_key.get(link["subject"])
        if subject is None:
            continue
        if link.get("object_vocab"):
            target = vocab_ids.get(link["object_vocab"])
        else:
            target = node_ids.get(link.get("object", ""))
        if target is None:
            continue
        _set_predicate_value(subject, link["predicate"], reference(target))


# ── collection expansion (new) ─────────────────────────────────────────────────


def _link_node(
    visit_node: dict[str, Any],
    visit_id: str,
    item_node: dict[str, Any],
    item_id: str,
    link: dict[str, Any],
) -> None:
    if link["direction"] == "from_visit":
        _set_predicate_value(visit_node, link["predicate"], reference(item_id))
    else:  # to_visit
        _set_predicate_value(item_node, link["predicate"], reference(visit_id))


def _build_item_node(
    item: Any,
    extras: dict[str, Any],
    spec: dict[str, Any],
    vocab_ids: dict[str, str],
) -> dict[str, Any]:
    node = make_labelled_node(
        node_id=_resolve(item, extras, spec["id_template"]),
        node_type=spec["type"],
        label=_resolve(item, extras, spec["label_template"]),
    )
    type_vocab = spec.get("type_vocab")
    if type_vocab and type_vocab in vocab_ids:
        node["crm:P2_has_type"] = reference(vocab_ids[type_vocab])
    _apply_field_mappings(item, extras, node, spec.get("field_mappings", []))
    return node


def _build_attachment_nodes(
    item: Any,
    raw_visit_id: str,
    visit_id: str,
    parent_id: str,
    spec: dict[str, Any],
) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = []
    att_spec = spec["attachments"]
    extras = {"_visit_id": raw_visit_id, "_parent_id": parent_id}
    for attachment in getattr(item, att_spec["source_collection"]):
        att_id = _resolve(attachment, extras, att_spec["id_template"])
        extra: dict[str, Any] = {}
        content_field = att_spec.get("content_field")
        if content_field:
            value = getattr(attachment, content_field)
            if value:
                extra["schema:contentUrl"] = value
        node = make_labelled_node(
            node_id=att_id,
            node_type=att_spec["type"],
            label=_resolve(attachment, extras, att_spec["label_template"]),
            extra=extra,
        )
        predicate = att_spec["link"]["predicate"]
        _set_predicate_value(node, predicate, reference(parent_id))
        _set_predicate_value(node, predicate, reference(visit_id))
        graph.append(node)
    return graph


def _build_collection_nodes(
    record: InSituVisitRecord,
    mapping: dict[str, Any],
    visit_node: dict[str, Any],
    visit_id: str,
    vocab_ids: dict[str, str],
) -> list[dict[str, Any]]:
    graph: list[dict[str, Any]] = []
    for spec in mapping.get("collection_nodes", []):
        extras = {"_visit_id": record.id}
        for item in getattr(record, spec["source_collection"]):
            item_node = _build_item_node(item, extras, spec, vocab_ids)
            item_id = item_node["@id"]
            _link_node(visit_node, visit_id, item_node, item_id, spec["link"])
            graph.append(item_node)

            primary_id = item_id
            creates = spec.get("creates")
            if creates:
                created = _build_item_node(item, extras, creates["node"], vocab_ids)
                _set_predicate_value(
                    item_node, creates["predicate"], reference(created["@id"])
                )
                graph.append(created)
                primary_id = created["@id"]

            if "attachments" in spec:
                graph.extend(
                    _build_attachment_nodes(item, record.id, visit_id, primary_id, spec)
                )
    return graph


def _build_provenance(
    record: InSituVisitRecord, mapping: dict[str, Any]
) -> dict[str, Any]:
    meta = mapping.get("metadata", {})
    return {
        "@id": f"ex:graph/visit-{record.id}",
        "@type": "crm:E73_Information_Object",
        "rdfs:label": f"CIDOC CRM graph for visit {record.code}",
        "dcterms:conformsTo": {"@id": meta.get("crm_context_url", "")},
        "dcterms:creator": meta.get("institution", ""),
        "dcterms:created": record.generated_at.isoformat(),
        "ex:mapping_version": meta.get("mapping_version", ""),
        "ex:crm_version": meta.get("crm_version", ""),
    }


def map_record_to_cidoc(
    record: InSituVisitRecord, mapping: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build the CIDOC-CRM JSON-LD document for one visit record."""
    mapping = mapping or load_mapping_definition()
    graph, node_ids, nodes_by_key = _build_scalar_nodes(record, mapping)
    vocab_nodes, vocab_ids = _build_vocab_nodes(mapping)
    graph.extend(vocab_nodes)
    _apply_links(mapping, node_ids, nodes_by_key, vocab_ids)

    visit_id = node_ids["visit"]
    visit_node = nodes_by_key["visit"]
    graph.extend(
        _build_collection_nodes(record, mapping, visit_node, visit_id, vocab_ids)
    )
    graph.append(_build_provenance(record, mapping))
    return {"@context": build_crm_context(), "@graph": graph}
