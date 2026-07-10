"""Human-readable description of the catalogue search strategy, surfaced to
staff alongside triage results (docs/plans/museum-questions-ai-triage-
refinements-plan.md, checkpoint 3 — "estratégia de busca").

Kept as a fixed constant here, rather than fetched dynamically from
``collection_object_index``, to avoid coupling this bounded context to that
one's internal similarity threshold. Trade-off accepted for this MVP: this
text can drift out of sync if the threshold in
``app/collection_object_index/infrastructure/repositories.py``
(``_WORD_SIMILARITY_THRESHOLD``) changes without updating it here.
"""

from __future__ import annotations

SEARCH_STRATEGY_DESCRIPTION = (
    "Correspondência aproximada por similaridade textual (não é busca exata)."
)
