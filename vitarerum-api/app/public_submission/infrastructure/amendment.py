"""Public-submission adapter for ``use_of_collections``'s AmendmentInvitationPort.

Owns the two pieces ``use_of_collections`` deliberately does not: the scoped,
expiring, single-use amendment token and the real e-mail delivery. Wired at the
composition root (``app.main``) over the request session, so the staff endpoint
in ``use_of_collections`` stays free of any ``public_submission`` import (the
dependency direction is enforced by import-linter)."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.public_submission.application.ports import (
    AmendmentInviteEmailSender,
    AmendmentTokenRepository,
    Clock,
)
from app.public_submission.domain.models import ProposalAmendmentToken
from app.use_of_collections.application.ports import ProposalRepository
from app.use_of_collections.domain.models import ProposalId


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class PublicAmendmentInvitationAdapter:
    def __init__(
        self,
        session: AsyncSession,
        token_repository: AmendmentTokenRepository,
        proposal_repository: ProposalRepository,
        email_sender: AmendmentInviteEmailSender,
        clock: Clock,
        token_ttl: timedelta,
    ) -> None:
        self._session = session
        self._tokens = token_repository
        self._proposals = proposal_repository
        self._email = email_sender
        self._clock = clock
        self._ttl = token_ttl

    async def invite_document_corrections(
        self,
        *,
        proposal_id: ProposalId,
        requester_email: str,
        requester_name: str,
        correction_item_ids: list[str],
    ) -> None:
        now = self._clock.now()
        raw_token = secrets.token_urlsafe(32)
        token = ProposalAmendmentToken(
            id=str(uuid.uuid4()),
            proposal_id=str(proposal_id),
            token_hash=hash_token(raw_token),
            requester_email=requester_email,
            correction_item_ids=list(correction_item_ids),
            created_at=now,
            expires_at=now + self._ttl,
        )
        await self._tokens.add(token)
        # Reasons for the e-mail body come from the durable correction items.
        proposal = await self._proposals.get_by_id(proposal_id)
        scope = set(correction_item_ids)
        reasons = (
            [ci.reason for ci in proposal.correction_items if ci.id in scope]
            if proposal is not None
            else []
        )
        # Commit the token before e-mailing, so the citizen never receives a link
        # whose token was rolled back (mirrors the confirmation-e-mail ordering).
        await self._session.commit()
        await self._email.send_amendment_invite(
            requester_email, requester_name, raw_token, reasons
        )
