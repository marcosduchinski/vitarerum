# SPEC-016 — Prompts versionados para contextos assistidos por IA

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-016 |
| Estado | Implementado |
| Contexto delimitado | `app/ai/prompts` |
| Escrita a partir de | `app/ai/prompts/`, `test/ai/prompts/`, contrato 16 |
| Specs relacionadas | [SPEC-017](../017-narrativa-museologica/spec.md), [SPEC-005](../005-analise-agentica-de-candidato/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md) |

## 1. Problema

O comportamento de um sistema assistido por modelo de linguagem depende tanto do
prompt como do modelo. Se o prompt for uma constante no codigo, alterar o
comportamento exige um *deploy*, e uma saida gerada no passado deixa de ser
explicavel: ninguem sabe com que instrucao foi produzida.

## 2. Objetivo

Manter prompts como conteudo **versionado, publicavel e imutavel apos
publicacao**, para que qualquer saida de IA possa ser atribuida a versao exata
que a produziu.

## 3. Linguagem ubiqua

- **Modelo de prompt (`template`)**: identidade estavel de um prompt, por proposito e chave.
- **Proposito**: `in_situ_narrative`, `proposal_assistance`, `project_assistance`.
- **Versao**: conteudo concreto. Estados `draft`, `published`, `archived`.
- **Versao ativa**: a versao publicada em vigor para o modelo.

---

## 4. Requisitos funcionais

### RF-001 — Listar modelos e versoes

- `GET /api/v1/ai/prompts` com filtros opcionais por proposito e estado;
- `GET /api/v1/ai/prompts/{templateId}/versions`.

O estado de filtragem reflete o **estado atual** das versoes, nao o historico de
arquivamento.

### RF-002 — Ler uma versao exata

`GET /api/v1/ai/prompts/versions/{versionId}` devolve o conteudo imutavel dessa
versao. E o endpoint usado pelas vistas de auditoria para inspecionar o prompt
que produziu uma saida passada.

### RF-003 — Criar rascunho

`POST /api/v1/ai/prompts/{templateId}/versions` cria uma versao `draft` com
rotulo, conteudo, temperatura por omissao e, opcionalmente, a versao de origem a
copiar.

Copiar preserva o conteudo da origem. Conteudo em branco e rotulo em branco sao
recusados com erro de validacao — **sem** `500` e sem persistir nada.

### RF-004 — Publicar de forma atomica

`POST /api/v1/ai/prompts/versions/{versionId}/publish` executa numa unica
operacao: arquiva a versao publicada em vigor do mesmo modelo, publica o
rascunho e atualiza a versao ativa.

Conflito de estado ou publicacao concorrente respondem `409
PROMPT_PUBLICATION_CONFLICT`.

### RF-005 — Arquivar apenas versoes nao publicadas

`POST /api/v1/ai/prompts/versions/{versionId}/archive` arquiva versoes que nao
estejam publicadas. Arquivar isoladamente a versao publicada responde `409
PUBLISHED_PROMPT_REQUIRED`: uma versao publicada so sai de servico como parte da
publicacao da sua substituta.

O motivo e operacional: sem versao publicada, os contextos assistidos ficam sem
prompt e falham.

### RF-006 — Imutabilidade do conteudo publicado

O conteudo de uma versao nao muda depois de publicado. Republicar uma nova versao
**nao** altera o que a versao anterior diz — uma narrativa gerada no passado
continua a apontar para o texto exato que a produziu.

### RF-007 — Unicidade da versao publicada

Existe no maximo uma versao publicada por modelo. A restricao de unicidade e
delimitada ao estado: varias versoes arquivadas coexistem sem conflito.

### RF-008 — Ausencia de prompt e erro operacional

Pedir o prompt publicado de um proposito e chave inexistentes levanta erro
operacional. Nao existe conteudo de recurso embutido no codigo: um prompt em
falta e um problema de configuracao a resolver, nao a mascarar.

### RF-009 — Autorizacao

Todos os endpoints sao apenas para staff, com a mesma politica usada pela geracao
de narrativa. Utilizadores `EXTERNAL` nao leem, publicam nem arquivam.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | O conteudo de uma versao publicada nunca muda |
| INV-002 | Existe no maximo uma versao publicada por modelo |
| INV-003 | Publicar arquiva a anterior na mesma operacao |
| INV-004 | Nunca se remove a versao publicada sem substituta |
| INV-005 | Nao existe prompt embutido no codigo como recurso |
| INV-006 | Toda a saida de IA e atribuivel a uma versao concreta |

## 6. Criterios de aceitacao

### CA-001 — Publicacao atomica e versao ativa
→ `test_use_cases.py::test_publish_archives_current_version_and_updates_active_cache`

### CA-002 — Arquivamento isolado da versao publicada recusado
→ `test_use_cases.py::test_archive_rejects_isolated_archive_of_published_version`

### CA-003 — Copia preserva o conteudo de origem
→ `test_use_cases.py::test_copy_as_new_draft_preserves_source_content`

### CA-004 — Prompt em falta e erro operacional
→ `test_use_cases.py::test_get_published_prompt_raises_operational_error_when_missing`

### CA-005 — Resolucao por proposito e chave; unicidade por estado
→ `test_repository.py::test_repository_resolves_published_prompt_by_purpose_and_key`, `::test_published_version_uniqueness_is_scoped_to_status`

### CA-006 — Filtros refletem o estado atual
→ `test_repository.py::test_list_templates_filters_by_draft_status`, `::test_list_templates_status_uses_current_state_not_archived_history`

### CA-007 — Conteudo congelado apos republicacao
→ `test_api.py::test_prompt_version_endpoint_returns_frozen_content_after_republish`

### CA-008 — Validacao de rascunho sem `500` e sem persistir
→ `test_api.py::test_create_draft_rejects_blank_content_without_500`, `::test_create_draft_rejects_blank_version_label_without_persisting`

### CA-009 — Autorizacao staff-only
→ `test_api.py::test_staff_can_list_ai_prompt_templates`, `::test_external_user_cannot_read_publish_or_archive_ai_prompts`

## 7. Requisitos nao funcionais

- **Auditabilidade**: cada saida assistida guarda identificador e rotulo da versao usada ([SPEC-005](../005-analise-agentica-de-candidato/spec.md), RF-001; [SPEC-017](../017-narrativa-museologica/spec.md), RF-006).
- **Operacao sem deploy**: alterar comportamento de IA e um ato de publicacao, nao de instalacao.
- **Fronteiras**: contextos consumidores acedem por linguagem publicada, nunca as tabelas deste contexto.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Modelo, versoes e estados | `app/ai/prompts/domain/` |
| Publicacao e arquivamento (RF-003..RF-005) | `app/ai/prompts/application/` |
| Unicidade e resolucao (RF-007, RF-008) | `app/ai/prompts/infrastructure/` |
| Endpoints | `app/ai/prompts/presentation/` |
| Adaptadores consumidores | `app/scientific_return/infrastructure/prompt_acl.py`, `app/ai/museum_narrative/` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |
| Ciclo de vida | `docs/diagrams/ai-prompts-life-cycle.svg` |

## 9. Questoes em aberto

1. A autorizacao e hoje "staff"; deve a publicacao de prompts exigir um grupo mais restrito, dado que altera o comportamento do sistema em producao?
2. Deve existir avaliacao obrigatoria de um rascunho antes de poder ser publicado?
