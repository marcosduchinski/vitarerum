import pytest

from app.ai.museum_question_triage.domain.models import (
    ClassificationOutcome,
    ClassificationScoreSource,
    MentionedObject,
    TriageClassification,
    UseCategory,
    UseCategoryClassification,
    UseCategoryScore,
)
from app.ai.museum_question_triage.domain.ports import ModelUnavailable
from app.ai.museum_question_triage.infrastructure.model_ollama import (
    _is_ollama_response_error,
    _json_object_from_text,
    _MentionedObjectSchema,
    _parse_classification,
    _parse_use_category_classification,
    _TriageClassificationSchema,
    _UseCategoryClassificationSchema,
    _UseCategoryScoreSchema,
)


def test_identifies_ollama_response_error() -> None:
    response_error = type(
        "ResponseError",
        (Exception,),
        {"__module__": "ollama._types"},
    )

    assert _is_ollama_response_error(response_error("model unavailable"))


def test_does_not_identify_other_response_error() -> None:
    response_error = type(
        "ResponseError",
        (Exception,),
        {"__module__": "some_other_client"},
    )

    assert not _is_ollama_response_error(response_error("different client"))


def test_extracts_json_object_from_plain_json_text() -> None:
    assert _json_object_from_text('{"is_visit_related": true}') == {
        "is_visit_related": True
    }


def test_extracts_json_object_from_markdown_fence() -> None:
    assert _json_object_from_text(
        '```json\n{"is_visit_related": false, "mentioned_objects": []}\n```'
    ) == {"is_visit_related": False, "mentioned_objects": []}


def test_extracts_json_object_embedded_in_text() -> None:
    assert _json_object_from_text(
        'Here is the result: {"is_visit_related": true, "mentioned_objects": []}'
    ) == {"is_visit_related": True, "mentioned_objects": []}


def test_parses_a_valid_schema_instance() -> None:
    schema = _TriageClassificationSchema(
        is_visit_related=True,
        mentioned_objects=[
            _MentionedObjectSchema(
                english="Allende meteorite", portuguese="Meteorito Allende"
            )
        ],
    )
    result = _parse_classification(schema)
    assert result == TriageClassification(
        is_visit_related=True,
        mentioned_objects=[
            MentionedObject(english="Allende meteorite", portuguese="Meteorito Allende")
        ],
    )


def test_parses_a_plain_dict() -> None:
    result = _parse_classification(
        {
            "is_visit_related": False,
            "mentioned_objects": [
                {"english": "Whale skeleton", "portuguese": "Esqueleto de baleia"}
            ],
        }
    )
    assert result == TriageClassification(
        is_visit_related=False,
        mentioned_objects=[
            MentionedObject(english="Whale skeleton", portuguese="Esqueleto de baleia")
        ],
    )


def test_empty_mentioned_objects_is_valid() -> None:
    result = _parse_classification({"is_visit_related": False, "mentioned_objects": []})
    assert result == TriageClassification(is_visit_related=False, mentioned_objects=[])


def test_missing_required_field_raises_model_unavailable() -> None:
    with pytest.raises(ModelUnavailable):
        _parse_classification({"mentioned_objects": []})


def test_wrong_type_raises_model_unavailable() -> None:
    with pytest.raises(ModelUnavailable):
        _parse_classification({"is_visit_related": "not-a-bool"})


def test_malformed_mentioned_object_entry_raises_model_unavailable() -> None:
    with pytest.raises(ModelUnavailable):
        _parse_classification(
            {
                "is_visit_related": True,
                # missing the required "portuguese" field
                "mentioned_objects": [{"english": "Whale skeleton"}],
            }
        )


def test_completely_unstructured_output_raises_model_unavailable() -> None:
    with pytest.raises(ModelUnavailable):
        _parse_classification("free text the model returned instead of JSON")


def test_parses_use_category_classification_schema_instance() -> None:
    score = _UseCategoryScoreSchema(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.91,
        source=ClassificationScoreSource.LLM,
    )
    schema = _UseCategoryClassificationSchema(
        outcome=ClassificationOutcome.CATEGORIZED,
        category_scores=[score],
        assigned_categories=[score],
    )

    result = _parse_use_category_classification(schema)

    expected_score = UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.91,
        source=ClassificationScoreSource.LLM,
    )
    assert result == UseCategoryClassification(
        outcome=ClassificationOutcome.CATEGORIZED,
        category_scores=[expected_score],
        assigned_categories=[expected_score],
    )


def test_parses_unclear_use_category_classification() -> None:
    result = _parse_use_category_classification(
        {
            "outcome": "UNCLEAR",
            "category_scores": [],
            "assigned_categories": [],
        }
    )

    assert result == UseCategoryClassification(
        outcome=ClassificationOutcome.UNCLEAR,
        category_scores=[],
        assigned_categories=[],
    )


def test_use_category_classification_rejects_unclear_with_assigned_category() -> None:
    score = {
        "category": "RESEARCH_PROJECTS",
        "confidence": 0.91,
        "source": "LLM",
    }

    with pytest.raises(ModelUnavailable):
        _parse_use_category_classification(
            {
                "outcome": "UNCLEAR",
                "category_scores": [score],
                "assigned_categories": [score],
            }
        )


def test_use_category_classification_discards_invented_categories() -> None:
    result = _parse_use_category_classification(
        {
            "outcome": "CATEGORIZED",
            "category_scores": [
                {
                    "category": "MADE_UP_CATEGORY",
                    "confidence": 0.99,
                    "source": "LLM",
                },
                {
                    "category": "RESEARCH_PROJECTS",
                    "confidence": 0.8,
                    "source": "LLM",
                },
            ],
            "assigned_categories": [
                {
                    "category": "MADE_UP_CATEGORY",
                    "confidence": 0.99,
                    "source": "LLM",
                },
                {
                    "category": "RESEARCH_PROJECTS",
                    "confidence": 0.8,
                    "source": "LLM",
                },
            ],
        }
    )

    expected_score = UseCategoryScore(
        category=UseCategory.RESEARCH_PROJECTS,
        confidence=0.8,
        source=ClassificationScoreSource.LLM,
    )
    assert result == UseCategoryClassification(
        outcome=ClassificationOutcome.CATEGORIZED,
        category_scores=[expected_score],
        assigned_categories=[expected_score],
    )


def test_rejects_categorized_with_only_invented_category() -> None:
    with pytest.raises(ModelUnavailable):
        _parse_use_category_classification(
            {
                "outcome": "CATEGORIZED",
                "category_scores": [
                    {
                        "category": "MADE_UP_CATEGORY",
                        "confidence": 0.8,
                        "source": "LLM",
                    }
                ],
                "assigned_categories": [
                    {
                        "category": "MADE_UP_CATEGORY",
                        "confidence": 0.8,
                        "source": "LLM",
                    }
                ],
            }
        )


def test_use_category_classification_rejects_confidence_outside_range() -> None:
    with pytest.raises(ModelUnavailable):
        _parse_use_category_classification(
            {
                "outcome": "CATEGORIZED",
                "category_scores": [
                    {
                        "category": "RESEARCH_PROJECTS",
                        "confidence": 1.2,
                        "source": "LLM",
                    }
                ],
                "assigned_categories": [
                    {
                        "category": "RESEARCH_PROJECTS",
                        "confidence": 1.2,
                        "source": "LLM",
                    }
                ],
            }
        )


def test_use_category_classification_rejects_assigned_score_divergence() -> None:
    with pytest.raises(ModelUnavailable):
        _parse_use_category_classification(
            {
                "outcome": "CATEGORIZED",
                "category_scores": [
                    {
                        "category": "RESEARCH_PROJECTS",
                        "confidence": 0.91,
                        "source": "LLM",
                    }
                ],
                "assigned_categories": [
                    {
                        "category": "RESEARCH_PROJECTS",
                        "confidence": 0.8,
                        "source": "LLM",
                    }
                ],
            }
        )


def test_use_category_classification_sorts_scores_deterministically() -> None:
    result = _parse_use_category_classification(
        {
            "outcome": "CATEGORIZED",
            "category_scores": [
                {
                    "category": "FILMING",
                    "confidence": 0.7,
                    "source": "LLM",
                },
                {
                    "category": "RESEARCH_PROJECTS",
                    "confidence": 0.91,
                    "source": "LLM",
                },
                {
                    "category": "EXHIBITION",
                    "confidence": 0.91,
                    "source": "LLM",
                },
            ],
            "assigned_categories": [
                {
                    "category": "FILMING",
                    "confidence": 0.7,
                    "source": "LLM",
                },
                {
                    "category": "RESEARCH_PROJECTS",
                    "confidence": 0.91,
                    "source": "LLM",
                },
                {
                    "category": "EXHIBITION",
                    "confidence": 0.91,
                    "source": "LLM",
                },
            ],
        }
    )

    assert [score.category for score in result.category_scores] == [
        UseCategory.EXHIBITION,
        UseCategory.RESEARCH_PROJECTS,
        UseCategory.FILMING,
    ]
    assert [score.category for score in result.assigned_categories] == [
        UseCategory.EXHIBITION,
        UseCategory.RESEARCH_PROJECTS,
        UseCategory.FILMING,
    ]
