# SPEC-010 — Submissao publica de propostas e canal de emenda

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-010 |
| Estado | Implementado |
| Contexto delimitado | `app/public_submission` |
| Escrita a partir de | `app/public_submission/`, `test/public_submission/`, contrato 11 |
| Specs relacionadas | [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-007](../007-identidade-e-acesso/spec.md), [SPEC-019](../019-numeros-de-referencia/spec.md) |
| Decisao de arquitetura | `docs/architecture/adr/0001-submission-channel.md` |

## 1. Problema

Um cidadao sem conta institucional tem de conseguir pedir acesso as colecoes.
Abrir um endpoint publico que escreve na fila de trabalho do staff expoe a
instituicao a spam, a submissoes em nome de terceiros e a carregamento de
ficheiros hostis.

## 2. Objetivo

Aceitar submissoes da internet aberta sem autenticacao, materializando uma
proposta na fila do staff **apenas** depois de o titular do email confirmar que
foi ele quem submeteu.

## 3. Modelo de confianca

Todos os campos sao entrada nao confiavel. A validacao do cliente, o token
Turnstile e o campo-armadilha sao **dissuasores**; a protecao real e do lado do
servidor.

| Protecao | Onde |
| --- | --- |
| Verificacao do token Turnstile no servidor | submissao |
| Limitacao de frequencia por IP, por email e global | submissao e confirmacao |
| Validacao, limites de comprimento e recusa de CR/LF em campos que entram em email | ambos |
| Duplo opt-in com token assinado, de uso unico e com prazo | ambos |
| Campo-armadilha (*honeypot*) | submissao |
| Ficheiros limitados, verificados por assinatura e guardados fora de qualquer raiz web | submissao |

---

## 4. Requisitos funcionais

### RF-001 — Submissao publica

`POST /api/v1/public/proposals` (`multipart/form-data`), sem autenticacao.

| Campo | Obrigatorio | Restricao |
| --- | --- | --- |
| `citizenName` | sim | 1–120 caracteres |
| `citizenEmail` | sim | ate 180 caracteres; recebe a ligacao de confirmacao |
| `subject` | sim | 1–160 caracteres |
| `body` | sim | 1–4000 caracteres |
| `useType` | sim | `EXHIBITION`, `IN_SITU_VISIT` ou `OTHER` |
| `proposedBeginDate` / `proposedEndDate` | sim | ISO 8601; semeiam as datas da proposta |
| `consent` | sim | tem de ser `true` (RGPD) |
| `captchaToken` | sim | verificado no servidor |
| `website` | nao | campo-armadilha |
| `documents` | sim | 1 a 5 ficheiros, PDF/JPG/PNG/DOCX, ate 10 MB cada |

Resposta `202` com recibo `PENDING_CONFIRMATION`. **Nenhuma proposta e visivel
ao staff nesta fase.**

### RF-002 — Codigos de recusa

| Situacao | Codigo |
| --- | --- |
| Validacao falhada, consentimento ausente, documentos ausentes ou acima de 5 | `422` |
| Turnstile invalido, ausente ou expirado | `403` |
| Ficheiro acima de 10 MB | `413` |
| Tipo de ficheiro nao suportado | `415` |
| Limite de frequencia excedido | `429` com `Retry-After` |
| Fornecedor de captcha inacessivel | `503` |

### RF-003 — Campo-armadilha silencioso

`website` preenchido produz `202` **sem trabalho nenhum**: sem validacao de
documentos, sem persistencia, sem email.

O campo nao e rejeitado por esquema, e aceita ate 255 caracteres. Rejeita-lo com
`422` revelaria ao bot que o campo esta a ser observado.

### RF-004 — Ordem das verificacoes baratas

Limitacao de frequencia e verificacao de captcha ocorrem **antes** de os
ficheiros carregados serem lidos. Um atacante nao consegue impor ao servidor o
custo de ler 50 MB antes de ser recusado.

### RF-005 — Duplo opt-in

A submissao cria um registo pendente e nao verificado, e envia para
`citizenEmail` uma ligacao com token assinado, de uso unico e com prazo.

`POST /api/v1/public/proposals/confirm` consome o token e materializa a proposta
na fila do staff, com canal `PUBLIC` e contacto do requerente preenchido.

### RF-006 — Resultados de confirmacao sem erro HTTP

Todos os desfechos respondem `200`, para a pagina publica poder mostrar uma
mensagem amigavel:

| `status` | Significado |
| --- | --- |
| `CONFIRMED` | Proposta criada, com numero de referencia |
| `ALREADY_CONFIRMED` | Ligacao ja usada; a proposta ja existe |
| `EXPIRED` | Token fora do prazo; e preciso resubmeter |
| `INVALID` | Token malformado ou desconhecido |

Codigos nao-2xx ficam reservados a falhas inesperadas e a `429`.

### RF-007 — Confirmacao idempotente

Reclicar uma ligacao ja usada devolve `ALREADY_CONFIRMED` e nao cria segunda
proposta. A leitura da submissao pendente e feita com bloqueio, para que duas
confirmacoes simultaneas nao materializem duas propostas.

### RF-008 — Expiracao que limpa atras de si

Confirmar uma ligacao expirada **recupera** os ficheiros carregados e apaga o
registo pendente. Um segundo clique passa a ler `INVALID`.

Dados pessoais de uma submissao nunca confirmada nao ficam a acumular.

### RF-009 — Conflito de numero de referencia

A atribuicao do numero de referencia da proposta tolera colisao concorrente,
repetindo a geracao em vez de falhar a confirmacao.

### RF-010 — Efeitos externos so depois do commit

O email de confirmacao so parte se a transacao ficar duravel. Se a persistencia
falhar depois de ficheiros escritos, os ficheiros sao removidos.

### RF-011 — Notificacao unica ao staff

A confirmacao notifica o staff uma unica vez, mesmo quando ha varios
destinatarios potenciais para o mesmo utilizador.

### RF-012 — Canal publico de emenda de documentos

Quando o staff pede correcoes sem rejeitar
([SPEC-008](../008-proposta-uso-de-colecoes/spec.md), RF-010), o requerente
recebe uma ligacao delimitada, de uso unico e com prazo:

| Endpoint | Proposito |
| --- | --- |
| `GET /public/proposals/amendments/{token}` | Hidrata o ecra: referencia, estado, itens de correcao no ambito e documentos atuais |
| `POST /public/proposals/amendments/{token}/documents` | Carrega substituicao ou documento em falta |
| `DELETE /public/proposals/amendments/{token}/documents/{documentId}` | Remove documento errado e recupera o ficheiro |
| `POST /public/proposals/amendments/{token}/submit` | Finaliza, resolve os itens, notifica o staff e **queima o token** |

Regras: o `documentType` volta exatamente como recebido; fora do ambito responde
`403`; vazio ou acima de 128 caracteres responde `422`; as regras de tipo e
tamanho de ficheiro sao as da entrada.

### RF-013 — Falhas opacas no canal de emenda

Token invalido, expirado ou ja usado respondem todos `404
AMENDMENT_UNAVAILABLE`, sem distincao — sondar nao revela nada. Uma proposta que
deixou de estar `PENDING` responde `409 PROPOSAL_NOT_PENDING`.

### RF-014 — Token em repouso

Apenas o SHA-256 do token e guardado; o valor bruto vive somente na ligacao
enviada por email. Os endpoints de emenda tem limitacao de frequencia por IP,
como os de entrada.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Nenhuma proposta chega ao staff sem confirmacao do titular do email |
| INV-002 | Uma submissao pendente exige pelo menos um documento |
| INV-003 | Um token de confirmacao serve uma unica vez |
| INV-004 | Uma submissao confirmada nunca expira |
| INV-005 | Uma submissao expirada nao deixa ficheiros nem registo |
| INV-006 | Um campo-armadilha preenchido nunca produz trabalho |
| INV-007 | Nenhum email parte antes de a transacao ficar duravel |
| INV-008 | Apenas o hash do token existe em repouso |
| INV-009 | O canal publico nunca aceita nem depende de credenciais |

## 6. Criterios de aceitacao

### CA-001 — Submissao valida devolve recibo e guarda datas propostas
→ `test_api.py::test_submit_returns_202_receipt`, `::test_submit_persists_proposed_dates`, `::test_submit_missing_proposed_dates_is_rejected`

### CA-002 — Campo-armadilha silencioso
→ `test_api.py::test_submit_honeypot_returns_202_no_work`, `::test_submit_honeypot_skips_document_validation`, `test_use_cases.py::test_honeypot_accepts_and_drops`

### CA-003 — Captcha e limite antes de ler ficheiros
→ `test_api.py::test_submit_captcha_failure_403`, `::test_submit_rate_limited_429_with_retry_after`, `::test_submit_rate_limited_before_reading_uploads`, `::test_submit_captcha_checked_before_reading_uploads`, `test_use_cases.py::test_captcha_failure_raises`, `::test_captcha_unavailable_raises`, `::test_rate_limited_raises`

### CA-004 — Validacao de conteudo e de ficheiros
→ `test_api.py::test_submit_missing_consent_is_rejected`, `::test_submit_invalid_use_type_is_rejected`, `::test_submit_missing_documents_is_rejected`, `::test_submit_too_many_documents_is_rejected`, `::test_submit_oversized_document_is_rejected`, `::test_submit_unsupported_document_is_rejected`, `test_domain.py::test_pending_submission_requires_at_least_one_document`

### CA-005 — Fluxo completo de duplo opt-in
→ `test_api.py::test_submit_then_confirm_flow`, `test_use_cases.py::test_happy_path_stores_pending_and_returns_token`, `::test_confirm_materialises_proposal`

### CA-006 — Idempotencia e concorrencia da confirmacao
→ `test_use_cases.py::test_confirm_twice_is_already_confirmed`, `::test_confirm_uses_locking_read`, `::test_confirm_retries_reference_number_conflict`, `test_domain.py::test_confirm_twice_raises`, `::test_confirm_sets_status_and_reference`

### CA-007 — Token desconhecido e expirado
→ `test_api.py::test_confirm_unknown_token_returns_200_invalid`, `test_use_cases.py::test_confirm_unknown_token_is_invalid`, `::test_confirm_expired_token_reclaims_files_and_row`, `test_domain.py::test_is_expired_true_after_ttl`, `::test_is_expired_false_within_ttl`, `::test_confirmed_submission_never_expires`

### CA-008 — Nenhum efeito externo sem commit
→ `test_api.py::test_submit_does_not_email_when_commit_fails`, `test_use_cases.py::test_submit_deletes_saved_files_when_persistence_fails`

### CA-009 — Notificacao unica ao staff
→ `test_api.py::test_confirm_public_proposal_notifies_staff_once`

### CA-010 — Token de emenda de uso unico e com prazo
→ `test_domain.py::test_amendment_token_is_active_when_fresh`, `::test_amendment_token_expires_after_ttl`, `::test_amendment_token_mark_used_is_single_use`, `::test_amendment_token_used_is_not_expired`, `test_api.py::test_submit_amendment_notifies_assigned_staff`

## 7. Requisitos nao funcionais

- **CORS**: restrito a origem publica; os endpoints nao aceitam cookies nem credenciais.
- **Armazenamento**: ficheiros fora de qualquer raiz web, sob `DATA_DIR`; analise antivirus e uma preocupacao de instalacao.
- **Borda**: WAF e gestao de bots ficam a frente da aplicacao; nao substituem as verificacoes do servidor.
- **RGPD**: consentimento explicito obrigatorio; submissoes nao confirmadas sao descartadas com os seus ficheiros.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Submissao pendente e tokens (RF-005..RF-008, RF-014) | `app/public_submission/domain/` |
| Casos de uso de submissao e confirmacao | `app/public_submission/application/` |
| Captcha, limitacao e email | `app/public_submission/infrastructure/` |
| Endpoints publicos | `app/public_submission/presentation/` |
| Canal de emenda (RF-012, RF-013) | `app/use_of_collections/infrastructure/amendment_invitation.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |
| Decisao de canal | `docs/architecture/adr/0001-submission-channel.md` |

## 9. Questoes em aberto

1. Qual o prazo adequado do token de confirmacao face ao comportamento real dos requerentes (atualmente 24 horas)?
2. Deve existir reenvio da ligacao de confirmacao, e como evitar que se torne um vetor de envio de email em massa?
