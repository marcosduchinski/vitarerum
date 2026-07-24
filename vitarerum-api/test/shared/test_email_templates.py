from app.shared.email_templates import (
    document_correction_invite_email,
    museum_question_out_of_scope_email,
    password_changed_email,
    password_reset_email,
    public_submission_confirmation_email,
    requester_access_created_email,
)


def test_predefined_email_templates_are_bilingual() -> None:
    templates = [
        password_reset_email("Ana", "https://example.test/reset"),
        password_changed_email("Ana"),
        public_submission_confirmation_email("Ana", "https://example.test/confirm"),
        document_correction_invite_email(
            "Ana", "https://example.test/edit", ["Missing signature"]
        ),
        museum_question_out_of_scope_email("Visit request"),
        requester_access_created_email(
            "Ana", "https://example.test/login", "temporary-password"
        ),
    ]

    for template in templates:
        assert " / " in template.subject
        assert "\n\n---\n\n" in template.body


def test_public_submission_confirmation_subject_has_no_trailing_separator() -> None:
    template = public_submission_confirmation_email(
        "Ana", "https://example.test/confirm"
    )

    assert template.subject == "Confirme o seu pedido / Confirm your request"
