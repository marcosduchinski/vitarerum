from __future__ import annotations

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True, slots=True)
class EmailTemplate:
    subject: str
    body: str


def password_reset_email(display_name: str, link: str) -> EmailTemplate:
    return EmailTemplate(
        subject="Redefinição de password / Password reset",
        body=(
            f"Olá {display_name},\n\n"
            "Recebemos um pedido para redefinir a sua password. Para "
            "continuar, aceda ao link abaixo (válido por tempo limitado):\n\n"
            f"{link}\n\n"
            "Se não foi você quem pediu, ignore esta mensagem. A sua password "
            "atual continua válida.\n\n"
            "---\n\n"
            f"Hello {display_name},\n\n"
            "We received a request to reset your password. To continue, open "
            "the link below (valid for a limited time):\n\n"
            f"{link}\n\n"
            "If this was not you, ignore this message. Your current password "
            "remains valid."
        ),
    )


def password_changed_email(display_name: str) -> EmailTemplate:
    return EmailTemplate(
        subject="A sua password foi alterada / Your password was changed",
        body=(
            f"Olá {display_name},\n\n"
            "A password da sua conta Vitarerum acabou de ser alterada.\n\n"
            "Se foi você, pode ignorar esta mensagem. Se não foi, contacte o "
            "suporte o mais rápido possível.\n\n"
            "---\n\n"
            f"Hello {display_name},\n\n"
            "The password for your Vitarerum account has just been changed.\n\n"
            "If this was you, you can ignore this message. If it was not, "
            "please contact support as soon as possible."
        ),
    )


def public_submission_confirmation_email(citizen_name: str, link: str) -> EmailTemplate:
    return EmailTemplate(
        subject="Confirme o seu pedido / Confirm your request",
        body=(
            f"Olá {citizen_name},\n\n"
            "Para concluir o seu pedido, confirme através do link abaixo:\n\n"
            f"{link}\n\n"
            "Se não foi você, ignore esta mensagem.\n\n"
            "---\n\n"
            f"Hello {citizen_name},\n\n"
            "To complete your request, confirm it using the link below:\n\n"
            f"{link}\n\n"
            "If this was not you, ignore this message."
        ),
    )


def document_correction_invite_email(
    citizen_name: str, link: str, reasons: list[str]
) -> EmailTemplate:
    pt_reasons = _bullet_block("Documentos a corrigir", reasons)
    en_reasons = _bullet_block("Documents to correct", reasons)
    return EmailTemplate(
        subject=(
            "Correção de documentos do seu pedido / "
            "Document corrections for your request"
        ),
        body=(
            f"Olá {citizen_name},\n\n"
            "A análise do seu pedido identificou documentos que precisam de "
            f"correção.{pt_reasons}\n\n"
            "Para corrigir, aceda ao link abaixo (válido por tempo limitado):\n\n"
            f"{link}\n\n"
            "Se não foi você, ignore esta mensagem.\n\n"
            "---\n\n"
            f"Hello {citizen_name},\n\n"
            "The review of your request identified documents that need "
            f"correction.{en_reasons}\n\n"
            "To correct them, open the link below (valid for a limited time):\n\n"
            f"{link}\n\n"
            "If this was not you, ignore this message."
        ),
    )


def museum_question_answer_subject(subject: str) -> str:
    return f"Resposta do Vitarerum / Vitarerum response: {subject}"


def museum_question_answer_text_body(
    requester_name: str, sanitized_answer_text: str
) -> str:
    return (
        f"Olá {requester_name},\n\n"
        f"{sanitized_answer_text}\n\n"
        "Vitarerum\n\n"
        "---\n\n"
        f"Hello {requester_name},\n\n"
        f"{sanitized_answer_text}\n\n"
        "Vitarerum"
    )


def museum_question_answer_html_body(
    requester_name: str, sanitized_answer_html: str
) -> str:
    escaped_name = escape(requester_name)
    return (
        "<!doctype html><html><body>"
        f"<p>Olá {escaped_name},</p>"
        f"{sanitized_answer_html}"
        "<p>Vitarerum</p>"
        "<hr>"
        f"<p>Hello {escaped_name},</p>"
        f"{sanitized_answer_html}"
        "<p>Vitarerum</p>"
        "</body></html>"
    )


def museum_question_out_of_scope_email(subject: str) -> EmailTemplate:
    return EmailTemplate(
        subject=f"Pergunte ao Museu / Ask the Museum: {subject}",
        body=(
            "Obrigado por entrar em contato com o Vitarerum.\n\n"
            "Neste momento, o Pergunte ao Museu está disponível apenas para "
            "perguntas relacionadas ao uso de coleções, especialmente visitas "
            "in situ para investigação.\n\n"
            "Perguntas sobre exposições, empréstimos, eventos, atividades "
            "educativas ou outros serviços do museu ainda não são tratadas por "
            "este canal e serão disponibilizadas em uma versão futura.\n\n"
            "Agradecemos a compreensão.\n\n"
            "---\n\n"
            "Thank you for contacting Vitarerum.\n\n"
            "At this time, Ask the Museum is available only for questions "
            "related to the use of collections, especially in situ research "
            "visits.\n\n"
            "Questions about exhibitions, loans, events, educational activities "
            "or other museum services are not yet handled through this channel "
            "and will be made available in a future version.\n\n"
            "Thank you for your understanding."
        ),
    )


def museum_question_submitted_staff_email(
    *,
    recipient_name: str,
    requester_name: str,
    subject: str,
    link: str,
) -> EmailTemplate:
    return EmailTemplate(
        subject=f"Nova pergunta pública / New public inquiry: {subject}",
        body=(
            f"Olá {recipient_name},\n\n"
            f"{requester_name} submeteu uma nova pergunta pública ao museu.\n\n"
            "Os curadores e gestores de coleções podem rever a pergunta no "
            f"Vitarerum: {link}\n\n"
            "---\n\n"
            f"Hello {recipient_name},\n\n"
            f"{requester_name} submitted a new public inquiry to the museum.\n\n"
            "Curators and collection managers can review the inquiry in "
            f"Vitarerum: {link}"
        ),
    )


def requester_access_created_email(
    requester_name: str, login_url: str, temporary_password: str
) -> EmailTemplate:
    return EmailTemplate(
        subject=(
            "O seu acesso à área pessoal do Vitarerum / "
            "Your access to the Vitarerum personal area"
        ),
        body=(
            f"Olá {requester_name},\n\n"
            "A sua proposta foi aprovada e criámos um acesso à sua área "
            "pessoal no Vitarerum.\n\n"
            f"Link de acesso: {login_url}\n"
            f"Senha provisória: {temporary_password}\n\n"
            "Recomendamos que altere esta senha assim que possível.\n\n"
            "---\n\n"
            f"Hello {requester_name},\n\n"
            "Your proposal was approved and we created access to your personal "
            "area in Vitarerum.\n\n"
            f"Access link: {login_url}\n"
            f"Temporary password: {temporary_password}\n\n"
            "We recommend changing this password as soon as possible."
        ),
    )


def proposal_forwarded_email(
    *,
    recipient_name: str,
    proposal_reference: str,
    forwarded_by_name: str,
    note: str | None,
    link: str,
) -> EmailTemplate:
    note_block_pt = f"\n\nNota: {note}" if note else ""
    note_block_en = f"\n\nNote: {note}" if note else ""
    return EmailTemplate(
        subject=(
            f"Proposta {proposal_reference} redirecionada / "
            f"Proposal {proposal_reference} forwarded"
        ),
        body=(
            f"Olá {recipient_name},\n\n"
            f"{forwarded_by_name} redirecionou a proposta {proposal_reference} "
            f"para si.{note_block_pt}\n\n"
            f"Aceda à proposta: {link}\n\n"
            "---\n\n"
            f"Hello {recipient_name},\n\n"
            f"{forwarded_by_name} forwarded proposal {proposal_reference} "
            f"to you.{note_block_en}\n\n"
            f"Open the proposal: {link}"
        ),
    )


def proposal_assigned_email(
    *,
    recipient_name: str,
    proposal_reference: str,
    assigned_by_name: str,
    note: str | None,
    link: str,
) -> EmailTemplate:
    note_block_pt = f"\n\nNota: {note}" if note else ""
    note_block_en = f"\n\nNote: {note}" if note else ""
    return EmailTemplate(
        subject=(
            f"Proposta {proposal_reference} atribuída / "
            f"Proposal {proposal_reference} assigned"
        ),
        body=(
            f"Olá {recipient_name},\n\n"
            f"{assigned_by_name} atribuiu a proposta {proposal_reference} "
            f"a si.{note_block_pt}\n\n"
            f"Aceda à proposta: {link}\n\n"
            "---\n\n"
            f"Hello {recipient_name},\n\n"
            f"{assigned_by_name} assigned proposal {proposal_reference} "
            f"to you.{note_block_en}\n\n"
            f"Open the proposal: {link}"
        ),
    )


def proposal_taken_over_email(
    *,
    recipient_name: str,
    proposal_reference: str,
    taken_over_by_name: str,
    note: str | None,
    link: str,
) -> EmailTemplate:
    note_block_pt = f"\n\nNota: {note}" if note else ""
    note_block_en = f"\n\nNote: {note}" if note else ""
    return EmailTemplate(
        subject=(
            f"Proposta {proposal_reference} assumida por outro membro / "
            f"Proposal {proposal_reference} taken over"
        ),
        body=(
            f"Olá {recipient_name},\n\n"
            f"{taken_over_by_name} assumiu a proposta {proposal_reference}, "
            f"que estava atribuída a si.{note_block_pt}\n\n"
            f"Aceda à proposta: {link}\n\n"
            "---\n\n"
            f"Hello {recipient_name},\n\n"
            f"{taken_over_by_name} took over proposal {proposal_reference}, "
            f"which was assigned to you.{note_block_en}\n\n"
            f"Open the proposal: {link}"
        ),
    )


def proposal_submitted_email(
    *,
    recipient_name: str,
    proposal_reference: str,
    submitted_by_name: str,
    link: str,
) -> EmailTemplate:
    return EmailTemplate(
        subject=(
            f"Nova proposta {proposal_reference} submetida / "
            f"New proposal {proposal_reference} submitted"
        ),
        body=(
            f"Olá {recipient_name},\n\n"
            f"{submitted_by_name} submeteu a proposta {proposal_reference}.\n\n"
            f"Aceda à proposta: {link}\n\n"
            "---\n\n"
            f"Hello {recipient_name},\n\n"
            f"{submitted_by_name} submitted proposal {proposal_reference}.\n\n"
            f"Open the proposal: {link}"
        ),
    )


def proposal_documents_submitted_email(
    *,
    recipient_name: str,
    proposal_reference: str,
    submitted_by_name: str,
    link: str,
) -> EmailTemplate:
    return EmailTemplate(
        subject=(
            f"Documentos enviados para {proposal_reference} / "
            f"Documents submitted for {proposal_reference}"
        ),
        body=(
            f"Olá {recipient_name},\n\n"
            f"{submitted_by_name} enviou documentos para a proposta "
            f"{proposal_reference}.\n\n"
            f"Aceda à proposta: {link}\n\n"
            "---\n\n"
            f"Hello {recipient_name},\n\n"
            f"{submitted_by_name} submitted documents for proposal "
            f"{proposal_reference}.\n\n"
            f"Open the proposal: {link}"
        ),
    )


def proposal_corrections_submitted_email(
    *,
    recipient_name: str,
    proposal_reference: str,
    submitted_by_name: str,
    link: str,
) -> EmailTemplate:
    return EmailTemplate(
        subject=(
            f"Correções enviadas para {proposal_reference} / "
            f"Corrections submitted for {proposal_reference}"
        ),
        body=(
            f"Olá {recipient_name},\n\n"
            f"{submitted_by_name} enviou correções para a proposta "
            f"{proposal_reference}.\n\n"
            f"Aceda à proposta: {link}\n\n"
            "---\n\n"
            f"Hello {recipient_name},\n\n"
            f"{submitted_by_name} submitted corrections for proposal "
            f"{proposal_reference}.\n\n"
            f"Open the proposal: {link}"
        ),
    )


def proposal_rejected_email(
    *,
    requester_name: str,
    proposal_reference: str,
    rejected_by_name: str,
    reason: str,
    link: str,
) -> EmailTemplate:
    return EmailTemplate(
        subject=(
            f"Proposta {proposal_reference} rejeitada / "
            f"Proposal {proposal_reference} rejected"
        ),
        body=(
            f"Olá {requester_name},\n\n"
            f"{rejected_by_name} rejeitou a proposta {proposal_reference}.\n\n"
            f"Motivo: {reason}\n\n"
            f"Aceda à proposta: {link}\n\n"
            "---\n\n"
            f"Hello {requester_name},\n\n"
            f"{rejected_by_name} rejected proposal {proposal_reference}.\n\n"
            f"Reason: {reason}\n\n"
            f"Open the proposal: {link}"
        ),
    )


def _bullet_block(title: str, items: list[str]) -> str:
    if not items:
        return ""
    bullet_list = "\n".join(f"  - {item}" for item in items)
    return f"\n\n{title}:\n{bullet_list}"
