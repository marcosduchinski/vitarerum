import json
from datetime import date

import pytest

from app.cidoc_crm.in_situ_visit_mapping.application.cidoc.engine import (
    map_record_to_cidoc,
)
from app.cidoc_crm.in_situ_visit_mapping.application.use_cases import (
    BuildInSituVisitCidoc,
    BuildInSituVisitCidocInput,
    InSituVisitRecordNotFound,
)
from app.cidoc_crm.in_situ_visit_mapping.domain.models import (
    AttachmentData,
    ChildData,
    InSituVisitId,
    InSituVisitRecord,
)


def _sample_record() -> InSituVisitRecord:
    return InSituVisitRecord.create(
        code="VS-0001",
        visit_begin_date=date(2026, 6, 19),
        visit_end_date=date(2026, 6, 20),
        visitor_name="Maria do Rosário",
        place_name="MUSEU",
        requested_objects=[ChildData("XL01", "lupus lupus", 1)],
        in_situ_occurrences=[
            ChildData(
                "OC-10",
                "Ocorrencia",
                0,
                [AttachmentData("DOC", "foto", "foto.jpeg", 0)],
            )
        ],
        in_situ_logs=[
            ChildData(
                "LOG01",
                "logou algo",
                0,
                [AttachmentData("loga01", "log", "log-ref", 0)],
            )
        ],
        in_situ_publications=[
            ChildData(
                "PUCos",
                "MARIA S.",
                0,
                [AttachmentData("publ", "paper", "Teste", 0)],
            )
        ],
    )


def _types(graph: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in graph:
        counts[node["@type"]] = counts.get(node["@type"], 0) + 1
    return counts


def test_full_expansion_emits_a_node_per_child() -> None:
    doc = map_record_to_cidoc(_sample_record())
    counts = _types(doc["@graph"])

    # visit + one occurrence sub-event are both E7_Activity
    assert counts["crm:E7_Activity"] == 2
    assert counts["crm:E21_Person"] == 1
    assert counts["crm:E53_Place"] == 1
    assert counts["crm:E52_Time-Span"] == 1
    assert counts["crm:E20_Biological_Object"] == 1
    assert counts["crm:E65_Creation"] == 1
    # publication's created Information Object + the provenance graph node
    assert counts["crm:E73_Information_Object"] == 2
    # one log + three attachments
    assert counts["crm:E31_Document"] == 4


def test_timespan_uses_p170_not_p82() -> None:
    doc = map_record_to_cidoc(_sample_record())
    timespan = next(
        n for n in doc["@graph"] if n["@type"] == "crm:E52_Time-Span"
    )
    # The term name must match the official 7.1.3 context exactly.
    assert timespan["crm:P170i_time_is_defined_by"] == "2026-06-19/2026-06-20"
    # 7.1.3's definition models declared intervals with P170, not P82a/P82b.
    assert "P82" not in json.dumps(doc["@graph"])


def test_context_is_inlined_official_713_plus_local_prefixes() -> None:
    context = map_record_to_cidoc(_sample_record())["@context"]
    # The official CIDOC-CRM namespace and core terms are present.
    assert context["crm"] == "http://www.cidoc-crm.org/cidoc-crm/"
    assert context["P170i_time_is_defined_by"]["@id"] == "crm:P170i_time_is_defined_by"
    # Project-local prefixes are layered on top.
    assert context["ex"] == "http://example.org/museum/"
    assert "schema" in context and "dcterms" in context


def test_targets_cidoc_713() -> None:
    doc = map_record_to_cidoc(_sample_record())
    provenance = next(
        n for n in doc["@graph"] if n["@id"].startswith("ex:graph/")
    )
    assert provenance["ex:crm_version"] == "7.1.3"


def test_attachments_carry_content_url() -> None:
    doc = map_record_to_cidoc(_sample_record())
    urls = {
        n["schema:contentUrl"] for n in doc["@graph"] if "schema:contentUrl" in n
    }
    assert urls == {"foto.jpeg", "log-ref", "Teste"}


def test_attachments_carry_description_as_note() -> None:
    doc = map_record_to_cidoc(_sample_record())
    attachment_notes = {
        n["crm:P3_has_note"]
        for n in doc["@graph"]
        if n["@id"].startswith("ex:document/")
        and n["@id"].find("-attachment/") != -1
    }
    assert attachment_notes == {"foto", "log", "paper"}


def test_visit_links_to_actor_place_timespan_and_type() -> None:
    doc = map_record_to_cidoc(_sample_record())
    visit = next(
        n
        for n in doc["@graph"]
        if n["@type"] == "crm:E7_Activity" and n["@id"].startswith("ex:visit/")
    )
    assert "crm:P14_carried_out_by" in visit
    assert "crm:P7_took_place_at" in visit
    assert "crm:P4_has_time-span" in visit
    assert visit["crm:P2_has_type"] == {"@id": "ex:type/in-situ-visit"}


def test_occurrence_and_log_link_to_related_object_when_present() -> None:
    record = InSituVisitRecord.create(
        code="VS-0002",
        visit_begin_date=date(2026, 6, 19),
        visit_end_date=date(2026, 6, 20),
        visitor_name="Maria do Rosário",
        place_name="MUSEU",
        requested_objects=[ChildData("XL01", "lupus lupus", 1)],
        in_situ_occurrences=[
            ChildData(
                "OC-10",
                "o objeto caiu da mesa",
                0,
                related_object_source_id="XL01",
            )
        ],
        in_situ_logs=[
            ChildData("LOG01", "detalhes finos", 0, related_object_source_id="XL01"),
            ChildData("LOG02", "sem objeto associado", 1),
        ],
    )
    doc = map_record_to_cidoc(record)
    object_id = next(
        n["@id"] for n in doc["@graph"] if n["@type"] == "crm:E20_Biological_Object"
    )

    occurrence = next(n for n in doc["@graph"] if n["@id"].startswith("ex:occurrence/"))
    # E7_Activity → E70_Thing: correct CRM domain/range for P16.
    assert occurrence["crm:P16_used_specific_object"] == {"@id": object_id}

    log_with_object = next(
        n for n in doc["@graph"] if n.get("rdfs:label") == "LOG01"
    )
    # E31_Document → E1_CRM_Entity: P129 (not P16) since a document isn't an
    # activity that "used" the object, it's just about it.
    assert log_with_object["crm:P129_is_about"] == {"@id": object_id}

    log_without_object = next(
        n for n in doc["@graph"] if n.get("rdfs:label") == "LOG02"
    )
    assert "crm:P129_is_about" not in log_without_object


def test_publication_information_object_links_to_related_object_when_present() -> None:
    record = InSituVisitRecord.create(
        code="VS-0003",
        visit_begin_date=date(2026, 6, 19),
        visit_end_date=date(2026, 6, 20),
        visitor_name="Maria do Rosário",
        place_name="MUSEU",
        requested_objects=[ChildData("XL01", "lupus lupus", 1)],
        in_situ_publications=[
            ChildData(
                "PUB01",
                "Heyning & Dahlheim, Orcinus orca",
                0,
                related_object_source_id="XL01",
            )
        ],
    )
    doc = map_record_to_cidoc(record)
    object_id = next(
        n["@id"] for n in doc["@graph"] if n["@type"] == "crm:E20_Biological_Object"
    )

    creation = next(n for n in doc["@graph"] if n["@type"] == "crm:E65_Creation")
    information_object = next(
        n for n in doc["@graph"] if n["@id"].startswith("ex:information/")
    )
    # The link belongs on the E73 Information Object (E89 Propositional Object),
    # not the E65 Creation event — P129's domain wouldn't accept the latter.
    assert "crm:P129_is_about" not in creation
    assert information_object["crm:P129_is_about"] == {"@id": object_id}


def test_attachments_link_to_related_object_when_parent_has_one() -> None:
    record = InSituVisitRecord.create(
        code="VS-0004",
        visit_begin_date=date(2026, 6, 19),
        visit_end_date=date(2026, 6, 20),
        visitor_name="Maria do Rosário",
        place_name="MUSEU",
        requested_objects=[ChildData("XL01", "Aguia-calçada", 1)],
        in_situ_occurrences=[
            ChildData(
                "OC-10",
                "observacao",
                0,
                [AttachmentData("IMG01", "fotografia dorsal da ave", "aguia.png", 0)],
                related_object_source_id="XL01",
            )
        ],
    )
    doc = map_record_to_cidoc(record)
    object_id = next(
        n["@id"] for n in doc["@graph"] if n["@type"] == "crm:E20_Biological_Object"
    )
    attachment = next(
        n
        for n in doc["@graph"]
        if n["@id"].startswith("ex:document/occurrence-attachment/")
    )

    assert attachment["crm:P3_has_note"] == "fotografia dorsal da ave"
    assert attachment["crm:P129_is_about"] == {"@id": object_id}


class _StubRepo:
    def __init__(self, record: InSituVisitRecord | None) -> None:
        self._record = record

    async def add(self, record: InSituVisitRecord) -> None:  # pragma: no cover
        raise NotImplementedError

    async def get_by_id(self, record_id: InSituVisitId) -> InSituVisitRecord | None:
        return self._record

    async def list(self, page: int, size: int):  # pragma: no cover
        raise NotImplementedError


async def test_use_case_returns_jsonld_for_existing_record() -> None:
    record = _sample_record()
    use_case = BuildInSituVisitCidoc(_StubRepo(record))
    doc = await use_case.execute(BuildInSituVisitCidocInput(record_id=record.id))
    assert doc["@graph"]
    assert doc["@context"]


async def test_use_case_raises_when_record_missing() -> None:
    use_case = BuildInSituVisitCidoc(_StubRepo(None))
    with pytest.raises(InSituVisitRecordNotFound):
        await use_case.execute(BuildInSituVisitCidocInput(record_id="missing"))
