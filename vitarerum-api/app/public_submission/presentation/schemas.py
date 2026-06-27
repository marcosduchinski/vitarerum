"""Pydantic request/response models mirroring ``public-proposals.openapi.yaml``.

The YAML is the source of truth; these constraints (lengths, honeypot, consent,
sanitisation) must match it. Strings are stored as plain text and MUST still be
escaped on render in the staff UI (defence in depth against stored XSS).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CRLF = re.compile(r"[\r\n]")


class PublicProposalSubmission(BaseModel):
    citizenName: str = Field(min_length=1, max_length=120)
    citizenEmail: EmailStr = Field(max_length=180)
    subject: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=4000)
    consent: Literal[True]  # RGPD consent; must be exactly true
    captchaToken: str = Field(min_length=1, max_length=2048)
    # Honeypot. The YAML caps this at length 0, but enforcing that at the schema
    # would 422 a filled field — leaking to the bot that it is monitored. The
    # trust model wants a silent accept-and-drop (202, no work), so we accept a
    # bounded value here and let the use case drop it.
    website: str = Field(default="", max_length=255)

    @field_validator("citizenName", "subject", "body")
    @classmethod
    def _strip_control_chars(cls, v: str) -> str:
        return _CONTROL_CHARS.sub("", v).strip()

    @field_validator("citizenName", "subject")
    @classmethod
    def _no_crlf(cls, v: str) -> str:
        # These can end up in an e-mail subject/display name → forbid CRLF.
        return _CRLF.sub(" ", v)


class PublicSubmissionReceipt(BaseModel):
    status: Literal["PENDING_CONFIRMATION"] = "PENDING_CONFIRMATION"
    email: EmailStr


class PublicConfirmationRequest(BaseModel):
    token: str = Field(min_length=1, max_length=4096)


class PublicConfirmationResult(BaseModel):
    status: Literal["CONFIRMED", "ALREADY_CONFIRMED", "EXPIRED", "INVALID"]
    referenceNumber: str | None = None
