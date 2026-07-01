from datetime import UTC, date, datetime, timedelta

import pytest

from app.public_submission.domain.models import (
    InvalidTransition,
    PendingPublicSubmission,
    PendingSubmissionStatus,
    PublicDocumentSubmission,
)
from app.shared.kernel import UseType


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
