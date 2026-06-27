"""SQLAlchemy adapter for the pending submission repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.public_submission.domain.models import (
    PendingPublicSubmission,
    PendingSubmissionStatus,
)
from app.public_submission.infrastructure.models import (
    PublicProposalSubmissionRecord,
)


def _to_domain(record: PublicProposalSubmissionRecord) -> PendingPublicSubmission:
    return PendingPublicSubmission(
        id=record.id,
        token=record.token,
        citizen_name=record.citizen_name,
        citizen_email=record.citizen_email,
        subject=record.subject,
        body=record.body,
        consent=record.consent,
        created_at=record.created_at,
        status=PendingSubmissionStatus(record.status),
        confirmed_at=record.confirmed_at,
        proposal_reference=record.proposal_reference,
    )


def _apply(record: PublicProposalSubmissionRecord, s: PendingPublicSubmission) -> None:
    record.id = s.id
    record.token = s.token
    record.citizen_name = s.citizen_name
    record.citizen_email = s.citizen_email
    record.subject = s.subject
    record.body = s.body
    record.consent = s.consent
    record.status = s.status.value
    record.created_at = s.created_at
    record.confirmed_at = s.confirmed_at
    record.proposal_reference = s.proposal_reference


class SqlAlchemyPendingSubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, submission: PendingPublicSubmission) -> None:
        record = PublicProposalSubmissionRecord()
        _apply(record, submission)
        self._session.add(record)

    async def get_by_token(self, token: str) -> PendingPublicSubmission | None:
        result = await self._session.execute(
            select(PublicProposalSubmissionRecord).where(
                PublicProposalSubmissionRecord.token == token
            )
        )
        record = result.scalar_one_or_none()
        return _to_domain(record) if record is not None else None

    async def save(self, submission: PendingPublicSubmission) -> None:
        result = await self._session.execute(
            select(PublicProposalSubmissionRecord).where(
                PublicProposalSubmissionRecord.id == submission.id
            )
        )
        record = result.scalar_one()
        _apply(record, submission)
