from app.scientific_return.application.full_agentic_grounding import (
    ground_article_assessment,
)
from app.scientific_return.application.ports import (
    BibliographicRecord,
    BibliographicSourceCapabilities,
)
from app.scientific_return.domain.enums import (
    AgentConfidence,
    EvidenceSourceField,
    GroundedClaimKind,
    GroundingRejectionReason,
    InventoryEvidenceStatus,
)
from app.scientific_return.domain.full_agentic_models import ArticleAssessment

_FULL_TEXT_SOURCE = BibliographicSourceCapabilities(
    name="EUROPE_PMC",
    searches_metadata=True,
    searches_indexed_full_text=True,
    returns_abstract=True,
    returns_inspectable_full_text=True,
    supports_structured_author=False,
)
_METADATA_SOURCE = BibliographicSourceCapabilities(
    name="OPENALEX",
    searches_metadata=True,
    searches_indexed_full_text=True,
    returns_abstract=True,
    returns_inspectable_full_text=False,
    supports_structured_author=True,
)


def _record(
    *,
    source: str = "EUROPE_PMC",
    title: str = "Study of specimen MB04-001066",
    abstract: str | None = None,
    indexed_text: str | None = None,
) -> BibliographicRecord:
    return BibliographicRecord(
        source=source,
        source_record_id="PMC1",
        title=title,
        authors=("P. Gomes",),
        publication_date="2025",
        abstract=abstract,
        url=None,
        doi=None,
        raw_metadata_hash="hash",
        indexed_text=indexed_text,
        indexed_text_source="OPEN_ACCESS_FULL_TEXT" if indexed_text else None,
    )


def _assessment(
    *, passages: tuple[str, ...], forms: tuple[str, ...]
) -> ArticleAssessment:
    return ArticleAssessment(
        relevant=True,
        confidence=AgentConfidence.HIGH,
        explanation="Semantically relevant",
        passages=passages,
        inventory_forms=forms,
        contradictions=(),
    )


def test_grounding_accepts_literal_form_in_title_without_full_text() -> None:
    grounded = ground_article_assessment(
        _assessment(
            passages=("Study of specimen MB04-001066",),
            forms=("MB04-001066",),
        ),
        _record(source="OPENALEX"),
        _METADATA_SOURCE,
    )

    assert grounded.inventory_evidence_status is InventoryEvidenceStatus.VERIFIED
    assert grounded.inventory_forms[0].source_field is EvidenceSourceField.TITLE
    assert grounded.rejected_inventory_forms == 0
    assert grounded.rejections == ()


def test_grounding_rejects_hallucinated_claims_without_changing_relevance() -> None:
    grounded = ground_article_assessment(
        _assessment(
            passages=("Invented exact quotation",),
            forms=("MUHNAC/MB99-999999",),
        ),
        _record(
            title="A taxonomic revision",
            abstract="No inventory number here.",
            indexed_text="Material examined: none catalogued.",
        ),
        _FULL_TEXT_SOURCE,
    )

    assert grounded.assessment.relevant is True
    assert grounded.passages == ()
    assert grounded.inventory_forms == ()
    assert grounded.inventory_evidence_status is InventoryEvidenceStatus.NOT_OBSERVED
    assert grounded.rejected_passages == 1
    assert grounded.rejected_inventory_forms == 1
    assert [
        (item.claim_kind, item.reason, item.excerpt) for item in grounded.rejections
    ] == [
        (
            GroundedClaimKind.PASSAGE,
            GroundingRejectionReason.NOT_IN_DELIVERED_FIELDS,
            "Invented exact quotation",
        ),
        (
            GroundedClaimKind.INVENTORY_FORM,
            GroundingRejectionReason.NOT_IN_DELIVERED_FIELDS,
            "MUHNAC/MB99-999999",
        ),
    ]


def test_grounding_normalises_unicode_and_whitespace_but_not_punctuation() -> None:
    grounded = ground_article_assessment(
        _assessment(
            passages=("Material  examined: MB11-001283",),
            forms=("MB11-001283", "MB11:001283"),
        ),
        _record(indexed_text="Material  examined: MB11-001283"),
        _FULL_TEXT_SOURCE,
    )

    assert [item.observed_form for item in grounded.inventory_forms] == ["MB11-001283"]
    assert grounded.passages == ("Material  examined: MB11-001283",)
    assert grounded.rejected_inventory_forms == 1
    assert grounded.rejections[0].reason is (
        GroundingRejectionReason.NOT_IN_DELIVERED_FIELDS
    )


def test_a_repeated_claim_is_grounded_once_and_reported_as_duplicate() -> None:
    grounded = ground_article_assessment(
        _assessment(
            passages=(),
            forms=("MB04-001066", "mb04-001066  "),
        ),
        _record(abstract="Specimen MB04-001066 was re-examined."),
        _FULL_TEXT_SOURCE,
    )

    assert len(grounded.inventory_forms) == 1
    assert grounded.inventory_forms[0].source_field is EvidenceSourceField.TITLE
    assert grounded.rejections[0].reason is GroundingRejectionReason.DUPLICATE_CLAIM


def test_an_empty_claim_is_rejected_with_its_own_reason() -> None:
    grounded = ground_article_assessment(
        _assessment(passages=("   ",), forms=()),
        _record(indexed_text="Material examined: MB04-001066"),
        _FULL_TEXT_SOURCE,
    )

    assert grounded.passages == ()
    assert grounded.rejections[0].reason is GroundingRejectionReason.EMPTY_CLAIM


def test_inspected_full_text_without_the_form_is_not_observed() -> None:
    grounded = ground_article_assessment(
        _assessment(passages=(), forms=()),
        _record(title="A revision", indexed_text="Material examined: none."),
        _FULL_TEXT_SOURCE,
    )

    assert grounded.inventory_evidence_status is InventoryEvidenceStatus.NOT_OBSERVED


def test_a_source_without_inspectable_body_reports_unavailable() -> None:
    grounded = ground_article_assessment(
        _assessment(passages=(), forms=()),
        _record(source="OPENALEX", title="A revision", abstract="No number here."),
        _METADATA_SOURCE,
    )

    assert grounded.inventory_evidence_status is InventoryEvidenceStatus.UNAVAILABLE


def test_full_text_capability_without_delivered_body_is_unavailable() -> None:
    grounded = ground_article_assessment(
        _assessment(passages=(), forms=()),
        _record(title="A revision", abstract="Closed access abstract."),
        _FULL_TEXT_SOURCE,
    )

    assert grounded.inventory_evidence_status is InventoryEvidenceStatus.UNAVAILABLE


def test_an_unknown_source_never_claims_the_body_was_inspected() -> None:
    grounded = ground_article_assessment(
        _assessment(passages=(), forms=()),
        _record(indexed_text="Material examined: none."),
        None,
    )

    assert grounded.inventory_evidence_status is InventoryEvidenceStatus.UNAVAILABLE
