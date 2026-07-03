from datetime import UTC, date, datetime, timedelta

import pytest

from app.public_submission.domain.models import (
    InvalidTransition,
    PendingPublicSubmission,
    PendingSubmissionStatus,
    ProposalAmendmentToken,
    PublicDocumentSubmission,
)
from app.shared.kernel import UseType

_TOKEN_NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


def _amendment_token(**kwargs: object) -> ProposalAmendmentToken:
    defaults = dict(
        id="amt-1",
        proposal_id="prop-1",
        token_hash="hash",
        requester_email="pedro@example.test",
        correction_item_ids=["ci-1"],
        created_at=_TOKEN_NOW,
        expires_at=_TOKEN_NOW + timedelta(hours=24),
    )
    defaults.update(kwargs)
    return ProposalAmendmentToken(**defaults)  # type: ignore[arg-type]


def test_amendment_token_is_active_when_fresh() -> None:
    token = _amendment_token()
    assert token.is_active(_TOKEN_NOW) is True
    assert token.is_expired(_TOKEN_NOW) is False
    assert token.is_used is False


def test_amendment_token_expires_after_ttl() -> None:
    token = _amendment_token()
    later = _TOKEN_NOW + timedelta(hours=25)
    assert token.is_expired(later) is True
    assert token.is_active(later) is False


def test_amendment_token_mark_used_is_single_use() -> None:
    token = _amendment_token()
    token.mark_used(_TOKEN_NOW)
    assert token.is_used is True
    assert token.is_active(_TOKEN_NOW) is False
    with pytest.raises(InvalidTransition):
        token.mark_used(_TOKEN_NOW)


def test_amendment_token_used_is_not_expired() -> None:
    # A used token is inactive but not reported as "expired" (it was consumed).
    token = _amendment_token()
    token.mark_used(_TOKEN_NOW)
    assert token.is_expired(_TOKEN_NOW + timedelta(hours=48)) is False


def _pending(created_at: datetime) -> PendingPublicSubmission:
    return PendingPublicSubmission(
        id="sub-1",
        token="tok-1",
        citizen_name="Pedro Silva",
        citizen_email="pedro@example.test",
        subject="Acesso à coleção",
        body="Gostaria de estudar um espécime.",
        use_type=UseType.IN_SITU_VISIT,
        consent=True,
        created_at=created_at,
        proposed_begin_date=date(2026, 7, 1),
        proposed_end_date=date(2026, 7, 15),
        documents=[
            PublicDocumentSubmission(
                id="doc-1",
                file_name="support.pdf",
                file_reference="public-submissions/sub-1/support.pdf",
                submitted_at=created_at,
            )
        ],
    )


def test_confirm_sets_status_and_reference() -> None:
    now = datetime(2026, 6, 26, tzinfo=UTC)
    submission = _pending(now)

    submission.confirm(proposal_reference="VRP-20260626-0001", occurred_at=now)

    assert submission.status is PendingSubmissionStatus.CONFIRMED
    assert submission.is_confirmed
    assert submission.proposal_reference == "VRP-20260626-0001"
    assert submission.confirmed_at == now


def test_confirm_twice_raises() -> None:
    now = datetime(2026, 6, 26, tzinfo=UTC)
    submission = _pending(now)
    submission.confirm(proposal_reference="VRP-20260626-0001", occurred_at=now)

    with pytest.raises(InvalidTransition, match="already confirmed"):
        submission.confirm(proposal_reference="VRP-20260626-0002", occurred_at=now)


def test_is_expired_true_after_ttl() -> None:
    created = datetime(2026, 6, 26, 10, 0, tzinfo=UTC)
    submission = _pending(created)
    later = created + timedelta(hours=25)

    assert submission.is_expired(later, timedelta(hours=24)) is True


def test_is_expired_false_within_ttl() -> None:
    created = datetime(2026, 6, 26, 10, 0, tzinfo=UTC)
    submission = _pending(created)
    later = created + timedelta(hours=1)

    assert submission.is_expired(later, timedelta(hours=24)) is False


def test_confirmed_submission_never_expires() -> None:
    created = datetime(2026, 6, 26, 10, 0, tzinfo=UTC)
    submission = _pending(created)
    submission.confirm(proposal_reference="VRP-20260626-0001", occurred_at=created)
    long_after = created + timedelta(days=365)

    assert submission.is_expired(long_after, timedelta(hours=24)) is False


def test_pending_submission_requires_at_least_one_document() -> None:
    now = datetime(2026, 6, 26, tzinfo=UTC)

    with pytest.raises(ValueError, match="At least one"):
        PendingPublicSubmission(
            id="sub-1",
            token="tok-1",
            citizen_name="Pedro Silva",
            citizen_email="pedro@example.test",
            subject="Acesso à coleção",
            body="Gostaria de estudar um espécime.",
            use_type=UseType.IN_SITU_VISIT,
            consent=True,
            created_at=now,
            proposed_begin_date=date(2026, 7, 1),
            proposed_end_date=date(2026, 7, 15),
            documents=[],
        )
