"""Pydantic request/response shapes for ProposalChat, matching
07Proposalchat-api.md exactly (camelCase JSON)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class IntendedUseModel(BaseModel):
    useType: str
    description: str


class FocusMessageModel(BaseModel):
    messageId: str
    sentAt: datetime
    sender: str
    subject: str
    body: str


class ProposalSummaryModel(BaseModel):
    proposalId: str
    referenceNumber: str
    title: str
    status: str
    intendedUse: IntendedUseModel


class TriageContextResponse(BaseModel):
    conversationId: str
    focusMessage: FocusMessageModel
    proposal: ProposalSummaryModel


class SuggestionRequest(BaseModel):
    conversationId: str
    messageId: str


class SuggestionSource(BaseModel):
    conversationId: str
    messageId: str


class SuggestionBody(BaseModel):
    intendedUse: IntendedUseModel
    confidence: float
    rationale: str
    source: SuggestionSource


class SuggestionResponse(BaseModel):
    suggestion: SuggestionBody
