"""Pydantic request/response models for the public Museum Questions API.

Strings are stored as plain text and MUST still be escaped on render in the
staff UI (defence in depth against stored XSS) — see the response section
plan's "conteudo do cidadao e sempre texto puro" decision.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CRLF = re.compile(r"[\r\n]")


class MuseumQuestionSubmission(BaseModel):
    requesterName: str = Field(min_length=1, max_length=120)
    requesterEmail: EmailStr = Field(max_length=180)
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)
    consent: Literal[True]  # RGPD consent; must be exactly true
    captchaToken: str = Field(min_length=1, max_length=2048)
    # Honeypot. Accepting (not rejecting) a filled value lets the use case
    # silently accept-and-drop instead of 422ing and tipping off the bot.
    website: str = Field(default="", max_length=255)

    @field_validator("requesterName", "subject", "message")
    @classmethod
    def _strip_control_chars(cls, v: str) -> str:
        cleaned = _CONTROL_CHARS.sub("", v).strip()
        if not cleaned:
            # min_length=1 only sees the raw value — a whitespace-only string
            # (or one made entirely of control chars) would otherwise pass it
            # and collapse to "" here, persisting an empty required field.
            raise ValueError("must not be empty or only whitespace")
        return cleaned

    @field_validator("requesterName", "subject")
    @classmethod
    def _no_crlf(cls, v: str) -> str:
        return _CRLF.sub(" ", v)


class MuseumQuestionReceipt(BaseModel):
    status: Literal["RECEIVED"] = "RECEIVED"
    email: EmailStr
