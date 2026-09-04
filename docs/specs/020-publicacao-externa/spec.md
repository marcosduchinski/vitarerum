# SPEC-020 — Publicacao externa de recursos

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-020 |
| Estado | Implementado |
| Contexto delimitado | `app/external_publications` |
| Escrita a partir de | `domain/models.py`, `application/use_cases.py`, `test/external_publications/` |
| Specs relacionadas | [SPEC-015](../015-relatorio-visita-in-situ/spec.md), [SPEC-013](../013-mapeamento-cidoc-crm/spec.md), [SPEC-009](../009-projeto-uso-de-colecoes/spec.md) |

## 1. Problema

Ha material do museu que faz sentido mostrar fora do sistema — um relatorio de
visita a um parceiro, um projeto a um portal de dados abertos. Fazer isso por
copia manual perde o controlo: ninguem sabe o que foi partilhado, com quem, ate
quando, nem consegue retirar o acesso.

## 2. Objetivo

Publicar um recurso interno para o exterior sob uma **concessao explicita e
revogavel**, com perfil de conteudo declarado, prazo opcional e registo de cada
acesso.

## 3. Linguagem ubiqua

- **Publicacao externa**: concessao de acesso a um recurso. Estados `PUBLISHED`, `REVOKED`.
- **Tipo de recurso**: `PROPOSAL`, `PROJECT`, `IN_SITU_VISIT_REPORT`.
- **Modo de acesso**: `TOKEN` (ligacao com segredo) ou `INTEGRATION_CLIENT` (cliente de integracao identificado).
- **Perfil**: `SUMMARY`, `DETAIL` ou `JSON_LD` — quanto e em que forma se mostra.
- **Acesso**: registo de cada tentativa, com desfecho `GRANTED` ou `DENIED`.

---

## 4. Requisitos funcionais

### RF-001 — Publicar um recurso

A publicacao exige tipo de recurso, identificador nao vazio, modo de acesso,
perfil e autor. Cria a concessao em `PUBLISHED`, com instante de publicacao e,
opcionalmente, prazo de validade.

### RF-002 — Requisitos por modo de acesso

| Modo | Exige |
| --- | --- |
| `TOKEN` | *hash* do token |
| `INTEGRATION_CLIENT` | identificador do cliente de integracao |

O token e guardado apenas como *hash*, e o valor bruto e produzido **uma unica
vez** no momento da publicacao.

### RF-003 — Perfil `JSON_LD` restrito

Servido em `GET /api/v1/external/publications/{token}/json-ld`.

O perfil `JSON_LD` so e valido para relatorios de visita in situ. Publicar
qualquer outro tipo de recurso com esse perfil e recusado.

A restricao existe porque so esse recurso possui uma projecao semantica
verificada ([SPEC-013](../013-mapeamento-cidoc-crm/spec.md)).

### RF-004 — Elegibilidade do recurso

Um recurso so e publicavel se existir e estiver num estado elegivel: propostas
`APPROVED`, projetos `IN_PROGRESS` ou `COMPLETED`. Um relatorio nao conforme e
recusado.

Recurso inexistente e recurso nao elegivel produzem erros distintos: o primeiro
e um engano de identificador, o segundo uma decisao de politica.

### RF-005 — Revogacao idempotente

Revogar marca a concessao como `REVOKED`, com autor e instante. Revogar de novo
nao altera nada.

### RF-006 — Verificacao de acessibilidade

Um acesso so e concedido se a concessao estiver `PUBLISHED` e dentro do prazo.
Concessao revogada e concessao expirada sao ambas inacessiveis.

Prazos ingenuos (sem fuso) sao normalizados antes da comparacao, para que a
verificacao nao dependa de como a data foi guardada.

### RF-007 — Semantica de nao encontrado para o exterior

Do lado publico, uma concessao revogada responde como inexistente. O exterior nao
distingue "nunca existiu" de "deixou de valer": distinguir seria informacao
gratuita para quem sonda.

### RF-008 — Registo de acessos

O historico le-se em
`GET /api/v1/external-publications/{publicationId}/accesses`.

Cada resolucao regista o acesso com o seu desfecho, incluindo os concedidos.

### RF-009 — Resposta por perfil

A resposta respeita o perfil declarado: o resumo omite os campos pesados. O
documento JSON-LD so e servido para relatorios de visita, apenas com perfil
compativel, e com o tipo de conteudo proprio de JSON-LD.

### RF-010 — Listagem de recursos publicaveis

`GET /api/v1/external-publications/publishable-resources`.

A listagem de recursos publicaveis delega por tipo no contexto proprietario,
atraves das interfaces publicadas.

### RF-011 — Autorizacao exclusiva de `SYS_ADMIN`

Gerir publicacoes externas e exclusivo de `SYS_ADMIN`. Outros grupos de staff nao
publicam nem revogam.

Partilhar material para fora da instituicao e um ato administrativo, nao
curatorial.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | O token existe em repouso apenas como *hash* |
| INV-002 | O token bruto e produzido uma unica vez |
| INV-003 | `JSON_LD` so se aplica a relatorios de visita in situ |
| INV-004 | Nenhum recurso nao elegivel e publicado |
| INV-005 | Uma concessao revogada nunca volta a conceder acesso |
| INV-006 | O exterior nao distingue revogado de inexistente |
| INV-007 | Todo o acesso resolvido fica registado |
| INV-008 | Apenas `SYS_ADMIN` gere publicacoes |

## 6. Criterios de aceitacao

### CA-001 — Token gerado e guardado como *hash* uma unica vez
→ `test_use_cases.py::test_create_external_publication_hashes_token_once`

### CA-002 — Elegibilidade do recurso
→ `test_use_cases.py::test_rejects_non_conformant_report_publication`, `::test_list_publishable_resources_delegates_by_type`

### CA-003 — Revogacao lida como inexistente pelo exterior
→ `test_use_cases.py::test_resolve_returns_404_semantics_for_revoked_publication`

### CA-004 — Expiracao e normalizacao de prazos
→ `test_use_cases.py::test_domain_blocks_expired_publication`, `::test_domain_normalizes_naive_expiration_before_access_check`

### CA-005 — Registo de acesso concedido
→ `test_use_cases.py::test_resolve_records_granted_access`

### CA-006 — JSON-LD apenas para relatorio e perfil compativel
→ `test_use_cases.py::test_json_ld_is_returned_for_report_detail_publication`, `::test_json_ld_rejects_summary_profile`, `test_api.py::test_json_ld_route_uses_json_ld_content_type`

### CA-007 — Resumo omite campos pesados
→ `test_api.py::test_public_summary_response_omits_heavy_fields`

### CA-008 — Autorizacao exclusiva de `SYS_ADMIN`
→ `test_api.py::test_sys_admin_can_list_external_publications`, `::test_staff_cannot_manage_external_publications`

## 7. Requisitos nao funcionais

- **Superficie externa**: os endpoints publicos nao expoem estado interno alem do perfil declarado.
- **Fronteiras**: os recursos sao lidos pelas linguagens publicadas dos contextos proprietarios.
- **Auditabilidade**: autor e instante de publicacao e de revogacao ficam registados.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Agregado, perfis e acessibilidade (RF-001..RF-006) | `app/external_publications/domain/models.py` |
| Casos de uso (RF-004, RF-007..RF-010) | `app/external_publications/application/use_cases.py` |
| Persistencia e leitores de recurso | `app/external_publications/infrastructure/` |
| Endpoints (RF-009, RF-011) | `app/external_publications/presentation/` |
| Fluxo | `docs/diagrams/external-publications-flow.svg` |

## 9. Questoes em aberto

1. Deve existir rotacao de token sem revogar a concessao?
2. O registo de acessos deve alimentar um relatorio de utilizacao por parceiro?
3. Que politica de retencao se aplica ao registo de acessos, dado que contem enderecos de origem?
