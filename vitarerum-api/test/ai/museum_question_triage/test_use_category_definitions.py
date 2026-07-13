from app.ai.museum_question_triage.domain.models import (
    ClassificationScoreSource,
    TriageVerdict,
    UseCategory,
    UseCategoryScore,
)
from app.ai.museum_question_triage.domain.use_category_definitions import (
    USE_CATEGORY_DEFINITIONS,
    CatalogueSearchPolicy,
    derived_scope_from_categories,
    should_search_catalogue_for_categories,
)


def _score(category: UseCategory) -> UseCategoryScore:
    return UseCategoryScore(
        category=category,
        confidence=0.9,
        source=ClassificationScoreSource.EMBEDDING,
    )


def test_every_use_category_has_a_static_definition() -> None:
    assert set(USE_CATEGORY_DEFINITIONS) == set(UseCategory)


def test_derived_scope_is_in_scope_when_any_category_is_collection_use() -> None:
    result = derived_scope_from_categories(
        [_score(UseCategory.EXHIBITION), _score(UseCategory.RESEARCH_PROJECTS)]
    )

    assert result is TriageVerdict.IN_SCOPE


def test_derived_scope_is_out_of_scope_without_collection_use_categories() -> None:
    result = derived_scope_from_categories(
        [_score(UseCategory.EXHIBITION), _score(UseCategory.FILMING)]
    )

    assert result is TriageVerdict.OUT_OF_SCOPE


def test_research_projects_always_search_catalogue() -> None:
    assert should_search_catalogue_for_categories(
        [_score(UseCategory.RESEARCH_PROJECTS)], mentioned_object_count=0
    )


def test_answering_enquiries_searches_only_when_objects_are_mentioned() -> None:
    assert not should_search_catalogue_for_categories(
        [_score(UseCategory.ANSWERING_ENQUIRIES)], mentioned_object_count=0
    )
    assert should_search_catalogue_for_categories(
        [_score(UseCategory.ANSWERING_ENQUIRIES)], mentioned_object_count=1
    )


def test_never_policy_does_not_search_even_with_mentioned_objects() -> None:
    assert (
        USE_CATEGORY_DEFINITIONS[UseCategory.EXHIBITION].catalogue_search_policy
        is CatalogueSearchPolicy.NEVER
    )
    assert not should_search_catalogue_for_categories(
        [_score(UseCategory.EXHIBITION)], mentioned_object_count=2
    )
