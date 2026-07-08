"""Adapter for :class:`ExternalRequesterProvisioner`.

Wraps Identity's published ``ProvisionExternalRequester`` (Open Host Service) so
``ApproveProposal`` can resolve a public proposal's ``requester_contact`` into a
system requester without this context importing Identity internals — only
``app.identity.public``.
"""

from __future__ import annotations

from app.identity.public import Actor, ProvisionExternalRequester


class IdentityExternalRequesterProvisioner:
    def __init__(self, provisioner: ProvisionExternalRequester) -> None:
        self._provisioner = provisioner

    async def provision(self, email: str, name: str) -> Actor:
        provisioned = await self._provisioner.execute(email, name)
        return provisioned.actor
