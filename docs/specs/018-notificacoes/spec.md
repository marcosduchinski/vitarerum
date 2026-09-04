# SPEC-018 — Notificacoes na aplicacao

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-018 |
| Estado | Implementado |
| Contexto delimitado | `app/notifications` |
| Escrita a partir de | `app/notifications/`, `test/notifications/` |
| Specs relacionadas | [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-011](../011-perguntas-ao-museu/spec.md), [SPEC-002](../002-vigilancia-retorno-cientifico/spec.md) |

## 1. Problema

O trabalho do museu e assincrono: uma proposta chega, um documento e entregue,
uma pergunta fica em atraso, uma vigilancia encontra candidatos. Sem um canal
interno, cada membro do staff teria de descobrir por si o que mudou.

## 2. Objetivo

Manter notificacoes internas dirigidas a uma **permissao** — nao a um
utilizador — para que quem trabalha em varios papeis veja apenas o que diz
respeito ao papel em que esta a atuar.

## 3. Linguagem ubiqua

- **Notificacao**: item dirigido a uma permissao, com tipo, recurso relacionado e estado de leitura.
- **Tipo (`NotificationKind`)**: `PROPOSAL_SUBMITTED`, `PROPOSAL_ASSIGNED`, `PROPOSAL_FORWARDED`, `PROPOSAL_TAKEN_OVER`, `PROPOSAL_DOCUMENTS_SUBMITTED`, `PROPOSAL_CORRECTIONS_SUBMITTED`, `MUSEUM_QUESTION_SUBMITTED`, `MUSEUM_QUESTION_FORWARDED`, `MUSEUM_QUESTION_RESPONSE_OVERDUE`, `SCIENTIFIC_RETURN_CANDIDATES_FOUND`.
- **Recurso relacionado**: `PROPOSAL`, `PROJECT` ou `MUSEUM_QUESTION`.
- **Limpar**: ocultar as notificacoes da permissao ativa sem as apagar do registo.

---

## 4. Requisitos funcionais

### RF-001 — Criacao dirigida a permissao

Uma notificacao nasce por nao lida, dirigida a uma permissao concreta, com tipo,
recurso relacionado e autor do ato que a originou.

Enderecar a permissao — e nao ao utilizador — e o que torna o painel coerente
com o modelo de atuacao por papel
([SPEC-007](../007-identidade-e-acesso/spec.md), RF-005).

### RF-002 — Difusao com deduplicacao de destinatarios

Ao notificar varios destinatarios, a mesma permissao nunca recebe duas
notificacoes do mesmo ato.

### RF-003 — O autor do ato nao e notificado do proprio ato

Atribuir ou encaminhar a si proprio nao gera notificacao nem email
([SPEC-008](../008-proposta-uso-de-colecoes/spec.md), RF-007).

### RF-004 — Listagem com autor resolvido

A listagem resolve o autor de cada notificacao sem repetir a resolucao para o
mesmo autor.

### RF-005 — Marcar como lida

Marcar como lida e **idempotente** e limitado ao destinatario: uma permissao nao
marca as notificacoes de outra.

### RF-006 — Marcar todas como lidas

`POST /api/v1/notifications/read-all`, limitado a permissao ativa.

### RF-007 — Limpar todas

`POST /api/v1/notifications/clear-all` oculta as notificacoes da permissao ativa e zera a contagem de nao lidas, sem
afetar outras permissoes.

### RF-008 — Contagem e filtros

Os endpoints permitem listar e filtrar (`GET /api/v1/notifications`), contar
nao lidas (`GET /api/v1/notifications/unread-count`) e marcar como lida
(`POST /api/v1/notifications/{notificationId}/read`).

### RF-009 — Isolamento

Os endpoints recusam operar sobre notificacoes de outro destinatario e recusam
chamadores `EXTERNAL`.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Uma notificacao pertence a uma permissao, nunca a um utilizador |
| INV-002 | Um ato nunca produz duas notificacoes para a mesma permissao |
| INV-003 | Ninguem e notificado do seu proprio ato |
| INV-004 | Marcar como lida e idempotente |
| INV-005 | Nenhuma operacao alcanca notificacoes de outro destinatario |
| INV-006 | Limpar oculta, nao apaga |

## 6. Criterios de aceitacao

### CA-001 — Criacao por nao lida
→ `test_use_cases.py::test_create_notification_persists_unread_item`

### CA-002 — Deduplicacao de destinatarios
→ `test_use_cases.py::test_create_notification_many_dedupes_recipients`, `::test_list_notifications_dedupes_triggered_by_resolution`

### CA-003 — Marcacao idempotente e delimitada
→ `test_use_cases.py::test_mark_read_is_idempotent_and_scoped_to_recipient`, `::test_mark_all_read_scopes_to_active_permission`

### CA-004 — Limpar delimitado a permissao ativa
→ `test_use_cases.py::test_clear_all_hides_notifications_and_scopes_to_active_permission`, `test_repository_and_api.py::test_repo_clear_all_hides_active_permission`, `::test_notifications_routes_clear_all_hides_list_and_clears_unread`

### CA-005 — Persistencia e rotas
→ `test_repository_and_api.py::test_sqlalchemy_notification_repository_round_trip_and_mark_all_read`, `::test_notifications_routes_list_filter_count_and_mark_read`

### CA-006 — Isolamento entre destinatarios e recusa de externos
→ `test_repository_and_api.py::test_notification_routes_reject_other_recipient_and_external_callers`

## 7. Requisitos nao funcionais

- **Acoplamento**: os contextos emissores usam a linguagem publicada de notificacoes; nao escrevem nas suas tabelas.
- **Efeitos externos**: quando a notificacao acompanha email, o envio ocorre apos o commit.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Modelo e tipos | `app/notifications/domain/` |
| Casos de uso (RF-001..RF-008) | `app/notifications/application/` |
| Persistencia | `app/notifications/infrastructure/` |
| Endpoints | `app/notifications/presentation/` |
| Linguagem publicada | `app/notifications/public.py` |
| Fluxo | `docs/diagrams/notifications-flow.svg` |

## 9. Questoes em aberto

1. Deve existir preferencia por utilizador sobre que tipos geram email alem da notificacao interna?
2. As notificacoes ocultadas devem ter politica de retencao propria?
