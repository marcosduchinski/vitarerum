"""Persona prompt templates (KG-RAG Phase 3).

One system instruction per narrative style; the user prompt carries canonical
visit facts as the only allowed source of facts.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from app.ai.museum_narrative.domain.facts import CanonicalVisitFacts
from app.ai.museum_narrative.domain.models import NarrativeType

_PERSONAS: dict[NarrativeType, str] = {
    NarrativeType.INSTITUTIONAL: (
        "formal, bureaucratic institutional reporting — focused on institutional "
        "impact, preservation, administrative completeness and compliance"
    ),
    NarrativeType.SCIENTIFIC: (
        "rigorous, objective scientific communication — emphasising research "
        "methodology, metadata accuracy and scientific output such as publications"
    ),
    NarrativeType.AUDIOGUIDE_ADULT: (
        "an engaging, clear museum audio-guide for general adult visitors — "
        "contextualising historical and cultural significance without heavy jargon"
    ),
    NarrativeType.AUDIOGUIDE_CHILD: (
        "a playful, pedagogical audio-guide for young learners — storytelling, "
        "enthusiastic, with curiosity triggers and interactive framing"
    ),
    NarrativeType.SOCIAL_MEDIA: (
        "concise, dynamic, hook-driven social-media copy — enthusiastic, with a "
        "call-to-action and native use of emojis"
    ),
}


def build_system_prompt(narrative_type: NarrativeType) -> str:
    persona = _PERSONAS[narrative_type]
    return (
        f"You are an expert museum communicator specializing in "
        f"{narrative_type.value} storytelling ({persona}). Translate the provided "
        "canonical visit facts into a fluid narrative.\n\n"
        "CRITICAL CONSTRAINTS:\n"
        "1. You must ONLY use facts declared in the provided context. Do "
        "not invent events, people, dates or outcomes beyond these facts.\n"
        f"2. Adopt the absolute tone, style and structure of the requested "
        f"narrative type: {narrative_type.value}.\n"
        "3. If useful, mention declared evidence gaps naturally, without "
        "turning them into accusations or filling them with invented detail.\n"
        "4. Output only the narrative text, with no preamble or metadata."
    )


def build_user_prompt(facts: CanonicalVisitFacts, target_language: str) -> str:
    return (
        f"[CANONICAL VISIT FACTS]\n"
        f"{json.dumps(asdict(facts), ensure_ascii=False, default=str)}\n\n"
        f"[TASK]\nWrite the final narrative in language code '{target_language}', "
        "tailored to the specified narrative-type constraints."
    )
