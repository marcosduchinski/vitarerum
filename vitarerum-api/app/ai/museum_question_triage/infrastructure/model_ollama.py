"""Local LLM adapter implementing ``TriageModelPort`` via Ollama.

Heavy imports (langchain-ollama / httpx) are loaded lazily inside each method
so the module imports without the model stack and unit tests can substitute a
fake port. ``classify`` uses structured output (a pydantic schema) so the
in/out-of-scope decision and the extracted object names come back as reliable
data rather than free text — the one deliberate deviation from
``app.ai.museum_narrative``'s single ``generate() -> str`` port.

Failure mapping:
- connection failures                → ModelUnavailable  (503)
- timeouts / slow responses           → ModelTimeout      (504)
- malformed/invalid structured output → ModelUnavailable  (503)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.ai.museum_question_triage.domain.models import (
    ClassificationOutcome,
    ClassificationScoreSource,
    InvalidMessageClassification,
    MentionedObject,
    TriageClassification,
    UseCategory,
    UseCategoryClassification,
    UseCategoryScore,
)
from app.ai.museum_question_triage.domain.ports import ModelTimeout, ModelUnavailable

_CLASSIFICATION_TEMPERATURE = 0.0
_REPLY_TEMPERATURE = 0.3
logger = logging.getLogger(__name__)


def _is_ollama_response_error(exc: BaseException) -> bool:
    exc_type = type(exc)
    return (
        exc_type.__name__ == "ResponseError"
        and exc_type.__module__.split(".", maxsplit=1)[0] == "ollama"
    )


class _MentionedObjectSchema(BaseModel):
    english: str = Field(description="The object/specimen name in English.")
    portuguese: str = Field(description="The object/specimen name in Portuguese.")


class _TriageClassificationSchema(BaseModel):
    is_visit_related: bool = Field(
        description=(
            "True if the message is in scope per the stated rule (collection "
            "use / in-situ investigation visit); false otherwise."
        )
    )
    mentioned_objects: list[_MentionedObjectSchema] = Field(
        default_factory=list,
        description=(
            "Specific object/specimen names explicitly named in the message, "
            "each given in both English and Portuguese. Empty list if none "
            "are named."
        ),
    )


class _UseCategoryScoreSchema(BaseModel):
    category: str = Field(description="One allowed Spectrum use category.")
    confidence: float = Field(
        ge=0,
        le=1,
        description="Model confidence from 0 to 1.",
    )
    source: ClassificationScoreSource = Field(
        description="Always LLM for Fase 0 use-category classification."
    )


class _UseCategoryClassificationSchema(BaseModel):
    outcome: ClassificationOutcome = Field(
        description="CATEGORIZED when at least one category applies; otherwise UNCLEAR."
    )
    category_scores: list[_UseCategoryScoreSchema] = Field(default_factory=list)
    assigned_categories: list[_UseCategoryScoreSchema] = Field(default_factory=list)


def _json_object_from_text(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(candidate[start : end + 1])

    if not isinstance(data, dict):
        raise TypeError("Expected a JSON object.")
    return data


def _parse_classification(result: Any) -> TriageClassification:
    """Validate the model's structured output, mapping any malformed/
    unexpected shape to :class:`ModelUnavailable` instead of letting a
    ``ValidationError`` escape as an unhandled 500. Kept as a plain function
    (no ``ChatOllama`` involved) so malformed-output cases are unit-testable
    without mocking the LLM client, per this repo's testing convention."""
    try:
        schema = (
            result
            if isinstance(result, _TriageClassificationSchema)
            else _TriageClassificationSchema.model_validate(result)
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise ModelUnavailable(
            "The triage model returned an invalid structured response"
        ) from exc
    return TriageClassification(
        is_visit_related=schema.is_visit_related,
        mentioned_objects=[
            MentionedObject(english=obj.english, portuguese=obj.portuguese)
            for obj in schema.mentioned_objects
        ],
    )


def _score_from_schema(score: _UseCategoryScoreSchema) -> UseCategoryScore | None:
    try:
        category = UseCategory(score.category)
    except ValueError:
        return None
    return UseCategoryScore(
        category=category,
        confidence=score.confidence,
        source=score.source,
    )


def _valid_scores_from_schema(
    scores: list[_UseCategoryScoreSchema],
) -> list[UseCategoryScore]:
    valid_scores: list[UseCategoryScore] = []
    for score in scores:
        parsed = _score_from_schema(score)
        if parsed is not None:
            valid_scores.append(parsed)
    return valid_scores


def _parse_use_category_classification(result: Any) -> UseCategoryClassification:
    try:
        schema = (
            result
            if isinstance(result, _UseCategoryClassificationSchema)
            else _UseCategoryClassificationSchema.model_validate(result)
        )
        return UseCategoryClassification(
            outcome=schema.outcome,
            category_scores=_valid_scores_from_schema(schema.category_scores),
            assigned_categories=_valid_scores_from_schema(schema.assigned_categories),
        )
    except (
        InvalidMessageClassification,
        ValidationError,
        ValueError,
        TypeError,
    ) as exc:
        raise ModelUnavailable(
            "The triage model returned an invalid use-category response"
        ) from exc


class OllamaTriageAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        api_key: str = "",
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._api_key = api_key

    def _client_kwargs(self) -> dict[str, object]:
        client_kwargs: dict[str, object] = {"timeout": self._timeout_seconds}
        if self._api_key:
            client_kwargs["headers"] = {"Authorization": f"Bearer {self._api_key}"}
        return client_kwargs

    async def _classify_with_json_fallback(self, message: str) -> TriageClassification:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama

        from app.ai.museum_question_triage.application.prompts import (
            build_classification_system_prompt,
            build_classification_user_prompt,
        )

        chat = ChatOllama(
            base_url=self._base_url,
            model=self._model,
            temperature=_CLASSIFICATION_TEMPERATURE,
            client_kwargs=self._client_kwargs(),
        )
        response = await chat.ainvoke(
            [
                SystemMessage(
                    content=(
                        f"{build_classification_system_prompt()}\n\n"
                        "Return valid JSON only, with no Markdown and no prose. "
                        "The JSON object must have exactly this shape: "
                        '{"is_visit_related": boolean, "mentioned_objects": '
                        '[{"english": string, "portuguese": string}]}.'
                    )
                ),
                HumanMessage(content=build_classification_user_prompt(message)),
            ]
        )
        try:
            return _parse_classification(_json_object_from_text(str(response.content)))
        except (json.JSONDecodeError, ModelUnavailable, TypeError) as exc:
            raise ModelUnavailable(
                "The triage model returned an invalid structured response"
            ) from exc

    async def _classify_use_categories_with_json_fallback(
        self, message: str
    ) -> UseCategoryClassification:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama

        from app.ai.museum_question_triage.application.prompts import (
            build_use_category_classification_system_prompt,
            build_use_category_classification_user_prompt,
        )

        chat = ChatOllama(
            base_url=self._base_url,
            model=self._model,
            temperature=_CLASSIFICATION_TEMPERATURE,
            client_kwargs=self._client_kwargs(),
        )
        response = await chat.ainvoke(
            [
                SystemMessage(
                    content=(
                        f"{build_use_category_classification_system_prompt()}\n\n"
                        "Return valid JSON only, with no Markdown and no prose. "
                        "Use exactly this shape: "
                        '{"outcome": "CATEGORIZED"|"UNCLEAR", '
                        '"category_scores": [{"category": string, '
                        '"confidence": number, "source": "LLM"}], '
                        '"assigned_categories": [{"category": string, '
                        '"confidence": number, "source": "LLM"}]}.'
                    )
                ),
                HumanMessage(
                    content=build_use_category_classification_user_prompt(message)
                ),
            ]
        )
        try:
            return _parse_use_category_classification(
                _json_object_from_text(str(response.content))
            )
        except (json.JSONDecodeError, ModelUnavailable, TypeError) as exc:
            raise ModelUnavailable(
                "The triage model returned an invalid use-category response"
            ) from exc

    async def classify(self, message: str) -> TriageClassification:
        import httpx
        from langchain_core.exceptions import OutputParserException
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama

        from app.ai.museum_question_triage.application.prompts import (
            build_classification_system_prompt,
            build_classification_user_prompt,
        )

        chat = ChatOllama(
            base_url=self._base_url,
            model=self._model,
            temperature=_CLASSIFICATION_TEMPERATURE,
            client_kwargs=self._client_kwargs(),
        ).with_structured_output(_TriageClassificationSchema)
        try:
            result = await chat.ainvoke(
                [
                    SystemMessage(content=build_classification_system_prompt()),
                    HumanMessage(content=build_classification_user_prompt(message)),
                ]
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ModelTimeout("The triage model did not respond in time") from exc
        except (httpx.ConnectError, httpx.HTTPError, ConnectionError, OSError) as exc:
            raise ModelUnavailable("The triage model is currently unavailable") from exc
        except OutputParserException as exc:
            # The model failed to produce output matching the requested schema
            # (e.g. it doesn't support tool/function calling well).
            logger.warning(
                "Ollama triage structured output failed; retrying JSON fallback.",
                exc_info=exc,
            )
            try:
                return await self._classify_with_json_fallback(message)
            except (httpx.TimeoutException, TimeoutError) as fallback_exc:
                raise ModelTimeout(
                    "The triage model did not respond in time"
                ) from fallback_exc
            except (
                httpx.ConnectError,
                httpx.HTTPError,
                ConnectionError,
                OSError,
            ) as fallback_exc:
                raise ModelUnavailable(
                    "The triage model is currently unavailable"
                ) from fallback_exc
            except Exception as fallback_exc:
                if _is_ollama_response_error(fallback_exc):
                    raise ModelUnavailable(
                        "The triage model is currently unavailable"
                    ) from fallback_exc
                raise
        except Exception as exc:
            if _is_ollama_response_error(exc):
                raise ModelUnavailable(
                    "The triage model is currently unavailable"
                ) from exc
            raise

        return _parse_classification(result)

    async def classify_use_categories(self, message: str) -> UseCategoryClassification:
        import httpx
        from langchain_core.exceptions import OutputParserException
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama

        from app.ai.museum_question_triage.application.prompts import (
            build_use_category_classification_system_prompt,
            build_use_category_classification_user_prompt,
        )

        chat = ChatOllama(
            base_url=self._base_url,
            model=self._model,
            temperature=_CLASSIFICATION_TEMPERATURE,
            client_kwargs=self._client_kwargs(),
        ).with_structured_output(_UseCategoryClassificationSchema)
        try:
            result = await chat.ainvoke(
                [
                    SystemMessage(
                        content=build_use_category_classification_system_prompt()
                    ),
                    HumanMessage(
                        content=build_use_category_classification_user_prompt(message)
                    ),
                ]
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ModelTimeout("The triage model did not respond in time") from exc
        except (httpx.ConnectError, httpx.HTTPError, ConnectionError, OSError) as exc:
            raise ModelUnavailable("The triage model is currently unavailable") from exc
        except OutputParserException as exc:
            logger.warning(
                "Ollama use-category structured output failed; retrying JSON fallback.",
                exc_info=exc,
            )
            try:
                return await self._classify_use_categories_with_json_fallback(message)
            except (httpx.TimeoutException, TimeoutError) as fallback_exc:
                raise ModelTimeout(
                    "The triage model did not respond in time"
                ) from fallback_exc
            except (
                httpx.ConnectError,
                httpx.HTTPError,
                ConnectionError,
                OSError,
            ) as fallback_exc:
                raise ModelUnavailable(
                    "The triage model is currently unavailable"
                ) from fallback_exc
            except Exception as fallback_exc:
                if _is_ollama_response_error(fallback_exc):
                    raise ModelUnavailable(
                        "The triage model is currently unavailable"
                    ) from fallback_exc
                raise
        except Exception as exc:
            if _is_ollama_response_error(exc):
                raise ModelUnavailable(
                    "The triage model is currently unavailable"
                ) from exc
            raise

        return _parse_use_category_classification(result)

    async def draft_out_of_scope_reply(self, message: str) -> str:
        import httpx
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama

        from app.ai.museum_question_triage.application.prompts import (
            build_out_of_scope_reply_system_prompt,
            build_out_of_scope_reply_user_prompt,
        )

        chat = ChatOllama(
            base_url=self._base_url,
            model=self._model,
            temperature=_REPLY_TEMPERATURE,
            client_kwargs=self._client_kwargs(),
        )
        try:
            response = await chat.ainvoke(
                [
                    SystemMessage(content=build_out_of_scope_reply_system_prompt()),
                    HumanMessage(content=build_out_of_scope_reply_user_prompt(message)),
                ]
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ModelTimeout("The triage model did not respond in time") from exc
        except (httpx.ConnectError, httpx.HTTPError, ConnectionError, OSError) as exc:
            raise ModelUnavailable("The triage model is currently unavailable") from exc
        except Exception as exc:
            if _is_ollama_response_error(exc):
                raise ModelUnavailable(
                    "The triage model is currently unavailable"
                ) from exc
            raise

        text = str(response.content).strip()
        if not text:
            raise ModelUnavailable("The language model returned an empty reply")
        return text
