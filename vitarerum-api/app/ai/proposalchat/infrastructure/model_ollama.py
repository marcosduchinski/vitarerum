"""LangGraph + Ollama adapter implementing ``IntendedUseSuggestionPort``.

A single-node LangGraph graph wraps ``ChatOllama`` and asks the model to classify
the focus message into the shared ``UseType`` taxonomy with a confidence and a
short rationale. Heavy imports (langgraph / langchain-ollama / httpx) are loaded
lazily inside :meth:`suggest` so the module imports without the model stack
installed and unit tests can substitute a fake port.

Failure mapping (per 07Proposalchat-api.md):
- connection failures        → :class:`ModelUnavailable`  (503)
- timeouts / slow responses  → :class:`ModelTimeout`      (504)
"""

from __future__ import annotations

import json
from typing import TypedDict

from app.ai.proposalchat.domain.models import (
    Confidence,
    ConversationContext,
    IntendedUseSuggestion,
)
from app.ai.proposalchat.domain.ports import ModelTimeout, ModelUnavailable
from app.shared.kernel import UseType

_SYSTEM_PROMPT = (
"You are a classification assistant responsible for triaging incoming "
"museum collection-use requests.\n\n"


"Your task is to read one email and identify the requester's primary "
"intended use of the museum collection.\n\n"

"Classify the request into exactly one of the following categories:\n\n"

"1. EXHIBITION\n"
"Use this category when the requester intends to display, present, "
"reproduce, interpret, or otherwise use museum objects, specimens, images, "
"records, or related information as part of an exhibition or public display.\n\n"

"This includes:\n"
"- Temporary or permanent exhibitions\n"
"- Physical or digital exhibitions\n"
"- Loans requested for exhibition purposes\n"
"- Use of object images or collection information in exhibition panels, "
"catalogues, labels, or interactive displays\n"
"- Travelling exhibitions\n"
"- Public displays hosted by another institution\n\n"

"Do not use this category when the requester only wants to inspect or "
"study objects without displaying them.\n\n"

"2. IN_SITU_VISIT\n"
"Use this category when the requester intends to visit the museum, "
"collection facility, archive, laboratory, storage area, or another "
"designated location to directly inspect, study, photograph, measure, "
"sample, document, or otherwise work with collection objects in person.\n\n"

"This includes:\n"
"- Research visits\n"
"- Consultation of physical specimens or objects\n"
"- On-site photography or digitisation\n"
"- Scientific examination\n"
"- Measurement, observation, or documentation\n"
"- Supervised handling of collection objects\n"
"- Sampling requests that require access to the physical collection\n"
"- Educational or professional visits focused on direct access to "
"collection material\n\n"

"Use this category even when the email does not explicitly say "
"\"in situ\", provided that physical access to the collection is clearly "
"requested.\n\n"

"3. OTHER\n"
"Use this category when the request does not primarily concern an "
"exhibition or an in-person collection visit.\n\n"

"This includes:\n"
"- Requests for digital files, photographs, metadata, cataloguing "
"information, or database records without a physical visit\n"
"- Publication, book, article, documentary, website, or media-use requests\n"
"- Reproduction or licensing requests unrelated to an exhibition\n"
"- General enquiries\n"
"- Donation or acquisition proposals\n"
"- Conservation advice\n"
"- Commercial-use requests\n"
"- Teaching requests that do not involve direct physical access to the "
"collection\n"
"- Requests whose intended use is unclear or cannot be determined from "
"the email\n\n"

"Classification rules:\n\n"

"- Classify according to the requester's primary intended use, not merely "
"the objects, departments, or collection areas mentioned.\n"
"- Consider the complete meaning of the email, including purpose, "
"requested actions, destination, dates, and expected outputs.\n"
"- If more than one use is mentioned, select the category that best "
"represents the main purpose of the request.\n"
"- If an exhibition is the final purpose but the requester also wants to "
"inspect objects beforehand, classify as EXHIBITION when the exhibition "
"is clearly the principal objective.\n"
"- If the main objective is physical examination or research and no "
"exhibition is planned, classify as IN_SITU_VISIT.\n"
"- If the email requests only images, records, metadata, or remote "
"information, classify as OTHER.\n"
"- Do not infer facts that are not supported by the email.\n"
"- When the intended use is genuinely ambiguous, classify as OTHER and "
"assign a lower confidence score.\n"
"- The description must restate the concrete intended use without adding "
"unsupported assumptions.\n"
"- The rationale must briefly identify the evidence in the email that "
"supports the selected category.\n\n"

"Return a STRICT JSON object using exactly this structure:\n\n"

"{\n"
"  \"useType\": \"EXHIBITION | IN_SITU_VISIT | OTHER\",\n"
"  \"description\": \"One concise sentence describing the requester's "
"concrete intended use.\",\n"
"  \"confidence\": 0.0,\n"
"  \"rationale\": \"One short sentence explaining the classification.\"\n"
"}\n\n"

"Output requirements:\n\n"

"- \"useType\" must contain exactly one of: \"EXHIBITION\", "
"\"IN_SITU_VISIT\", or \"OTHER\".\n"
"- \"description\" must contain one concise sentence.\n"
"- \"confidence\" must be a number between 0 and 1.\n"
"- Use confidence above 0.85 only when the intended use is explicit.\n"
"- Use confidence between 0.60 and 0.85 when the intended use is strongly "
"implied.\n"
"- Use confidence below 0.60 when the request is incomplete or ambiguous.\n"
"- \"rationale\" must contain one short sentence suitable for a museum "
"staff reviewer.\n"
"- Return valid JSON.\n"
"- Do not use Markdown.\n"
"- Do not include comments, explanations, code fences, or text outside "
"the JSON object.\n\n"

"Email to classify:\n\n"
"{email_content}"


)



class _GraphState(TypedDict, total=False):
    prompt: str
    content: str


def _build_user_prompt(context: ConversationContext) -> str:
    focus = context.focus
    return (
        f"From: {focus.sender}\n"
        f"Subject: {focus.subject}\n\n"
        f"{focus.body}"
    )


def _coerce_use_type(raw: object) -> UseType:
    try:
        return UseType(str(raw).strip().upper())
    except ValueError:
        return UseType.OTHER


def _coerce_confidence(raw: object) -> Confidence:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = 0.0
    return Confidence(min(1.0, max(0.0, value)))


class LangGraphIntendedUseAdapter:
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

    async def suggest(self, context: ConversationContext) -> IntendedUseSuggestion:
        content = await self._invoke_model(context)
        data = self._parse(content)
        return IntendedUseSuggestion(
            use_type=_coerce_use_type(data.get("useType")),
            description=str(data.get("description", "")).strip(),
            confidence=_coerce_confidence(data.get("confidence")),
            rationale=str(data.get("rationale", "")).strip(),
            source_conversation_id=context.conversation_id,
            source_message_id=context.focus.message_id,
        )

    async def _invoke_model(self, context: ConversationContext) -> str:
        # Lazy imports: keep the model stack off the import path until first use.
        import httpx
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama
        from langgraph.graph import END, START, StateGraph

        client_kwargs: dict[str, object] = {"timeout": self._timeout_seconds}
        if self._api_key:
            # Ollama Cloud authenticates via a bearer token on every request.
            client_kwargs["headers"] = {"Authorization": f"Bearer {self._api_key}"}

        chat = ChatOllama(
            base_url=self._base_url,
            model=self._model,
            format="json",
            client_kwargs=client_kwargs,
        )

        async def classify(state: _GraphState) -> _GraphState:
            response = await chat.ainvoke(
                [
                    SystemMessage(content=_SYSTEM_PROMPT),
                    HumanMessage(content=state["prompt"]),
                ]
            )
            return {"content": str(response.content)}

        graph = StateGraph(_GraphState)
        graph.add_node("classify", classify)
        graph.add_edge(START, "classify")
        graph.add_edge("classify", END)
        compiled = graph.compile()

        try:
            result = await compiled.ainvoke(
                _GraphState(prompt=_build_user_prompt(context))
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise ModelTimeout("The language model did not respond in time") from exc
        except (httpx.ConnectError, httpx.HTTPError, ConnectionError, OSError) as exc:
            raise ModelUnavailable(
                "The language model is currently unavailable"
            ) from exc
        return str(result["content"])

    @staticmethod
    def _parse(content: str) -> dict[str, object]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
