from __future__ import annotations

import builtins
from datetime import UTC, date, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.reference_numbers.domain.models import (
    LegacyReferenceFormat,
    ReferenceKind,
    ReferenceMask,
    ReferencePolicy,
    ReferencePolicyEvent,
    ReferencePolicyId,
    ReferencePolicyStatus,
)
from app.reference_numbers.domain.ports import ActiveReferencePolicyConflict
from app.reference_numbers.infrastructure.models import (
    ReferenceLegacyFormatRecord,
    ReferencePolicyEventRecord,
    ReferencePolicyRecord,
    ReferencePolicySequenceRecord,
)


def policy_to_record(policy: ReferencePolicy) -> ReferencePolicyRecord:
    return ReferencePolicyRecord(
        id=policy.id,
        kind=policy.kind.value,
        mask=policy.mask.value,
        sequence_scope=policy.sequence_scope.value,
        status=policy.status.value,
        active_from=policy.active_from,
        active_until=policy.active_until,
        created_by=policy.created_by,
        created_at=policy.created_at,
        updated_by=policy.updated_by,
        updated_at=policy.updated_at,
        activated_by=policy.activated_by,
        activated_at=policy.activated_at,
    )


def policy_to_domain(record: ReferencePolicyRecord) -> ReferencePolicy:
    return ReferencePolicy(
        id=ReferencePolicyId(record.id),
        kind=ReferenceKind(record.kind),
        mask=ReferenceMask(record.mask),
        status=ReferencePolicyStatus(record.status),
        active_from=record.active_from,
        active_until=record.active_until,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_by=record.updated_by,
        updated_at=record.updated_at,
        activated_by=record.activated_by,
        activated_at=record.activated_at,
    )


def legacy_to_domain(record: ReferenceLegacyFormatRecord) -> LegacyReferenceFormat:
    return LegacyReferenceFormat(
        kind=ReferenceKind(record.kind), name=record.name, pattern=record.pattern
    )


class SqlAlchemyReferencePolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, policy: ReferencePolicy) -> None:
        self._session.add(policy_to_record(policy))
        # Flush the policy row before adding its event: there is no ORM
        # relationship() between ReferencePolicyRecord and
        # ReferencePolicyEventRecord (only a raw FK column), so SQLAlchemy's
        # unit of work has no dependency edge telling it the event must be
        # inserted after the policy — without this explicit ordering it can
        # (and on PostgreSQL, did) attempt the event insert first and violate
        # the foreign key.
        await self._session.flush()
        self._session.add(
            _event_record(policy, ReferencePolicyEvent.CREATED, policy.created_by)
        )
        await self._session.flush()

    async def save(self, policy: ReferencePolicy) -> None:
        try:
            await self._session.merge(policy_to_record(policy))
            if policy.updated_by is not None:
                event_type = (
                    ReferencePolicyEvent.ACTIVATED
                    if policy.status is ReferencePolicyStatus.ACTIVE
                    else ReferencePolicyEvent.DEACTIVATED
                )
                self._session.add(_event_record(policy, event_type, policy.updated_by))
            await self._session.flush()
        except IntegrityError as exc:
            raise ActiveReferencePolicyConflict(
                f"An active policy already exists for {policy.kind.value}."
            ) from exc

    async def get(self, policy_id: ReferencePolicyId) -> ReferencePolicy | None:
        stmt = select(ReferencePolicyRecord).where(
            ReferencePolicyRecord.id == policy_id
        )
        record = (await self._session.execute(stmt)).scalar_one_or_none()
        return policy_to_domain(record) if record else None

    async def list(
        self, kind: ReferenceKind | None = None
    ) -> builtins.list[ReferencePolicy]:
        stmt = select(ReferencePolicyRecord)
        if kind is not None:
            stmt = stmt.where(ReferencePolicyRecord.kind == kind.value)
        stmt = stmt.order_by(
            ReferencePolicyRecord.kind.asc(),
            ReferencePolicyRecord.created_at.desc(),
        )
        records = (await self._session.execute(stmt)).scalars().all()
        return [policy_to_domain(record) for record in records]

    async def get_active(
        self, kind: ReferenceKind, on_date: date
    ) -> ReferencePolicy | None:
        at_start = datetime.combine(on_date, datetime.min.time(), tzinfo=UTC)
        stmt = (
            select(ReferencePolicyRecord)
            .where(
                ReferencePolicyRecord.kind == kind.value,
                ReferencePolicyRecord.status == ReferencePolicyStatus.ACTIVE.value,
                (
                    (ReferencePolicyRecord.active_until.is_(None))
                    | (ReferencePolicyRecord.active_until > at_start)
                ),
            )
            .order_by(ReferencePolicyRecord.active_from.desc())
            .limit(1)
        )
        record = (await self._session.execute(stmt)).scalar_one_or_none()
        return policy_to_domain(record) if record else None

    async def deactivate_active(self, kind: ReferenceKind, actor_id: str) -> None:
        now = datetime.now(UTC)
        stmt = (
            update(ReferencePolicyRecord)
            .where(
                ReferencePolicyRecord.kind == kind.value,
                ReferencePolicyRecord.status == ReferencePolicyStatus.ACTIVE.value,
            )
            .values(
                status=ReferencePolicyStatus.INACTIVE.value,
                active_until=now,
                updated_by=actor_id,
                updated_at=now,
            )
        )
        await self._session.execute(stmt)

    async def list_legacy_formats(
        self, kind: ReferenceKind
    ) -> builtins.list[LegacyReferenceFormat]:
        stmt = (
            select(ReferenceLegacyFormatRecord)
            .where(ReferenceLegacyFormatRecord.kind == kind.value)
            .order_by(ReferenceLegacyFormatRecord.name.asc())
        )
        records = (await self._session.execute(stmt)).scalars().all()
        return [legacy_to_domain(record) for record in records]


class SqlAlchemyReferenceSequenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve_next(self, policy: ReferencePolicy, on_date: date) -> int:
        scope_key = policy.mask.scope_key(on_date)
        for attempt in range(3):
            stmt = (
                select(ReferencePolicySequenceRecord)
                .where(
                    ReferencePolicySequenceRecord.policy_id == policy.id,
                    ReferencePolicySequenceRecord.scope_key == scope_key,
                )
                .with_for_update()
            )
            record = (await self._session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(UTC)
            if record is not None:
                value = record.next_value
                record.next_value = value + 1
                record.updated_at = now
                await self._session.flush()
                return value

            try:
                async with self._session.begin_nested():
                    record = ReferencePolicySequenceRecord(
                        policy_id=policy.id,
                        scope_key=scope_key,
                        next_value=2,
                        updated_at=now,
                    )
                    self._session.add(record)
                    await self._session.flush()
                return 1
            except IntegrityError:
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")  # pragma: no cover


def _event_record(
    policy: ReferencePolicy, event_type: ReferencePolicyEvent, actor_id: str
) -> ReferencePolicyEventRecord:
    return ReferencePolicyEventRecord(
        policy_id=policy.id,
        event_type=event_type.value,
        actor_permission_id=actor_id,
        occurred_at=datetime.now(UTC),
        payload_json=(
            '{"kind":"'
            + policy.kind.value
            + '","mask":"'
            + policy.mask.value
            + '","status":"'
            + policy.status.value
            + '"}'
        ),
    )
