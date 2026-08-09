import base64
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.config import settings as app_settings
from app.database import Base
from app.museum_questions.domain.models import MuseumQuestion
from app.museum_questions.infrastructure.models import MuseumQuestionRecord
from app.museum_questions.infrastructure.repositories import (
    SqlAlchemyMuseumQuestionRepository,
)
from app.museum_questions.presentation import dependencies as museum_questions_deps
from app.public_submission.domain.models import (
    PendingPublicSubmission,
    ProposalAmendmentToken,
    PublicDocumentSubmission,
)
from app.public_submission.infrastructure.models import (
    ProposalAmendmentTokenRecord,
    PublicProposalSubmissionRecord,
)
from app.public_submission.infrastructure.repositories import (
    SqlAlchemyAmendmentTokenRepository,
    SqlAlchemyPendingSubmissionRepository,
)
from app.public_submission.presentation import dependencies as public_submission_deps
from app.shared.field_encryption import FieldEncryptor
from app.shared.kernel import UseType

_NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


async def _session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, expire_on_commit=False)


def _encryptor() -> FieldEncryptor:
    return FieldEncryptor(b"k" * 32)


_DB_KEY = base64.b64encode(b"d" * 32).decode("ascii")
_DECOY_FILE_KEY = base64.b64encode(b"f" * 32).decode("ascii")

_ENCRYPTOR_FACTORIES: list[tuple[Any, Callable[[], FieldEncryptor]]] = [
    (museum_questions_deps, museum_questions_deps._field_encryptor),
    (public_submission_deps, public_submission_deps._field_encryptor),
]


def _settings(owner: Any) -> Any:
    return owner.settings


@pytest.mark.parametrize("settings_owner, factory", _ENCRYPTOR_FACTORIES)
def test_context_encryptor_uses_configured_db_field_key(
    settings_owner: Any,
    factory: Callable[[], FieldEncryptor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each context must build its encryptor from ``db_field_encryption_key``.

    ``file_encryption_key`` is set to a different valid key on purpose: wiring
    the wrong setting would still produce a usable encryptor, so the assertion
    decrypts a value sealed with the *expected* key instead of merely checking
    that a round-trip works."""
    owner_settings = _settings(settings_owner)
    monkeypatch.setattr(owner_settings, "db_field_encryption_key", _DB_KEY)
    monkeypatch.setattr(owner_settings, "file_encryption_key", _DECOY_FILE_KEY)
    aad = "museum_questions.requester_email"
    sealed = FieldEncryptor.from_base64(_DB_KEY).encrypt_text("ana@example.org", aad)

    assert factory().decrypt_text(sealed, aad) == "ana@example.org"


@pytest.mark.parametrize("settings_owner, factory", _ENCRYPTOR_FACTORIES)
def test_context_encryptor_rejects_missing_db_field_key(
    settings_owner: Any,
    factory: Callable[[], FieldEncryptor],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset key must fail loudly. There is no unencrypted fallback here,
    unlike file storage — see ``.env.example``."""
    monkeypatch.setattr(_settings(settings_owner), "db_field_encryption_key", "")

    with pytest.raises(ValueError, match="db_field_encryption_key must be configured"):
        factory()


async def test_museum_questions_wiring_encrypts_through_context_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the composition, not just the repository: build the repository
    the way the context wires it and confirm the row lands encrypted."""
    monkeypatch.setattr(app_settings, "db_field_encryption_key", _DB_KEY)
    factory = await _session_factory()
    question = MuseumQuestion(
        id="q-wiring",
        requester_name="Ana Souza",
        requester_email="ana@example.org",
        subject="Sensitive subject",
        message="Sensitive message",
        created_at=_NOW,
        response_due_at=_NOW + timedelta(days=15),
    )

    async with factory() as session:
        await museum_questions_deps._repository(session).add(question)
        await session.commit()

    async with factory() as session:
        raw = (await session.execute(select(MuseumQuestionRecord))).scalar_one()
        assert raw.requester_email != "ana@example.org"
        assert raw.message != "Sensitive message"

        loaded = await museum_questions_deps._repository(session).get_by_id("q-wiring")

    assert loaded is not None
    assert loaded.requester_email == "ana@example.org"
    assert loaded.message == "Sensitive message"


async def test_public_submission_repository_stores_selected_fields_encrypted() -> None:
    factory = await _session_factory()
    submission = PendingPublicSubmission(
        id="sub-1",
        token="token-1",
        citizen_name="Ana Souza",
        citizen_email="ana@example.org",
        subject="Sensitive subject",
        body="Sensitive body",
        use_type=UseType.IN_SITU_VISIT,
        consent=True,
        created_at=_NOW,
        proposed_begin_date=date(2026, 9, 1),
        proposed_end_date=date(2026, 9, 2),
        documents=[
            PublicDocumentSubmission(
                id="doc-1",
                file_name="personal-id.pdf",
                file_reference="public-submissions/sub-1/personal-id.pdf",
                submitted_at=_NOW,
            )
        ],
    )

    async with factory() as session:
        repo = SqlAlchemyPendingSubmissionRepository(session, _encryptor())
        await repo.add(submission)
        await session.commit()

    async with factory() as session:
        raw = (
            await session.execute(
                select(PublicProposalSubmissionRecord).options(
                    selectinload(PublicProposalSubmissionRecord.documents)
                )
            )
        ).scalar_one()
        assert raw.citizen_name != "Ana Souza"
        assert raw.citizen_email != "ana@example.org"
        assert raw.subject != "Sensitive subject"
        assert raw.body != "Sensitive body"
        assert raw.documents[0].file_name != "personal-id.pdf"

        repo = SqlAlchemyPendingSubmissionRepository(session, _encryptor())
        loaded = await repo.get_by_token("token-1")

    assert loaded is not None
    assert loaded.citizen_name == "Ana Souza"
    assert loaded.citizen_email == "ana@example.org"
    assert loaded.subject == "Sensitive subject"
    assert loaded.body == "Sensitive body"
    assert loaded.documents[0].file_name == "personal-id.pdf"


async def test_museum_question_repository_filters_by_hash_and_encrypts() -> None:
    factory = await _session_factory()
    question = MuseumQuestion(
        id="q1",
        requester_name="Ana Souza",
        requester_email="ana@example.org",
        subject="Sensitive subject",
        message="Sensitive message",
        created_at=_NOW,
        response_due_at=_NOW + timedelta(days=15),
    )
    question.answer(
        body="Sensitive answer",
        answered_by="perm-staff",
        answered_at=_NOW,
        sent_at=_NOW,
    )

    async with factory() as session:
        repo = SqlAlchemyMuseumQuestionRepository(session, _encryptor())
        await repo.add(question)
        await session.commit()

    async with factory() as session:
        raw = (await session.execute(select(MuseumQuestionRecord))).scalar_one()
        assert raw.requester_name != "Ana Souza"
        assert raw.requester_email != "ana@example.org"
        assert raw.subject != "Sensitive subject"
        assert raw.message != "Sensitive message"
        assert raw.answer_body != "Sensitive answer"
        assert raw.requester_email_hash == _encryptor().lookup_hash(
            " ANA@example.org ", "museum_questions.requester_email_hash"
        )

        repo = SqlAlchemyMuseumQuestionRepository(session, _encryptor())
        rows, total = await repo.list(
            status=None,
            requester_email="ANA@example.org",
            assigned_to=None,
            unassigned_only=False,
            page=0,
            size=20,
        )

    assert total == 1
    assert rows[0].question.requester_name == "Ana Souza"
    assert rows[0].question.requester_email == "ana@example.org"
    assert rows[0].question.answer_body == "Sensitive answer"


async def test_amendment_token_repository_stores_requester_email_encrypted() -> None:
    factory = await _session_factory()
    token = ProposalAmendmentToken(
        id="amt-1",
        proposal_id="prop-1",
        token_hash="deadbeef",
        requester_email="ana@example.org",
        correction_item_ids=["ci-1"],
        created_at=_NOW,
        expires_at=_NOW + timedelta(hours=24),
    )

    async with factory() as session:
        repo = SqlAlchemyAmendmentTokenRepository(session, _encryptor())
        await repo.add(token)
        await session.commit()

    async with factory() as session:
        raw = (await session.execute(select(ProposalAmendmentTokenRecord))).scalar_one()
        assert raw.requester_email != "ana@example.org"

        repo = SqlAlchemyAmendmentTokenRepository(session, _encryptor())
        loaded = await repo.get_by_hash("deadbeef")

    assert loaded is not None
    assert loaded.requester_email == "ana@example.org"
