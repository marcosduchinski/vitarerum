"""Lightweight content regression tests for the classification prompt.

These don't call a real model — they guard against silently reintroducing a
wording bug we found empirically: earlier phrasing ("extract any *specific*
object/specimen names") made llama3.1:8b skip general-category mentions (e.g.
a citizen asking about "lizards" with no named individual specimen), even
though such messages are exactly the kind of research request this pipeline
should flag as in-scope with an extractable object.
"""

from app.ai.museum_question_triage.application.prompts import (
    build_classification_system_prompt,
)


def test_classification_prompt_does_not_require_a_specific_named_specimen() -> None:
    prompt = build_classification_system_prompt()
    assert "extract any specific object" not in prompt.lower()
    assert "only extract object/specimen names" not in prompt.lower()


def test_classification_prompt_explicitly_allows_general_categories() -> None:
    prompt = build_classification_system_prompt()
    assert "general kind" in prompt or "general kind/category" in prompt
    assert "lizards" in prompt
