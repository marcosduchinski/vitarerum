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
from app.shared.field_encryption import FieldEncryptor
from app.shared.kernel import UseType

_SUBMISSION_CITIZEN_NAME = "public_proposal_submissions.citizen_name"
_SUBMISSION_CITIZEN_EMAIL = "public_proposal_submissions.citizen_email"
_SUBMISSION_SUBJECT = "public_proposal_submissions.subject"
_SUBMISSION_BODY = "public_proposal_submissions.body"
_DOCUMENT_FILE_NAME = "public_proposal_submission_documents.file_name"
_AMENDMENT_REQUESTER_EMAIL = "proposal_amendment_tokens.requester_email"


def _to_domain(
    record: PublicProposalSubmissionRecord, encryptor: FieldEncryptor
) -> PendingPublicSubmission:
    return PendingPublicSubmission(
        id=record.id,
        token=record.token,
        citizen_name=encryptor.decrypt_text(
            record.citizen_name, _SUBMISSION_CITIZEN_NAME
        )
        or "",
        citizen_email=encryptor.decrypt_text(
            record.citizen_email, _SUBMISSION_CITIZEN_EMAIL
        )
        or "",
        subject=encryptor.decrypt_text(record.subject, _SUBMISSION_SUBJECT) or "",
        body=encryptor.decrypt_text(record.body, _SUBMISSION_BODY) or "",
        use_type=UseType(record.use_type),
        consent=record.consent,
        created_at=record.created_at,
        proposed_begin_date=record.proposed_begin_date,
        proposed_end_date=record.proposed_end_date,
        documents=[
            PublicDocumentSubmission(
                id=document.id,
                file_name=encryptor.decrypt_text(
                    document.file_name, _DOCUMENT_FILE_NAME
                )
                or "",
                file_reference=document.file_reference,
                submitted_at=document.submitted_at,
            )
            for document in record.documents
        ],
        status=PendingSubmissionStatus(record.status),
        confirmed_at=record.confirmed_at,
        proposal_reference=record.proposal_reference,
    )


def _apply(
    record: PublicProposalSubmissionRecord,
    s: PendingPublicSubmission,
    encryptor: FieldEncryptor,
) -> None:
    record.id = s.id
    record.token = s.token
    record.citizen_name = encryptor.encrypt_required_text(
        s.citizen_name, _SUBMISSION_CITIZEN_NAME
    )
    record.citizen_email = encryptor.encrypt_required_text(
        s.citizen_email, _SUBMISSION_CITIZEN_EMAIL
    )
    record.subject = encryptor.encrypt_required_text(s.subject, _SUBMISSION_SUBJECT)
    record.body = encryptor.encrypt_required_text(s.body, _SUBMISSION_BODY)
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
            file_name=encryptor.encrypt_required_text(
                document.file_name, _DOCUMENT_FILE_NAME
            ),
            file_reference=document.file_reference,
            submitted_at=document.submitted_at,
        )
        for document in s.documents
    ]


class SqlAlchemyPendingSubmissionRepository:
    def __init__(self, session: AsyncSession, encryptor: FieldEncryptor) -> None:
        self._session = session
        self._encryptor = encryptor

    async def add(self, submission: PendingPublicSubmission) -> None:
        record = PublicProposalSubmissionRecord()
        _apply(record, submission, self._encryptor)
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
        return _to_domain(record, self._encryptor) if record is not None else None

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
        return _to_domain(record, self._encryptor) if record is not None else None

    async def save(self, submission: PendingPublicSubmission) -> None:
        result = await self._session.execute(
            select(PublicProposalSubmissionRecord)
            .options(selectinload(PublicProposalSubmissionRecord.documents))
            .where(PublicProposalSubmissionRecord.id == submission.id)
        )
        record = result.scalar_one()
        _apply(record, submission, self._encryptor)

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


def _token_to_domain(
    record: ProposalAmendmentTokenRecord, encryptor: FieldEncryptor
) -> ProposalAmendmentToken:
    return ProposalAmendmentToken(
        id=record.id,
        proposal_id=record.proposal_id,
        token_hash=record.token_hash,
        requester_email=encryptor.decrypt_text(
            record.requester_email, _AMENDMENT_REQUESTER_EMAIL
        )
        or "",
        correction_item_ids=list(record.correction_item_ids),
        created_at=record.created_at,
        expires_at=record.expires_at,
        used_at=record.used_at,
    )


class SqlAlchemyAmendmentTokenRepository:
    def __init__(self, session: AsyncSession, encryptor: FieldEncryptor) -> None:
        self._session = session
        self._encryptor = encryptor

    async def add(self, token: ProposalAmendmentToken) -> None:
        record = ProposalAmendmentTokenRecord(
            id=token.id,
            proposal_id=token.proposal_id,
            token_hash=token.token_hash,
            requester_email=self._encryptor.encrypt_required_text(
                token.requester_email, _AMENDMENT_REQUESTER_EMAIL
            ),
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
        return (
            _token_to_domain(record, self._encryptor) if record is not None else None
        )

    async def save(self, token: ProposalAmendmentToken) -> None:
        result = await self._session.execute(
            select(ProposalAmendmentTokenRecord).where(
                ProposalAmendmentTokenRecord.id == token.id
            )
        )
        record = result.scalar_one()
        record.requester_email = self._encryptor.encrypt_required_text(
            token.requester_email, _AMENDMENT_REQUESTER_EMAIL
        )
        record.correction_item_ids = list(token.correction_item_ids)
        record.expires_at = token.expires_at
        record.used_at = token.used_at
