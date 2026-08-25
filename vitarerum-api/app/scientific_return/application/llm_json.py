"""Helpers for reading structured output from a language model.

Every field is validated on the way in. A model response is untrusted input
like any other: it may be truncated, fenced, oversized, or carry fields nobody
asked for, and each of those must fail loudly rather than propagate.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

MAX_STRING_LENGTH = 2000
MAX_LIST_ITEMS = 20
MAX_ITEM_LENGTH = 1000


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def strip_json_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().casefold() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def parse_json_object(raw: str, *, allowed_fields: set[str]) -> dict[str, Any]:
    """Decode one JSON object and reject anything outside ``allowed_fields``.

    Unknown fields are an error rather than something to ignore: they usually
    mean the model answered a different contract than the one it was given.
    """
    try:
        payload = json.loads(strip_json_fence(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    unexpected = set(payload) - allowed_fields
    if unexpected:
        raise ValueError(
            "LLM response contains unexpected fields: " + ", ".join(sorted(unexpected))
        )
    return payload


def required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"LLM response field '{key}' must be a non-empty string")
    text = value.strip()
    if len(text) > MAX_STRING_LENGTH:
        raise ValueError(f"LLM response field '{key}' is oversized")
    return text


def required_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"LLM response field '{key}' must be a boolean")
    return value


def optional_bool(payload: dict[str, Any], key: str, *, default: bool) -> bool:
    """Absence falls back to ``default``; a present wrong type still fails.

    Small models routinely omit a field they consider unnecessary rather than
    state it. Rejecting the whole response for a missing flag throws away work
    the model got right, while accepting ``"false"`` as a boolean would give up
    the guarantee that a stated value means what it says.
    """
    if key not in payload or payload[key] is None:
        return default
    return required_bool(payload, key)


def optional_string(payload: dict[str, Any], key: str, *, default: str) -> str:
    """Absence falls back to ``default``; a present malformed value still fails."""
    if key not in payload or payload[key] is None:
        return default
    return required_string(payload, key)


def string_list(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"LLM response field '{key}' must be an array of strings")
    if len(value) > MAX_LIST_ITEMS:
        raise ValueError(f"LLM response field '{key}' has too many items")
    normalized = tuple(item.strip() for item in value if item.strip())
    if any(len(item) > MAX_ITEM_LENGTH for item in normalized):
        raise ValueError(f"LLM response field '{key}' contains an oversized item")
    return normalized


def required_object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"LLM response field '{key}' must be an object")
    return value
