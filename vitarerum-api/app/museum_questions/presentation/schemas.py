"""Pydantic request/response models for the public Museum Questions API.

Strings are stored as plain text and MUST still be escaped on render in the
staff UI (defence in depth against stored XSS) — see the response section
plan's "conteudo do cidadao e sempre texto puro" decision.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.identity.public import GroupName

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


MuseumQuestionStatusValue = Literal[
    "SUBMITTED", "IN_PROGRESS", "ANSWERED", "OUT_OF_SCOPE", "CLOSED"
]


class MuseumQuestionAttachmentResponse(BaseModel):
    id: str
    fileName: str
    contentType: str
    sizeBytes: int
    createdAt: datetime


class UserSummary(BaseModel):
    id: str
    name: str
    email: str


class PermissionDetail(BaseModel):
    permissionId: str
    user: UserSummary
    group: GroupName


class MuseumQuestionListItemResponse(BaseModel):
    id: str
    requesterName: str
    requesterEmail: EmailStr
    subject: str
    message: str
    status: MuseumQuestionStatusValue
    createdAt: datetime
    responseDueAt: datetime
    responseOverdueNotifiedAt: datetime | None = None
    responseOverdue: bool = False
    answeredAt: datetime | None = None
    answeredBy: str | None = None
    answerBody: str | None = None
    answerSentAt: datetime | None = None
    outOfScopeAt: datetime | None = None
    outOfScopeBy: str | None = None
    outOfScopeReason: str | None = None
    outOfScopeEmailSentAt: datetime | None = None
    closedAt: datetime | None = None
    closedBy: str | None = None
    assignedTo: PermissionDetail | None = None
    attachmentCount: int = 0


class MuseumQuestionDetailResponse(BaseModel):
    id: str
    requesterName: str
    requesterEmail: EmailStr
    subject: str
    message: str
    status: MuseumQuestionStatusValue
    createdAt: datetime
    responseDueAt: datetime
    responseOverdueNotifiedAt: datetime | None = None
    responseOverdue: bool = False
    answeredAt: datetime | None = None
    answeredBy: str | None = None
    answerBody: str | None = None
    answerSentAt: datetime | None = None
    outOfScopeAt: datetime | None = None
    outOfScopeBy: str | None = None
    outOfScopeReason: str | None = None
    outOfScopeEmailSentAt: datetime | None = None
    closedAt: datetime | None = None
    closedBy: str | None = None
    assignedTo: PermissionDetail | None = None
    attachments: list[MuseumQuestionAttachmentResponse] = Field(default_factory=list)


class PaginatedMuseumQuestionsResponse(BaseModel):
    content: list[MuseumQuestionListItemResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class AnswerMuseumQuestionRequest(BaseModel):
    answerBody: str = Field(min_length=1, max_length=4000)

    @field_validator("answerBody")
    @classmethod
    def _strip_answer(cls, v: str) -> str:
        cleaned = _CONTROL_CHARS.sub("", v).strip()
        if not cleaned:
            raise ValueError("must not be empty or only whitespace")
        return cleaned


class MarkOutOfScopeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = _CONTROL_CHARS.sub("", v).strip()
        return cleaned or None


class ForwardMuseumQuestionRequest(BaseModel):
    targetPermissionId: str = Field(min_length=1, max_length=36)
