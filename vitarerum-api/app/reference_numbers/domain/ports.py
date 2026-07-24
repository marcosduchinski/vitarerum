from __future__ import annotations

import builtins
from datetime import date
from typing import Protocol

from app.reference_numbers.domain.models import (
    LegacyReferenceFormat,
    ReferenceKind,
    ReferencePolicy,
    ReferencePolicyId,
)


class ActiveReferencePolicyConflict(Exception):
    pass


class ReferencePolicyRepository(Protocol):
    async def add(self, policy: ReferencePolicy) -> None: ...
    async def save(self, policy: ReferencePolicy) -> None: ...
    async def get(self, policy_id: ReferencePolicyId) -> ReferencePolicy | None: ...
    async def list(
        self, kind: ReferenceKind | None = None
    ) -> builtins.list[ReferencePolicy]: ...
    async def get_active(
        self, kind: ReferenceKind, on_date: date
    ) -> ReferencePolicy | None: ...
    async def deactivate_active(self, kind: ReferenceKind, actor_id: str) -> None: ...
    async def list_legacy_formats(
        self, kind: ReferenceKind
    ) -> builtins.list[LegacyReferenceFormat]: ...


class ReferenceSequenceRepository(Protocol):
    async def reserve_next(self, policy: ReferencePolicy, on_date: date) -> int: ...
