"""DB-backed coverage for the document-correction / amendment flow.

Exercises the SQLAlchemy round-trip of correction items and the amendment use
cases over a real (in-memory) session, plus the public amendment-token repo."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.identity.public import Actor, GroupName
from app.public_submission.domain.models import ProposalAmendmentToken
from app.public_submission.infrastructure.repositories import (
    SqlAlchemyAmendmentTokenRepository,
)
from app.use_of_collections.application.use_cases import (
    CorrectionScopeError,
    DocumentCorrectionInput,
    RemoveAmendmentDocument,
    RemoveAmendmentDocumentInput,
    RequestDocumentCorrections,
    RequestDocumentCorrectionsInput,
    SubmitAmendmentCorrections,
    SubmitAmendmentCorrectionsInput,
    SubmitAmendmentDocument,
    SubmitAmendmentDocumentInput,
)
from app.use_of_collections.domain.enums import (
    DocumentCorrectionStatus,
    ProposalStatus,
    SubmissionChannel,
    UseType,
)
from app.use_of_collections.domain.models import (
    Document,
    DocumentId,
    DocumentType,
    EmailAddress,
    Proposal,
    ProposalId,
    ReferenceNumber,
    RequesterContact,
    UnsatisfiedCorrection,
)
from app.use_of_collections.infrastructure.repositories import (
    SqlAlchemyProposalRepository,
)

_NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
_STAFF = Actor(
    id="staff-1",  # type: ignore[arg-type]
    group=GroupName.COLLECTIONS_MANAGEMENT,
    email="curator@museum.pt",
)


class _FakeStorage:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def save(self, content: bytes, filename: str) -> str:
        self.saved[filename] = content
        return filename

    async def read(self, file_reference: str) -> bytes:
        return self.saved[file_reference]

    async def delete(self, file_reference: str) -> None:
        self.deleted.append(file_reference)
        self.saved.pop(file_reference, None)


async def _session_factory() -> async_sessionmaker:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


def _pending_proposal(with_document: bool = True) -> Proposal:
    documents = (
        [
            Document(
                id=DocumentId("doc-1"),
                type=DocumentType("ID_CARD"),
                file_name="id.pdf",
                file_reference="proposals/prop-1/id.pdf",
                submitted_at=_NOW,
                submitted_by=None,  # public submission → no PermissionId
            )
        ]
        if with_document
        else []
    )
    return Proposal(
        id=ProposalId("prop-1"),
        reference_number=ReferenceNumber("VRP-20260703-0001"),
        title="Public request",
        collection_use_project_id=None,
        intended_use=UseType.IN_SITU_VISIT,
        begin_date=date(2026, 8, 1),
        end_date=date(2026, 8, 2),
        status=ProposalStatus.PENDING,
        requested_by=None,
        submitted_at=_NOW,
        submission_channel=SubmissionChannel.PUBLIC,
        requester_contact=RequesterContact(
            name="Pedro Silva", email=EmailAddress("pedro@example.test")
        ),
        documents=documents,
    )


async def test_correction_items_round_trip_with_null_submitted_by() -> None:
    factory = await _session_factory()
    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        await repo.add(_pending_proposal())
        await session.commit()

        # Staff requests a correction on the public document (submitted_by=None).
        await RequestDocumentCorrections(repo).execute(
            RequestDocumentCorrectionsInput(
                proposal_id=ProposalId("prop-1"),
                caller=_STAFF,
                items=[
                    DocumentCorrectionInput(
                        document_type="ID_CARD",
                        reason="Illegible",
                        document_id="doc-1",
                    )
                ],
                requester_email="pedro@example.test",
                requester_name="Pedro Silva",
            )
        )
        await session.commit()

    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        reloaded = await repo.get_by_id(ProposalId("prop-1"))
    assert reloaded is not None
    assert reloaded.documents[0].submitted_by is None
    assert len(reloaded.correction_items) == 1
    item = reloaded.correction_items[0]
    assert item.status == DocumentCorrectionStatus.REQUESTED
    assert item.document_id == "doc-1"
    assert item.document_type == DocumentType("ID_CARD")


async def _seed_missing_cv_correction(factory: async_sessionmaker) -> None:
    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        await repo.add(_pending_proposal(with_document=False))
        await RequestDocumentCorrections(repo).execute(
            RequestDocumentCorrectionsInput(
                proposal_id=ProposalId("prop-1"),
                caller=_STAFF,
                items=[DocumentCorrectionInput(document_type="CV", reason="Missing")],
                requester_email="pedro@example.test",
                requester_name="Pedro Silva",
            )
        )
        await session.commit()


async def test_amendment_add_then_submit_resolves() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    await _seed_missing_cv_correction(factory)

    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        document = await SubmitAmendmentDocument(repo, storage).execute(
            SubmitAmendmentDocumentInput(
                proposal_id=ProposalId("prop-1"),
                file_content=b"%PDF-1.4 cv",
                file_name="cv.pdf",
                document_type="CV",
                allowed_document_types={"CV"},
            )
        )
        await session.commit()
    assert document.submitted_by is None

    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        item_id = (
            (await repo.get_by_id(ProposalId("prop-1"))).correction_items[0].id  # type: ignore[union-attr]
        )
        await SubmitAmendmentCorrections(repo).execute(
            SubmitAmendmentCorrectionsInput(
                proposal_id=ProposalId("prop-1"), item_ids=[item_id]
            )
        )
        await session.commit()

    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        final = await repo.get_by_id(ProposalId("prop-1"))
    assert final is not None
    assert final.status == ProposalStatus.PENDING
    assert final.correction_items[0].status == DocumentCorrectionStatus.RESOLVED


async def test_amendment_submit_without_document_is_rejected() -> None:
    factory = await _session_factory()
    await _seed_missing_cv_correction(factory)
    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        with pytest.raises(UnsatisfiedCorrection):
            await SubmitAmendmentCorrections(repo).execute(
                SubmitAmendmentCorrectionsInput(proposal_id=ProposalId("prop-1"))
            )


async def test_amendment_upload_out_of_scope_is_rejected() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    await _seed_missing_cv_correction(factory)
    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        with pytest.raises(CorrectionScopeError):
            await SubmitAmendmentDocument(repo, storage).execute(
                SubmitAmendmentDocumentInput(
                    proposal_id=ProposalId("prop-1"),
                    file_content=b"%PDF-1.4 x",
                    file_name="passport.pdf",
                    document_type="PASSPORT",  # not the requested CV
                    allowed_document_types={"CV"},
                )
            )
    assert storage.saved == {}  # scope checked before any file write


async def test_amendment_upload_free_text_type_trims_and_matches_scope() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        await repo.add(_pending_proposal(with_document=False))
        await RequestDocumentCorrections(repo).execute(
            RequestDocumentCorrectionsInput(
                proposal_id=ProposalId("prop-1"),
                caller=_STAFF,
                items=[
                    DocumentCorrectionInput(
                        document_type="  Insurance certificate  ", reason="Missing"
                    )
                ],
                requester_email="pedro@example.test",
                requester_name="Pedro Silva",
            )
        )
        await session.commit()

    # The scope is derived from the stored (now trimmed) correction item type.
    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        proposal = await repo.get_by_id(ProposalId("prop-1"))
        assert proposal is not None
        allowed = {ci.document_type.value for ci in proposal.correction_items}
    assert allowed == {"Insurance certificate"}

    # Even if the re-sent type carries stray spaces, normalisation makes it match.
    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        document = await SubmitAmendmentDocument(repo, storage).execute(
            SubmitAmendmentDocumentInput(
                proposal_id=ProposalId("prop-1"),
                file_content=b"%PDF-1.4 x",
                file_name="cert.pdf",
                document_type="  Insurance certificate  ",
                allowed_document_types=allowed,
            )
        )
        await session.commit()
    assert document.type.value == "Insurance certificate"


async def test_amendment_upload_blank_type_rejected() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    await _seed_missing_cv_correction(factory)
    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        with pytest.raises(ValueError, match="Document type is required"):
            await SubmitAmendmentDocument(repo, storage).execute(
                SubmitAmendmentDocumentInput(
                    proposal_id=ProposalId("prop-1"),
                    file_content=b"%PDF-1.4 x",
                    file_name="blank.pdf",
                    document_type="   ",
                    allowed_document_types={"CV"},
                )
            )
    assert storage.saved == {}  # invalid type rejected before any file write


async def test_amendment_upload_replaces_flagged_document() -> None:
    """Uploading a corrected file for a replacement-type item atomically detaches
    the flagged document — the citizen doesn't have to remove it by hand first."""
    factory = await _session_factory()
    storage = _FakeStorage()

    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        await repo.add(_pending_proposal())  # seeds doc-1 (ID_CARD)
        await RequestDocumentCorrections(repo).execute(
            RequestDocumentCorrectionsInput(
                proposal_id=ProposalId("prop-1"),
                caller=_STAFF,
                items=[
                    DocumentCorrectionInput(
                        document_type="ID_CARD",
                        reason="Illegible",
                        document_id="doc-1",
                    )
                ],
                requester_email="pedro@example.test",
                requester_name="Pedro Silva",
            )
        )
        await session.commit()

    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        new_document = await SubmitAmendmentDocument(repo, storage).execute(
            SubmitAmendmentDocumentInput(
                proposal_id=ProposalId("prop-1"),
                file_content=b"%PDF-1.4 id",
                file_name="id-clear.pdf",
                document_type="ID_CARD",
                allowed_document_types={"ID_CARD"},
            )
        )
        await session.commit()

    assert storage.deleted == ["proposals/prop-1/id.pdf"]

    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        after = await repo.get_by_id(ProposalId("prop-1"))
    assert after is not None
    assert [d.id for d in after.documents] == [new_document.id]


async def test_amendment_remove_reclaims_file() -> None:
    factory = await _session_factory()
    storage = _FakeStorage()
    await _seed_missing_cv_correction(factory)
    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        document = await SubmitAmendmentDocument(repo, storage).execute(
            SubmitAmendmentDocumentInput(
                proposal_id=ProposalId("prop-1"),
                file_content=b"%PDF-1.4 cv",
                file_name="cv.pdf",
                document_type="CV",
                allowed_document_types={"CV"},
            )
        )
        await session.commit()

    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        await RemoveAmendmentDocument(repo, storage).execute(
            RemoveAmendmentDocumentInput(
                proposal_id=ProposalId("prop-1"),
                document_id=DocumentId(document.id),
                allowed_ids={DocumentId(document.id)},
            )
        )
        await session.commit()
    assert storage.deleted == [document.file_reference]

    async with factory() as session:
        repo = SqlAlchemyProposalRepository(session)
        after = await repo.get_by_id(ProposalId("prop-1"))
    assert after is not None
    assert after.documents == []


async def test_amendment_token_repository_round_trip() -> None:
    factory = await _session_factory()
    token = ProposalAmendmentToken(
        id="amt-1",
        proposal_id="prop-1",
        token_hash="deadbeef",
        requester_email="pedro@example.test",
        correction_item_ids=["ci-1", "ci-2"],
        created_at=_NOW,
        expires_at=_NOW + timedelta(hours=24),
    )
    async with factory() as session:
        repo = SqlAlchemyAmendmentTokenRepository(session)
        await repo.add(token)
        await session.commit()

    async with factory() as session:
        repo = SqlAlchemyAmendmentTokenRepository(session)
        loaded = await repo.get_by_hash("deadbeef")
        assert loaded is not None
        assert loaded.correction_item_ids == ["ci-1", "ci-2"]
        loaded.mark_used(_NOW)
        await repo.save(loaded)
        await session.commit()

    async with factory() as session:
        repo = SqlAlchemyAmendmentTokenRepository(session)
        reloaded = await repo.get_by_hash("deadbeef")
    assert reloaded is not None
    assert reloaded.is_used is True
