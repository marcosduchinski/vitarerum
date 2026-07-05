from datetime import UTC, datetime

from app.museum_questions.domain.models import MuseumQuestion, MuseumQuestionStatus

_NOW = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def test_new_question_defaults_to_submitted_with_no_audit_fields() -> None:
    question = MuseumQuestion(
        id="q1",
        requester_name="Ana Souza",
        requester_email="ana@example.org",
        subject="Duvida sobre visita in situ",
        message="Gostaria de agendar uma visita para pesquisa.",
        created_at=_NOW,
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
