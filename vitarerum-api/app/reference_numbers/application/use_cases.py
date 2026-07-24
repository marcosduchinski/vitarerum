from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.identity.public import Actor, GroupName
from app.reference_numbers.domain.models import (
    ReferenceKind,
    ReferenceMask,
    ReferencePolicy,
    ReferencePolicyId,
    ReferencePolicyStatus,
)
from app.reference_numbers.domain.ports import (
    ReferencePolicyRepository,
    ReferenceSequenceRepository,
)
from app.shared.authorization import require_group
from app.shared.kernel import ReferenceNumber


class ReferencePolicyNotFound(Exception):
    pass


class ActiveReferencePolicyNotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PreviewReferencePolicyOutput:
    kind: ReferenceKind
    mask: str
    sequence_scope: str
    example: str
    tokens: tuple[str, ...]


class PreviewReferencePolicy:
    def execute(
        self, *, kind: ReferenceKind, mask: str, sample_date: date, caller: Actor
    ) -> PreviewReferencePolicyOutput:
        require_group(caller, GroupName.SYS_ADMIN)
        reference_mask = ReferenceMask(mask)
        return PreviewReferencePolicyOutput(
            kind=kind,
            mask=reference_mask.value,
            sequence_scope=reference_mask.sequence_scope.value,
            example=reference_mask.render(on_date=sample_date, sequence=1),
            tokens=reference_mask.tokens,
        )


class CreateReferencePolicy:
    def __init__(self, repository: ReferencePolicyRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, kind: ReferenceKind, mask: str, caller: Actor
    ) -> ReferencePolicy:
        require_group(caller, GroupName.SYS_ADMIN)
        policy = ReferencePolicy.create_draft(
            kind=kind, mask=ReferenceMask(mask), created_by=str(caller.id)
        )
        await self._repository.add(policy)
        return policy


class ActivateReferencePolicy:
    def __init__(self, repository: ReferencePolicyRepository) -> None:
        self._repository = repository

    async def execute(self, *, policy_id: str, caller: Actor) -> ReferencePolicy:
        require_group(caller, GroupName.SYS_ADMIN)
        policy = await self._repository.get(ReferencePolicyId(policy_id))
        if policy is None:
            raise ReferencePolicyNotFound(policy_id)
        await self._repository.deactivate_active(policy.kind, str(caller.id))
        active = policy.activate(actor_id=str(caller.id))
        await self._repository.save(active)
        return active


class DeactivateReferencePolicy:
    def __init__(self, repository: ReferencePolicyRepository) -> None:
        self._repository = repository

    async def execute(self, *, policy_id: str, caller: Actor) -> ReferencePolicy:
        require_group(caller, GroupName.SYS_ADMIN)
        policy = await self._repository.get(ReferencePolicyId(policy_id))
        if policy is None:
            raise ReferencePolicyNotFound(policy_id)
        inactive = policy.deactivate(actor_id=str(caller.id))
        await self._repository.save(inactive)
        return inactive


class ListReferencePolicies:
    def __init__(self, repository: ReferencePolicyRepository) -> None:
        self._repository = repository

    async def execute(
        self, *, caller: Actor, kind: ReferenceKind | None = None
    ) -> list[ReferencePolicy]:
        require_group(caller, GroupName.SYS_ADMIN)
        return await self._repository.list(kind)


class GetReferencePolicy:
    def __init__(self, repository: ReferencePolicyRepository) -> None:
        self._repository = repository

    async def execute(self, *, policy_id: str, caller: Actor) -> ReferencePolicy:
        require_group(caller, GroupName.SYS_ADMIN)
        policy = await self._repository.get(ReferencePolicyId(policy_id))
        if policy is None:
            raise ReferencePolicyNotFound(policy_id)
        return policy


class GenerateReferenceNumber:
    def __init__(
        self,
        policy_repository: ReferencePolicyRepository,
        sequence_repository: ReferenceSequenceRepository,
    ) -> None:
        self._policy_repository = policy_repository
        self._sequence_repository = sequence_repository

    async def execute(self, *, kind: ReferenceKind, on_date: date) -> ReferenceNumber:
        policy = await self._policy_repository.get_active(kind, on_date)
        if policy is None:
            raise ActiveReferencePolicyNotFound(kind.value)
        sequence = await self._sequence_repository.reserve_next(policy, on_date)
        return ReferenceNumber(policy.mask.render(on_date=on_date, sequence=sequence))


class ValidateReferenceNumber:
    def __init__(self, repository: ReferencePolicyRepository) -> None:
        self._repository = repository

    async def execute(self, *, kind: ReferenceKind, value: str) -> bool:
        policies = await self._repository.list(kind)
        # A DRAFT policy was never activated, so it never generated real
        # references — only policies that were (or are) actually live count
        # as "historical" for validation purposes.
        ever_active = (
            policy
            for policy in policies
            if policy.status != ReferencePolicyStatus.DRAFT
        )
        if any(policy.matches(value) for policy in ever_active):
            return True
        legacy_formats = await self._repository.list_legacy_formats(kind)
        return any(legacy.matches(value) for legacy in legacy_formats)
