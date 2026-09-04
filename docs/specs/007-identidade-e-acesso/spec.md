# SPEC-007 — Identidade, autenticacao e permissao de atuacao

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-007 |
| Estado | Implementado |
| Contexto delimitado | `app/identity` (linguagem publicada em `app/identity/public.py`) |
| Escrita a partir de | `domain/models.py`, `application/use_cases.py`, `app/shared/dependencies.py`, `test/identity/` |
| Specs relacionadas | Todas as restantes: nenhuma opera sem um ator autenticado |

## 1. Problema

O museu tem pessoal interno com papeis distintos e requerentes externos que
nunca pertenceram a instituicao. Um utilizador pode pertencer a mais do que um
grupo, e o que ele pode fazer depende do papel em que esta a atuar **naquele
pedido**, nao do conjunto de papeis que possui.

Deduzir o papel a partir do token seria escolher pelo utilizador — e escolheria
sempre o mais permissivo.

## 2. Objetivo

Autenticar utilizadores e estabelecer, em cada pedido, um **ator** = utilizador
autenticado + grupo em que esta a atuar, validando que a permissao invocada lhe
pertence de facto.

## 3. Linguagem ubiqua

- **Utilizador**: pessoa com credenciais. Estados `ACTIVE`, `DISABLED`.
- **Grupo**: papel institucional — `EXTERNAL`, `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION`, `SYS_ADMIN`.
- **Permissao**: ligacao entre um utilizador e um grupo. O seu identificador e o que o cliente envia para declarar em que papel atua.
- **Ator**: par (permissao, grupo) resolvido e validado num pedido concreto.
- **Instituicao**: entidade a que os grupos pertencem.
- **Requerente externo**: utilizador do grupo `EXTERNAL`, criado pelo sistema a partir de uma submissao publica.

---

## 4. Requisitos funcionais

### RF-001 — Login como unico estabelecimento de sessao

`POST /api/v1/auth/login` com email e password devolve `accessToken`, o
utilizador, as suas permissoes e a instituicao em que atua.

A lista de permissoes e **nao vazia**: um utilizador sem grupo nao entra, e a
recusa e indistinguivel de credenciais invalidas.

### RF-002 — Recusas de login indistinguiveis

Password errada, email desconhecido, utilizador desativado e utilizador sem
permissoes produzem todos `401` com a mesma mensagem. O sistema nao revela quais
emails existem.

### RF-003 — Pedido autenticado

Todos os restantes endpoints exigem dois cabecalhos:

```http
Authorization: Bearer <accessToken>
X-Permission-Id: <permissionId>
```

### RF-004 — Semantica estrita de `401` e `403`

| Situacao | Codigo |
| --- | --- |
| Cabecalho `Authorization` ausente ou malformado | `401` |
| Token invalido ou expirado | `401` |
| Utilizador desativado | `401` |
| Token emitido antes da ultima mudanca de password | `401` |
| `X-Permission-Id` ausente | `403` |
| Permissao desconhecida | `403` |
| Permissao que nao pertence ao utilizador autenticado | `403` |
| Grupo em atuacao sem autorizacao para a operacao | `403` |

`401` significa "quem es tu deixou de ser valido" e termina a sessao no cliente.
`403` significa "es quem dizes, mas nao neste papel".

### RF-005 — O grupo em atuacao nunca e inferido do token

O papel resulta exclusivamente de `X-Permission-Id`, sempre validado contra o
utilizador do token. Nenhum caso de uso deduz o grupo a partir do token.

### RF-006 — Invalidacao de sessoes por mudanca de password

Alterar ou repor a password atualiza `passwordChangedAt`. Tokens emitidos antes
desse instante sao rejeitados com `401`.

A comparacao trunca `passwordChangedAt` ao segundo, porque o `iat` do JWT so tem
resolucao de segundos: um login feito no mesmo segundo da alteracao — o que o
cliente e instruido a fazer logo apos uma reposicao — permanece valido.

### RF-007 — Politica unica de password

Uma unica politica governa criacao, alteracao, reposicao administrativa e
reposicao self-service: nao vazia, entre 5 e 128 caracteres. Nenhum fluxo pode
divergir para uma politica mais fraca.

### RF-008 — Alterar a propria password

Exige a password atual. Password atual errada e recusada; password nova fraca e
recusada. O sucesso devolve `204` e atualiza `passwordChangedAt`.

### RF-009 — Reposicao self-service sem enumeracao de contas

`POST /auth/password-reset` responde da mesma forma para email conhecido e
desconhecido. Para um email desconhecido, **nenhum token e criado**.

Um novo pedido invalida os tokens ainda por usar do mesmo utilizador.

### RF-010 — Token de reposicao de uso unico e curta duracao

O token e opaco; a base de dados guarda apenas o seu SHA-256. Expira em
`PASSWORD_RESET_TOKEN_TTL_MINUTES` (60 por omissao) e morre na confirmacao.

Token invalido, expirado ou ja usado produzem o **mesmo** erro opaco.

### RF-011 — Limitacao de frequencia

Pedido e confirmacao de reposicao estao sujeitos a limitacao de frequencia
propria.

### RF-012 — Segredos nunca em registos nem em representacoes

O token bruto so existe na ligacao enviada por email. O remetente nunca o
regista. A representacao de um requerente aprovisionado nunca expoe a password
temporaria. Passwords sao guardadas com bcrypt e nunca devolvidas.

### RF-013 — Aprovisionamento de requerente externo

O contexto expoe, pela linguagem publicada, a criacao de um utilizador
`EXTERNAL` a partir de um email e nome. Para o mesmo email, a permissao
existente e reutilizada em vez de duplicada. A password temporaria gerada
permite login.

### RF-014 — Administracao de utilizadores

Listar e ler utilizadores esta disponivel aos grupos internos. Criar
utilizadores e atribuir grupos e vedado ao grupo `EXTERNAL`.

Alterar o nome de exibicao altera **apenas** o nome.

### RF-015 — Protecao do ultimo administrador ativo

Desativar o ultimo `SYS_ADMIN` ativo, ou remove-lo do grupo, e recusado. O
sistema nao permite ficar sem administracao.

### RF-016 — Unicidade

Email de utilizador e unico, comparado sem sensibilidade a maiusculas. A mesma
permissao (utilizador + grupo) nao pode existir em duplicado.

### RF-017 — Instituicoes

CRUD de instituicoes restrito a `SYS_ADMIN`. Nome duplicado responde `409`.
Apagar uma instituicao com grupos associados responde `409`. A listagem e
paginada e a leitura de grupos inclui o identificador da instituicao.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | O grupo em atuacao e sempre validado contra o utilizador autenticado |
| INV-002 | `401` e exclusivo de falha de autenticacao; autorizacao e sempre `403` |
| INV-003 | Passwords existem apenas como hash bcrypt |
| INV-004 | Um token de reposicao serve uma unica vez |
| INV-005 | Nenhum segredo — password, token, JWT — entra em registos ou representacoes |
| INV-006 | Existe sempre pelo menos um `SYS_ADMIN` ativo |
| INV-007 | Uma sessao anterior a mudanca de password deixa de ser aceite |
| INV-008 | O sistema nunca revela se um email esta registado |

## 6. Criterios de aceitacao

### CA-001 — Autenticacao e as suas recusas
→ `test_auth.py::test_authenticate_success_returns_user_and_permissions`, `::test_authenticate_wrong_password_raises`, `::test_authenticate_unknown_email_raises`, `::test_authenticate_user_without_permissions_raises`, `::test_authenticate_disabled_user_raises`

### CA-002 — Login pela API e seus codigos
→ `test_auth.py::test_login_success_returns_token_user_and_flat_group`, `::test_login_wrong_password_is_401_with_message`, `::test_login_disabled_user_is_401_with_message`, `::test_login_unknown_email_is_401`, `::test_login_missing_password_is_422_with_errors`

### CA-003 — Fronteira `401` / `403` no ator
→ `test_auth.py::test_caller_missing_authorization_is_401`, `::test_caller_malformed_token_is_401`, `::test_caller_valid_token_missing_permission_header_is_403`, `::test_caller_unknown_permission_is_403`, `::test_caller_permission_not_owned_is_403`, `::test_caller_disabled_user_is_401`, `::test_caller_valid_and_owned_returns_actor`

### CA-004 — Sessoes antigas caem na mudanca de password
→ `test_auth.py::test_caller_token_issued_before_password_change_is_401`, `::test_caller_token_issued_after_password_change_is_valid`, `::test_caller_token_issued_same_second_as_change_is_valid`

### CA-005 — Politica de password em todos os fluxos
→ `test_auth.py::test_change_password_success_updates_hash_and_changed_at`, `::test_change_password_wrong_current_password_raises`, `::test_change_password_weak_new_password_raises`, `::test_change_password_api_wrong_current_is_400`, `::test_change_password_api_weak_new_password_is_400`, `::test_change_password_api_requires_authentication`

### CA-006 — Reposicao sem enumeracao e com erro opaco
→ `test_password_reset.py::test_request_reset_unknown_email_returns_none_and_creates_no_token`, `::test_confirm_reset_used_token_raises_opaque_error`, `::test_confirm_reset_expired_token_raises_opaque_error`, `::test_confirm_reset_unknown_token_raises_opaque_error`

### CA-007 — Token de uso unico, invalidacao do anterior e limite de frequencia
→ `test_password_reset.py::test_request_reset_known_email_creates_token_and_returns_raw_token`, `::test_request_reset_invalidates_previous_unused_token`, `::test_request_reset_respects_rate_limit`, `::test_confirm_reset_respects_rate_limit`, `test_password_reset_token_repository.py::test_save_marks_token_used`, `::test_invalidate_active_for_user_marks_only_that_users_unused_tokens`

### CA-008 — Segredos fora dos registos
→ `test_email.py::test_logging_sender_never_logs_the_raw_reset_token`, `test_provision_external_requester.py::test_provisioned_requester_repr_does_not_expose_temporary_password`

### CA-009 — Aprovisionamento idempotente de requerente externo
→ `test_provision_external_requester.py::test_provision_creates_user_and_external_permission_when_absent`, `::test_provision_reuses_existing_permission_for_same_email`, `::test_provisioned_temporary_password_allows_login`

### CA-010 — Ultimo administrador protegido
→ `test_auth.py::test_disable_last_active_sys_admin_is_rejected`

### CA-011 — Unicidade de email e de permissao
→ `test_identity_uniqueness.py::test_duplicate_email_is_rejected_case_insensitively`, `::test_duplicate_permission_is_rejected`

### CA-012 — Instituicoes restritas a `SYS_ADMIN`
→ `test_institutions_api.py::test_non_sysadmin_is_forbidden`, `::test_create_duplicate_name_returns_409`, `::test_delete_institution_with_groups_returns_409`, `::test_list_institutions_is_paginated`

### CA-013 — Autorizacao por grupo na administracao
→ `test_auth.py::test_external_user_cannot_create_identity_user`, `::test_external_user_cannot_assign_identity_group`, `::test_external_user_can_list_identity_users`, `::test_administration_user_can_list_identity_users`

## 7. Requisitos nao funcionais

- **Configuracao segura**: fora de local/test, `JWT_SECRET` nao pode ser o valor por omissao nem ter menos de 32 bytes; CORS nao pode ser aberto.
- **Duracao do token**: `ACCESS_TOKEN_TTL_MINUTES`, 12 horas por omissao.
- **Fronteira de contexto**: os restantes contextos usam identidade **apenas** por `app.identity.public`.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Modelo de dominio (RF-006, RF-010) | `app/identity/domain/models.py`, `domain/enums.py` |
| Politica de password (RF-007) | `app/identity/application/password_policy.py` |
| Casos de uso (RF-001, RF-008..RF-017) | `app/identity/application/use_cases.py` |
| Resolucao do ator (RF-003..RF-006) | `app/shared/dependencies.py` |
| Hash, tokens e limitacao (RF-010..RF-012) | `app/identity/infrastructure/{security,rate_limiter,email}.py` |
| Linguagem publicada (RF-013) | `app/identity/public.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 9. Questoes em aberto

1. A politica de password (minimo 5 caracteres) e adequada ao perfil de risco atual da instalacao?
2. Deve existir revogacao explicita de token (lista de revogacao) alem da invalidacao por mudanca de password?
3. O modelo multi-instituicao esta previsto no dominio mas nao exercitado: que regras mudam quando existir mais do que uma?
