"""Adapter for :class:`ExternalRequesterProvisioner`.

Wraps Identity's published ``ProvisionExternalRequester`` (Open Host Service) so
``ApproveProposal`` can resolve a public proposal's ``requester_contact`` into a
system requester without this context importing Identity internals — only
``app.identity.public``.
"""

from __future__ import annotations

from app.identity.public import ProvisionExternalRequester
from app.use_of_collections.application.ports import ResolvedExternalRequester


class IdentityExternalRequesterProvisioner:
    def __init__(self, provisioner: ProvisionExternalRequester) -> None:
        self._provisioner = provisioner

    async def provision(self, email: str, name: str) -> ResolvedExternalRequester:
        provisioned = await self._provisioner.execute(email, name)
        return ResolvedExternalRequester(
            actor=provisioned.actor,
            temporary_password=provisioned.temporary_password,
        )
