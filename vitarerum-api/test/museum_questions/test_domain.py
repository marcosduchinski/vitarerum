from datetime import UTC, datetime, timedelta

import pytest

from app.museum_questions.domain.models import (
    InvalidMuseumQuestionTransition,
    MuseumQuestion,
    MuseumQuestionStatus,
)

_NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_new_question_defaults_to_submitted_with_no_audit_fields() -> None:
    question = MuseumQuestion(
        id="q1",
        requester_name="Ana Souza",
        requester_email="ana@example.org",
        subject="Duvida sobre visita in situ",
        message="Gostaria de agendar uma visita para pesquisa.",
        created_at=_NOW,
        response_due_at=_NOW + timedelta(days=15),
    )
    assert question.status == MuseumQuestionStatus.SUBMITTED
    assert question.answered_at is None
    assert question.answered_by is None
    assert question.answer_body is None
    assert question.answer_sent_at is None
    assert question.out_of_scope_at is None
    assert question.out_of_scope_by is None
    assert question.out_of_scope_reason is None
    assert question.out_of_scope_email_sent_at is None
    assert question.closed_at is None
    assert question.closed_by is None


def test_answer_transitions_submitted_question() -> None:
    question = _question()
    question.answer(
        body="  Response body  ",
        answered_by="perm-1",
        answered_at=_NOW,
        sent_at=_NOW,
    )
    assert question.status == MuseumQuestionStatus.ANSWERED
    assert question.answer_body == "Response body"
    assert question.answered_by == "perm-1"
    assert question.answer_sent_at == _NOW


def test_answer_transitions_in_progress_question() -> None:
    question = _question(MuseumQuestionStatus.IN_PROGRESS)
    question.answer(
        body="Response body",
        answered_by="perm-1",
        answered_at=_NOW,
        sent_at=_NOW,
    )
    assert question.status == MuseumQuestionStatus.ANSWERED


def test_forward_transitions_submitted_question_to_in_progress() -> None:
    question = _question()
    question.forward(target_permission_id="perm-1")
    assert question.status == MuseumQuestionStatus.IN_PROGRESS
    assert question.assigned_to == "perm-1"


def test_forward_keeps_reassigned_question_in_progress() -> None:
    question = _question(MuseumQuestionStatus.IN_PROGRESS)
    question.forward(target_permission_id="perm-2")
    assert question.status == MuseumQuestionStatus.IN_PROGRESS
    assert question.assigned_to == "perm-2"


def test_close_rejects_submitted_question() -> None:
    question = _question()
    with pytest.raises(InvalidMuseumQuestionTransition):
        question.close(by="perm-1", closed_at=_NOW)


def _question(
    status: MuseumQuestionStatus = MuseumQuestionStatus.SUBMITTED,
) -> MuseumQuestion:
    return MuseumQuestion(
        id="q1",
        requester_name="Ana Souza",
        requester_email="ana@example.org",
        subject="Duvida sobre visita in situ",
        message="Gostaria de agendar uma visita para pesquisa.",
        created_at=_NOW,
        response_due_at=_NOW + timedelta(days=15),
        status=status,
    )


def test_submitted_question_is_overdue_after_response_due_at() -> None:
    question = _question()
    assert question.is_unanswered_overdue(_NOW + timedelta(days=15))


def test_in_progress_question_is_overdue_after_response_due_at() -> None:
    question = _question(MuseumQuestionStatus.IN_PROGRESS)
    assert question.is_unanswered_overdue(_NOW + timedelta(days=15))


def test_answered_question_is_not_overdue() -> None:
    question = _question()
    question.answer(
        body="Response body",
        answered_by="perm-1",
        answered_at=_NOW,
        sent_at=_NOW,
    )
    assert not question.is_unanswered_overdue(_NOW + timedelta(days=16))
