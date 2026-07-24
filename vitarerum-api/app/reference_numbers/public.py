from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol

from app.reference_numbers.domain.models import ReferenceKind
from app.shared.kernel import ReferenceNumber

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["ReferenceKind", "ReferenceNumberGenerator", "get_reference_generator"]


class ReferenceNumberGenerator(Protocol):
    async def generate(
        self, *, kind: ReferenceKind, on_date: date
    ) -> ReferenceNumber: ...


class _SqlAlchemyReferenceNumberGenerator:
    def __init__(self, session: AsyncSession) -> None:
        from app.reference_numbers.application.use_cases import (
            GenerateReferenceNumber,
        )
        from app.reference_numbers.infrastructure.repositories import (
            SqlAlchemyReferencePolicyRepository,
            SqlAlchemyReferenceSequenceRepository,
        )

        self._use_case = GenerateReferenceNumber(
            SqlAlchemyReferencePolicyRepository(session),
            SqlAlchemyReferenceSequenceRepository(session),
        )

    async def generate(
        self, *, kind: ReferenceKind, on_date: date
    ) -> ReferenceNumber:
        return await self._use_case.execute(kind=kind, on_date=on_date)


def get_reference_generator(session: AsyncSession) -> ReferenceNumberGenerator:
    return _SqlAlchemyReferenceNumberGenerator(session)
