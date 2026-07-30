"""Opaque public-token generation and hashing helpers."""

from __future__ import annotations

import hashlib
import secrets


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def hash_opaque_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
