"""Default (local/dev) adapter for :class:`AmendmentInvitationPort`.

The real adapter — which mints a scoped, expiring token and e-mails the citizen a
link into the public amendment channel — lives in the ``public_submission``
context and is wired at the composition root (``app.main``) via
``dependency_overrides``. This logging stand-in keeps the staff endpoint usable
in tests / local runs where no override is installed, without pulling a
cross-context dependency into ``use_of_collections``.
"""

from __future__ import annotations

import logging

from app.use_of_collections.domain.models import ProposalId

logger = logging.getLogger(__name__)


class LoggingAmendmentInvitation:
    async def invite_document_corrections(
        self,
        *,
        proposal_id: ProposalId,
        requester_email: str,
        requester_name: str,
        correction_item_ids: list[str],
    ) -> None:
        logger.info(
            "[amendment] would invite %s (%s) to correct %d item(s) on proposal %s",
            requester_name,
            requester_email,
            len(correction_item_ids),
            proposal_id,
        )
