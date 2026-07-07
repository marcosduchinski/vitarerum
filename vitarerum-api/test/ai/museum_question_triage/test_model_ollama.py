import pytest

from app.ai.museum_question_triage.domain.models import (
    MentionedObject,
    TriageClassification,
)
from app.ai.museum_question_triage.domain.ports import ModelUnavailable
from app.ai.museum_question_triage.infrastructure.model_ollama import (
    _MentionedObjectSchema,
    _parse_classification,
    _TriageClassificationSchema,
)


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
            MentionedObject(
                english="Allende meteorite", portuguese="Meteorito Allende"
            )
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
    result = _parse_classification(
        {"is_visit_related": False, "mentioned_objects": []}
    )
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
