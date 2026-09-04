# SPEC-011 — Pergunte ao Museu

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-011 |
| Estado | Implementado |
| Contexto delimitado | `app/museum_questions` |
| Escrita a partir de | `app/museum_questions/`, `test/museum_questions/`, contratos 13 e 14 |
| Specs relacionadas | [SPEC-010](../010-submissao-publica/spec.md), [SPEC-018](../018-notificacoes/spec.md) |

## 1. Problema

Nem todo o contacto com o museu e um pedido formal de acesso. Muitas mensagens
sao perguntas simples — "posso visitar a colecao para a minha tese?" — e
obriga-las a passar pelo circuito completo de proposta afasta quem pergunta e
enche a fila do staff com pedidos que nao sao pedidos.

## 2. Objetivo

Oferecer um canal publico leve para perguntas, com uma unica resposta manual do
staff, sem fio de conversa nem consulta publica de estado, e com um prazo de
resposta que a instituicao consegue vigiar.

## 3. Escopo declarado ao cidadao

Neste momento so recebem resposta manual as perguntas sobre uso de colecoes,
sobretudo visitas in situ para investigacao. As restantes **nao sao recusadas na
submissao**: sao aceites, marcadas fora de ambito pelo staff e encerradas com
resposta automatica. O formulario publico anuncia esta regra.

A escolha e deliberada: recusar a entrada obrigaria o cidadao a adivinhar a
fronteira administrativa do museu antes de conseguir escrever.

## 4. Linguagem ubiqua

- **Pergunta**: mensagem publica. Estados `SUBMITTED`, `IN_PROGRESS`, `ANSWERED`, `OUT_OF_SCOPE`, `CLOSED`.
- **Encaminhamento**: atribuicao da pergunta a um membro do staff; muda o estado para `IN_PROGRESS`.
- **Prazo de resposta (`responseDueAt`)**: 15 dias de calendario a contar da submissao.
- **Em atraso**: pergunta `SUBMITTED` ou `IN_PROGRESS`, sem resposta, com prazo ultrapassado.

---

## 5. Requisitos funcionais — canal publico

### RF-001 — Submissao sem autenticacao

`POST /api/v1/public/museum-questions`, em JSON ou `multipart/form-data` quando
ha imagens.

| Campo | Obrigatorio | Restricao |
| --- | --- | --- |
| `requesterName` | sim | 1–120 caracteres |
| `requesterEmail` | sim | ate 180 caracteres; recebe a resposta |
| `subject` | sim | 1–200 caracteres |
| `message` | sim | 1–4000 caracteres |
| `consent` | sim | tem de ser `true` (RGPD) |
| `captchaToken` | sim | verificado no servidor |
| `website` | nao | campo-armadilha |
| `attachments` | nao | 0–10 ficheiros, PNG/JPEG, ate 5 MiB cada e 25 MiB no total |

Resposta `202` com ecra de confirmacao mascarado. Nao e devolvido nenhum
identificador visivel ao staff.

### RF-002 — Sem duplo opt-in

Ao contrario da submissao de proposta
([SPEC-010](../010-submissao-publica/spec.md)), uma submissao valida e
persistida como `SUBMITTED` numa unica chamada. Nao ha email de confirmacao a
clicar.

A diferenca justifica-se pelo risco: uma pergunta nao cria conta, nao entra no
circuito de decisao e nao gera documentacao institucional.

### RF-003 — Protecoes do canal aberto

Verificacao de Turnstile, limitacao de frequencia por IP, por email e global
(`429` com `Retry-After`), limites de comprimento, remocao de caracteres de
controlo e recusa de CR/LF em campos que entram no email.

### RF-004 — Campo-armadilha silencioso

`website` preenchido produz `202` sem trabalho.

### RF-005 — Imagens verificadas

Anexos sao verificados por assinatura de conteudo, limitados em numero e
tamanho, e guardados fora de qualquer raiz web. Se a persistencia falhar depois
de os ficheiros serem escritos, os ficheiros sao descartados.

### RF-006 — Sem credenciais

Os endpoints publicos nao aceitam nem dependem de cookies ou cabecalhos de
autenticacao. CORS restrito a origem publica.

---

## 6. Requisitos funcionais — canal interno

### RF-007 — Autorizacao

Endpoints internos exigem token e `X-Permission-Id`, restritos a `CURATORIAL` e
`COLLECTIONS_MANAGEMENT`. `DIRECTION` nao tem acesso inicial a fila.

### RF-008 — Fila de trabalho

`GET /museum-questions` devolve fila paginada ordenada por `createdAt` ascendente,
com filtros por estado, email do requerente, responsavel atribuido e apenas nao
atribuidas. Os itens de lista trazem `attachmentCount`, nao os metadados
completos dos anexos.

O filtro por email do requerente opera sobre o **hash de pesquisa** do valor
cifrado, nunca sobre texto em claro.

### RF-009 — Transicoes validas

```text
SUBMITTED -> ANSWERED
SUBMITTED -> OUT_OF_SCOPE
SUBMITTED -> IN_PROGRESS (encaminhamento)
IN_PROGRESS -> ANSWERED
IN_PROGRESS -> OUT_OF_SCOPE
IN_PROGRESS -> IN_PROGRESS (novo encaminhamento)
ANSWERED  -> CLOSED
OUT_OF_SCOPE -> CLOSED
```

`SUBMITTED -> CLOSED` e invalido: nada se encerra sem ter sido respondido ou
declarado fora de ambito.

### RF-010 — Resposta manual

`POST /museum-questions/{id}/answer` e valido a partir de `SUBMITTED` ou
`IN_PROGRESS`. Envia o email e regista quem respondeu, quando, o corpo da
resposta e o instante do envio.

### RF-011 — Fora de ambito

`POST /museum-questions/{id}/mark-out-of-scope` aceita razao opcional, e valido
a partir de `SUBMITTED` ou `IN_PROGRESS`, envia o email padrao e regista autor,
instante, razao e envio.

### RF-012 — Encaminhamento

`POST /museum-questions/{id}/forward` e valido a partir de `SUBMITTED` ou
`IN_PROGRESS`. O alvo tem de pertencer a `CURATORIAL` ou
`COLLECTIONS_MANAGEMENT`. Regista o responsavel, notifica-o na aplicacao e muda
o estado para `IN_PROGRESS`.

### RF-013 — Encerramento

`PATCH /museum-questions/{id}/close` so e valido a partir de `ANSWERED` ou
`OUT_OF_SCOPE`. Regista autor e instante e **nao envia email**.

### RF-014 — Descarga de anexos

`GET /museum-questions/{questionId}/attachments/{attachmentId}` e exclusivo do
staff, verifica que o anexo pertence a pergunta, devolve o `Content-Type` de
confianca, `Content-Disposition: inline` e `X-Content-Type-Options: nosniff`.

### RF-015 — Resumo para painel *(especificado, nao implementado)*

O contrato 14 documenta `GET /museum-questions/summary`, devolvendo contagens
por estado. **Nao existe no codigo**: nao ha rota, caso de uso nem teste.

Alem de ausente, a rota colide com `GET /museum-questions/{questionId}` tal como
esta declarada — `summary` seria interpretado como identificador. Implementa-la
exige declara-la antes da rota parametrizada.

Nao existe criterio de aceitacao para este requisito enquanto a lacuna nao for
fechada.

### RF-016 — Prazo de resposta e alerta de atraso

Cada pergunta recebe prazo de 15 dias de calendario, persistido em
`responseDueAt`. Uma pergunta esta em atraso quando esta `SUBMITTED` ou
`IN_PROGRESS`, sem resposta, e o prazo ja passou.

```bash
uv run python -m app.museum_questions.presentation.commands notify-overdue --limit 100
```

O comando envia **uma** notificacao `MUSEUM_QUESTION_RESPONSE_OVERDUE` aos
gestores de colecoes quando a pergunta entra em atraso, e e idempotente por
pergunta atraves de `responseOverdueNotifiedAt`. Sem gestores para notificar, a
pergunta **nao** e marcada como notificada — o alerta fica devido em vez de se
perder.

### RF-017 — Email de resposta seguro na renderizacao

O email de resposta e enviado em multipart: uma versao de texto legivel e uma
versao HTML que preserva a marcacao permitida e remove a marcacao insegura.

### RF-018 — Efeitos externos so depois do commit

Resposta e marcacao fora de ambito nao enviam email se a transacao falhar.

---

## 7. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Uma pergunta nunca passa de `SUBMITTED` diretamente a `CLOSED` |
| INV-002 | Encaminhar deixa a pergunta em `IN_PROGRESS` e regista o responsavel |
| INV-003 | Encerrar nunca envia email |
| INV-004 | O email do requerente e pesquisado por hash, nunca em claro |
| INV-005 | Um alerta de atraso e enviado no maximo uma vez por pergunta |
| INV-006 | Nenhum email parte antes de a transacao ficar duravel |
| INV-007 | Um campo-armadilha preenchido nunca produz trabalho |
| INV-008 | Texto submetido e sempre escapado na renderizacao para o staff |

## 8. Criterios de aceitacao

### CA-001 — Submissao publica e recibo
→ `test_api.py::test_submit_returns_202_receipt`, `test_use_cases.py::test_execute_persists_submitted_question`

### CA-002 — Protecoes do canal aberto
→ `test_api.py::test_submit_captcha_failure_403`, `::test_submit_captcha_unavailable_503`, `::test_submit_rate_limited_429_with_retry_after`, `::test_submit_honeypot_returns_202_no_work`, `test_use_cases.py::test_honeypot_accepts_and_drops`, `::test_rate_limit_raises`, `::test_captcha_failure_raises`, `::test_captcha_unavailable_raises`

### CA-003 — Validacao e sanitizacao
→ `test_api.py::test_submit_missing_consent_is_rejected`, `::test_submit_sanitizes_control_characters_and_crlf`, `::test_submit_whitespace_only_fields_are_rejected`, `::test_submit_missing_field_is_rejected`, `::test_submit_invalid_email_is_rejected`, `::test_submit_over_length_message_is_rejected`

### CA-004 — Anexos de imagem verificados e limitados
→ `test_api.py::test_submit_accepts_multipart_images`, `::test_submit_rejects_more_than_ten_images`, `::test_submit_rejects_non_image_attachment`, `::test_uploaded_images_rejects_configurable_total_limit`, `test_use_cases.py::test_persist_uploads_images_and_tracks_attachment_metadata`, `::test_persist_discards_uploaded_files_when_repository_fails`

### CA-005 — Autorizacao do canal interno
→ `test_api.py::test_internal_questions_reject_non_staff`, `::test_internal_questions_reject_direction_initial_access`, `test_use_cases.py::test_list_questions_requires_staff`, `::test_list_questions_rejects_direction_initial_access`

### CA-006 — Fila, filtros e paginacao
→ `test_api.py::test_list_internal_questions_filters_and_paginates`, `::test_list_internal_questions_filters_by_requester_email`, `::test_list_questions_filters_by_assignee_and_hydrates_assignment`, `::test_list_questions_filters_unassigned_submitted`, `test_use_cases.py::test_list_questions_filters_and_orders`, `::test_list_questions_filters_by_requester_email`

### CA-007 — Transicoes e suas guardas
→ `test_domain.py::test_new_question_defaults_to_submitted_with_no_audit_fields`, `::test_answer_transitions_submitted_question`, `::test_close_rejects_submitted_question`, `test_use_cases.py::test_answer_question_marks_answered`, `::test_answer_question_rejects_finalized_question`, `::test_mark_out_of_scope_updates_status`, `::test_close_question_after_final_response`, `::test_close_submitted_question_is_rejected`

### CA-008 — Encaminhamento com alvo valido
→ `test_api.py::test_forward_internal_question_assigns_and_notifies_target`, `::test_forward_internal_question_rejects_invalid_target_group`, `::test_forward_internal_question_rejects_answered_question`, `test_use_cases.py::test_forward_question_assigns_submitted_question`, `::test_forward_question_rejects_finalized_question`

### CA-009 — Email so depois do commit
→ `test_api.py::test_answer_internal_question_sends_email_and_commits`, `::test_answer_internal_question_does_not_email_when_commit_fails`, `::test_mark_out_of_scope_does_not_email_when_commit_fails`, `::test_mark_out_of_scope_sends_standard_email`, `::test_submit_commit_failure_propagates`

### CA-010 — Prazo e alerta de atraso idempotente
→ `test_domain.py::test_submitted_question_is_overdue_after_response_due_at`, `::test_answered_question_is_not_overdue`, `test_use_cases.py::test_notify_overdue_questions_notifies_collection_managers_once`, `::test_notify_overdue_questions_without_managers_does_not_mark_notified`

### CA-011 — Email de resposta seguro
→ `test_email.py::test_answer_text_body_turns_allowed_html_into_readable_text`, `::test_answer_html_body_keeps_allowed_markup_and_drops_unsafe_markup`, `::test_smtp_answer_email_is_multipart_with_plain_and_html`

### CA-012 — Anexo servido em seguranca
→ `test_api.py::test_download_internal_question_attachment_returns_inline_image`, `::test_get_internal_question_detail_includes_attachments`

## 9. Requisitos nao funcionais

- **Confidencialidade**: nome, email e mensagem do requerente sao dados sensiveis; o email e cifrado com hash de pesquisa.
- **Duplicacao deliberada**: o adaptador de captcha e o limitador sao proprios deste contexto, e nao partilhados com `public_submission`, para nao criar acoplamento entre dois canais publicos com politicas que podem divergir.
- **XSS armazenado**: o texto submetido e escapado na renderizacao para o staff.

## 10. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Agregado e transicoes (RF-009..RF-013, RF-016) | `app/museum_questions/domain/models.py` |
| Casos de uso publicos e internos | `app/museum_questions/application/` |
| Captcha, limitador, email e anexos | `app/museum_questions/infrastructure/` |
| Endpoints e comando de atraso (RF-016) | `app/museum_questions/presentation/` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 11. Questoes em aberto

1. O prazo de 15 dias e uma promessa institucional ou apenas um limiar operacional? A distincao muda o que deve ser exposto ao cidadao.
2. Deve existir reencaminhamento em cadeia (A encaminha para B, B para C) com historico, ou a atribuicao unica e suficiente?
