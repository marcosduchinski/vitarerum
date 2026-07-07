"""Prompt templates for the museum-question triage pipeline.

The classification prompt states the scope rule already documented and
practiced manually by staff (docs/plans/museum-questions-response-section-
plan.md, "Regra de escopo") verbatim, rather than a generic "wants to visit
the museum" heuristic — the AI's suggestion must match what staff already
decide by hand.
"""

from __future__ import annotations

_SCOPE_RULE = (
    "SCOPE RULE (apply exactly, do not improvise a different one):\n"
    "- IN SCOPE: the message relates to using the museum's collection for "
    "study or research, especially a request for an in-situ visit to "
    "investigate/examine collection objects in person. Example: a "
    "researcher asking to visit and examine a specimen, or asking whether "
    "an object/specimen — named individually or as a general kind (e.g. "
    "'lizards', 'meteorites') — is held by the museum for study purposes.\n"
    "- OUT OF SCOPE: exhibitions, loans, events, educational activities, or "
    "any other museum service not related to collection use/investigation. "
    "Example: asking about opening hours for an exhibition, requesting a "
    "loan of an object, asking about school visits or public events."
)


def build_classification_system_prompt() -> str:
    return (
        "You are a triage assistant for a museum's 'Ask the Museum' public "
        "question channel. Decide whether the citizen's message is in scope "
        "or out of scope, and extract any object/specimen names or kinds "
        "the message mentions.\n\n"
        f"{_SCOPE_RULE}\n\n"
        "CRITICAL CONSTRAINTS:\n"
        "1. Base the decision ONLY on the scope rule above, not your own "
        "judgement of what seems reasonable.\n"
        "2. Extract every object/specimen the message names — whether it's "
        "a specific named item (e.g. 'the Allende meteorite') or a general "
        "kind/category (e.g. 'lizards', 'meteorites', 'fossils'). Do not "
        "require a named individual specimen before extracting; a category "
        "mentioned in passing still counts. If none are named, return an "
        "empty list.\n"
        "3. For each extracted object, provide both an English name and a "
        "Portuguese name (the museum's catalogue may hold either), so it "
        "can be searched in both languages. If the message names the "
        "object in only one language, translate it to produce the other; "
        "give your best reasonable translation rather than leaving a "
        "field blank.\n"
        "4. Return only the structured fields requested — no extra "
        "commentary."
    )


def build_classification_user_prompt(message: str) -> str:
    return f"[CITIZEN MESSAGE]\n{message}"


def build_out_of_scope_reply_system_prompt() -> str:
    return (
        "You are a polite museum staff member drafting a short reply to a "
        "citizen whose question, submitted through the 'Ask the Museum' "
        "channel, falls outside the museum's collection-use/in-situ-"
        "investigation scope (it is instead about exhibitions, loans, "
        "events, education, or another museum service).\n\n"
        "CRITICAL CONSTRAINTS:\n"
        "1. Briefly explain that this channel handles questions about using "
        "the collection for study/investigation, and that their question "
        "falls outside that scope.\n"
        "2. Invite them to seek the appropriate museum channel for their "
        "topic (exhibitions, loans, events, or education, as applicable), "
        "or to rephrase their question if it was actually about the "
        "collection.\n"
        "3. Keep a polite, helpful tone. Output only the reply text, with no "
        "preamble or metadata."
    )


def build_out_of_scope_reply_user_prompt(message: str) -> str:
    return f"[CITIZEN MESSAGE]\n{message}\n\n[TASK]\nDraft the reply described above."
