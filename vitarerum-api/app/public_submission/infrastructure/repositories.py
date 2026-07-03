"""SQLAlchemy adapter for the pending submission repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.public_submission.domain.models import (
    PendingPublicSubmission,
    PendingSubmissionStatus,
    ProposalAmendmentToken,
    PublicDocumentSubmission,
)
from app.public_submission.infrastructure.models import (
    ProposalAmendmentTokenRecord,
    PublicDocumentSubmissionRecord,
    PublicProposalSubmissionRecord,
)
from app.shared.kernel import UseType


def _to_domain(record: PublicProposalSubmissionRecord) -> PendingPublicSubmission:
    return PendingPublicSubmission(
        id=record.id,
        token=record.token,
        citizen_name=record.citizen_name,
        citizen_email=record.citizen_email,
        subject=record.subject,
        body=record.body,
        use_type=UseType(record.use_type),
        consent=record.consent,
        created_at=record.created_at,
        proposed_begin_date=record.proposed_begin_date,
        proposed_end_date=record.proposed_end_date,
        documents=[
            PublicDocumentSubmission(
                id=document.id,
                file_name=document.file_name,
                file_reference=document.file_reference,
                submitted_at=document.submitted_at,
            )
            for document in record.documents
        ],
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
    record.use_type = s.use_type.value
    record.proposed_begin_date = s.proposed_begin_date
    record.proposed_end_date = s.proposed_end_date
    record.consent = s.consent
    record.status = s.status.value
    record.created_at = s.created_at
    record.confirmed_at = s.confirmed_at
    record.proposal_reference = s.proposal_reference
    record.documents = [
        PublicDocumentSubmissionRecord(
            id=document.id,
            file_name=document.file_name,
            file_reference=document.file_reference,
            submitted_at=document.submitted_at,
        )
        for document in s.documents
    ]


class SqlAlchemyPendingSubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, submission: PendingPublicSubmission) -> None:
        record = PublicProposalSubmissionRecord()
        _apply(record, submission)
        self._session.add(record)
        # Flush so unique-token / constraint violations surface here, before any
        # side effect (e.g. the confirmation e-mail) is triggered by the caller.
        await self._session.flush()

    async def get_by_token(self, token: str) -> PendingPublicSubmission | None:
        result = await self._session.execute(
            select(PublicProposalSubmissionRecord)
            .options(selectinload(PublicProposalSubmissionRecord.documents))
            .where(PublicProposalSubmissionRecord.token == token)
        )
        record = result.scalar_one_or_none()
        return _to_domain(record) if record is not None else None

    async def get_by_token_for_update(
        self, token: str
    ) -> PendingPublicSubmission | None:
        # Row-level lock held until the request transaction commits: concurrent
        # confirmations of the same token are serialised, so only one materialises
        # a proposal; the loser re-reads the row as CONFIRMED.
        result = await self._session.execute(
            select(PublicProposalSubmissionRecord)
            .options(selectinload(PublicProposalSubmissionRecord.documents))
            .where(PublicProposalSubmissionRecord.token == token)
            .with_for_update()
        )
        record = result.scalar_one_or_none()
        return _to_domain(record) if record is not None else None

    async def save(self, submission: PendingPublicSubmission) -> None:
        result = await self._session.execute(
            select(PublicProposalSubmissionRecord)
            .options(selectinload(PublicProposalSubmissionRecord.documents))
            .where(PublicProposalSubmissionRecord.id == submission.id)
        )
        record = result.scalar_one()
        _apply(record, submission)

    async def delete(self, submission: PendingPublicSubmission) -> None:
        # Load the document collection so the ORM cascades the child-row deletes
        # (the FK has no DB-level ON DELETE CASCADE).
        result = await self._session.execute(
            select(PublicProposalSubmissionRecord)
            .options(selectinload(PublicProposalSubmissionRecord.documents))
            .where(PublicProposalSubmissionRecord.id == submission.id)
        )
        record = result.scalar_one_or_none()
        if record is not None:
            await self._session.delete(record)


def _token_to_domain(record: ProposalAmendmentTokenRecord) -> ProposalAmendmentToken:
    return ProposalAmendmentToken(
        id=record.id,
        proposal_id=record.proposal_id,
        token_hash=record.token_hash,
        requester_email=record.requester_email,
        correction_item_ids=list(record.correction_item_ids),
        created_at=record.created_at,
        expires_at=record.expires_at,
        used_at=record.used_at,
    )


class SqlAlchemyAmendmentTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: ProposalAmendmentToken) -> None:
        record = ProposalAmendmentTokenRecord(
            id=token.id,
            proposal_id=token.proposal_id,
            token_hash=token.token_hash,
            requester_email=token.requester_email,
            correction_item_ids=list(token.correction_item_ids),
            created_at=token.created_at,
            expires_at=token.expires_at,
            used_at=token.used_at,
        )
        self._session.add(record)
        await self._session.flush()

    async def get_by_hash(self, token_hash: str) -> ProposalAmendmentToken | None:
        result = await self._session.execute(
            select(ProposalAmendmentTokenRecord).where(
                ProposalAmendmentTokenRecord.token_hash == token_hash
            )
        )
        record = result.scalar_one_or_none()
        return _token_to_domain(record) if record is not None else None

    async def save(self, token: ProposalAmendmentToken) -> None:
        result = await self._session.execute(
            select(ProposalAmendmentTokenRecord).where(
                ProposalAmendmentTokenRecord.id == token.id
            )
        )
        record = result.scalar_one()
        record.requester_email = token.requester_email
        record.correction_item_ids = list(token.correction_item_ids)
        record.expires_at = token.expires_at
        record.used_at = token.used_at
