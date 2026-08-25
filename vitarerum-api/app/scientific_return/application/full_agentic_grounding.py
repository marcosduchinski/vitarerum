from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from app.scientific_return.application.ports import (
    BibliographicRecord,
    BibliographicSourceCapabilities,
)
from app.scientific_return.domain.enums import (
    EvidenceSourceField,
    GroundedClaimKind,
    GroundingRejectionReason,
    InventoryEvidenceStatus,
)
from app.scientific_return.domain.full_agentic_models import (
    ArticleAssessment,
    GroundedArticleAssessment,
    GroundedInventoryForm,
    GroundingRejection,
)

_WHITESPACE = re.compile(r"\s+")
_EXCERPT_LIMIT = 120


def _normalise(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip().casefold()


def _excerpt(value: str) -> str:
    return " ".join(value.split())[:_EXCERPT_LIMIT]


def ground_article_assessment(
    assessment: ArticleAssessment,
    record: BibliographicRecord,
    capabilities: BibliographicSourceCapabilities | None,
) -> GroundedArticleAssessment:
    """Ground factual claims without changing the reader's relevance verdict."""

    fields = (
        (EvidenceSourceField.TITLE, record.title),
        (EvidenceSourceField.ABSTRACT, record.abstract or ""),
        (EvidenceSourceField.INDEXED_TEXT, record.indexed_text or ""),
    )
    normalised_fields = tuple((kind, _normalise(value)) for kind, value in fields)
    rejections: list[GroundingRejection] = []

    def keep(
        claims: tuple[str, ...], kind: GroundedClaimKind
    ) -> list[tuple[str, EvidenceSourceField]]:
        kept: list[tuple[str, EvidenceSourceField]] = []
        seen: set[str] = set()
        for claimed in claims:
            needle = _normalise(claimed)
            if not needle:
                rejections.append(
                    GroundingRejection(
                        kind, GroundingRejectionReason.EMPTY_CLAIM, _excerpt(claimed)
                    )
                )
                continue
            if needle in seen:
                rejections.append(
                    GroundingRejection(
                        kind,
                        GroundingRejectionReason.DUPLICATE_CLAIM,
                        _excerpt(claimed),
                    )
                )
                continue
            found = next(
                (field for field, content in normalised_fields if needle in content),
                None,
            )
            if found is None:
                rejections.append(
                    GroundingRejection(
                        kind,
                        GroundingRejectionReason.NOT_IN_DELIVERED_FIELDS,
                        _excerpt(claimed),
                    )
                )
                continue
            seen.add(needle)
            kept.append((claimed.strip(), found))
        return kept

    grounded_passages = tuple(
        text for text, _ in keep(assessment.passages, GroundedClaimKind.PASSAGE)
    )
    grounded_forms = tuple(
        GroundedInventoryForm(
            observed_form=text,
            source_field=field,
            source_locator=(
                record.indexed_text_source
                if field is EvidenceSourceField.INDEXED_TEXT
                else None
            ),
        )
        for text, field in keep(
            assessment.inventory_forms, GroundedClaimKind.INVENTORY_FORM
        )
    )

    # Absence only means "not observed" when the body the inventory code would
    # sit in was actually delivered. A source that returns metadata alone can
    # neither prove nor disprove the claim, so it reports UNAVAILABLE instead of
    # implying to the curator that the number is missing from the publication.
    inspected_body = bool(
        record.indexed_text
        and capabilities
        and capabilities.returns_inspectable_full_text
    )
    if grounded_forms:
        status = InventoryEvidenceStatus.VERIFIED
    elif inspected_body:
        status = InventoryEvidenceStatus.NOT_OBSERVED
    else:
        status = InventoryEvidenceStatus.UNAVAILABLE

    grounded_assessment = replace(
        assessment,
        passages=grounded_passages,
        inventory_forms=tuple(item.observed_form for item in grounded_forms),
    )
    return GroundedArticleAssessment(
        assessment=grounded_assessment,
        passages=grounded_passages,
        inventory_forms=grounded_forms,
        inventory_evidence_status=status,
        rejected_passages=len(assessment.passages) - len(grounded_passages),
        rejected_inventory_forms=len(assessment.inventory_forms) - len(grounded_forms),
        rejections=tuple(rejections),
    )
