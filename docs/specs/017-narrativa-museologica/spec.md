# SPEC-017 — Narrativa museologica assistida (KG-RAG)

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-017 |
| Estado | Implementado |
| Contexto delimitado | `app/ai/museum_narrative` |
| Escrita a partir de | `app/ai/museum_narrative/`, `test/ai/museum_narrative/`, contrato 09 |
| Specs relacionadas | [SPEC-013](../013-mapeamento-cidoc-crm/spec.md), [SPEC-016](../016-prompts-versionados/spec.md), [SPEC-015](../015-relatorio-visita-in-situ/spec.md) |

## 1. Problema

Um registo de visita in situ e uma estrutura de dados. Comunicar o que
aconteceu — a um curador, a um investigador, a um visitante, a uma crianca —
exige texto, e escrever esse texto a mao para cada publico e trabalho que nao
escala.

O risco de gerar esse texto com um modelo e conhecido: o modelo inventa datas,
pessoas, objetos e lugares que soam plausiveis.

## 2. Objetivo

Gerar narrativas a partir de um registo de visita, usando o grafo CIDOC-CRM
validado como **porta semantica**, factos canonicos como unica entrada do modelo,
e verificacoes deterministicas que assinalam invencoes para revisao humana.

## 3. Linguagem ubiqua

- **Factos canonicos**: representacao factual do registo, derivada do instantaneo, que o prompt recebe.
- **Porta semantica**: validacao do grafo (RDF + SHACL) que autoriza a geracao.
- **Tipo de narrativa**: estilo de reescrita (persona do modelo), **nao** propriedade da visita.
- **Instantaneo de factos (`facts_snapshot`)**: congelamento do que foi usado — factos, documento CIDOC compacto e relatorio de validacao.
- **Achado de validacao**: deteccao deterministica de conteudo nao suportado pelos factos.
- **Revisao editorial**: correcao manual do texto, registada em modo acrescento.

---

## 4. Requisitos funcionais

### RF-001 — Gerar narrativa a partir de um registo

`POST /api/v1/cidoc-mapping/in-situ-visit/{recordId}/narrative`, apenas staff.
Corpo opcional: `target_language` (omissao `pt`), `narrative_type` (omissao
`institutional`), `creativity_temperature` (omissao `0.3`, entre 0.0 e 1.0).

### RF-002 — Tipos de narrativa

| Valor | Publico | Tom |
| --- | --- | --- |
| `institutional` | Curadoria, direcao, portais de dados abertos | Formal, orientado a conformidade |
| `scientific` | Investigadores | Rigoroso, metodologico |
| `audioguide_adult` | Visitantes | Claro, pouco jargao |
| `audioguide_child` | Publico jovem | Narrativo, pedagogico |
| `social_media` | Comunidade digital | Conciso, com gancho e chamada a acao |

O tipo omitido resolve para `institutional` com origem `default`; fornecido, e
ecoado com origem `request_body`. Um tipo desconhecido responde `400` e **nada e
persistido**.

### RF-003 — O grafo e a porta, os factos sao a entrada

O grafo CIDOC-CRM validado e a **unica** porta semantica autorizada. O prompt do
modelo recebe apenas factos canonicos: nunca IRIs CIDOC, nunca JSON-LD expandido.

A separacao e deliberada: o grafo serve para verificar; texto tecnico dentro do
prompt so aumentaria a superficie de alucinacao.

### RF-004 — Falha da porta impede geracao

Falha de conformidade semantica responde `422`. Registo inexistente responde
`404`.

### RF-005 — Prompt vindo do registo de prompts publicados

O prompt de sistema e obtido do registo de prompts versionados
([SPEC-016](../016-prompts-versionados/spec.md)). Nao existe prompt embutido como
recurso de recurso: sem prompt publicado, a geracao falha com `503`.

Uma versao de prompt de outro tipo de narrativa e recusada.

### RF-006 — Metadados de geracao persistidos

Cada geracao guarda: tipo resolvido e origem da resolucao, lingua, temperatura,
modelo, identificador do instantaneo de factos, identificador e rotulo da versao
de prompt, *hash* da resposta do modelo, conformidade da validacao e achados.

### RF-007 — Instantaneo de factos congelado

E persistido o `facts_snapshot` exato usado para construir o prompt, incluindo o
documento CIDOC-CRM compacto e o relatorio de validacao SHACL que autorizou
aquela geracao naquele momento.

Uma narrativa existente **mantem** a sua versao de prompt depois de uma nova
publicacao: o passado nao e reescrito.

### RF-008 — Verificacoes deterministicas contra os factos

Depois da geracao, verificacoes deterministicas comparam o texto com os factos
canonicos e produzem achados com codigo, mensagem e evidencia. Codigos atuais
cobrem: datas inventadas, datas planeadas apresentadas como executadas, pessoas
inventadas, objetos inventados e lugares inventados.

Uma data **dentro** do intervalo planeado nao e assinalada.

Os achados marcam para revisao; nao bloqueiam a geracao.

### RF-009 — Ausencia declarada

O prompt recebe explicitamente a ausencia de informacao, em vez de a omitir: um
facto ausente declarado e menos convidativo a invencao do que um campo em falta.

### RF-010 — Historico de geracoes

Cada geracao e persistida. O mesmo registo pode ser recontado varias vezes, em
estilos, linguas e temperaturas diferentes, e todas as execucoes ficam guardadas,
listadas da mais recente para a mais antiga.

### RF-011 — Pre-visualizacao sem persistir

Existe pre-visualizacao que devolve metadados de rascunho **sem persistir**
narrativa. Aceita uma versao de prompt existente ou conteudo pontual — neste caso
com identificador de versao nulo. Combinacoes invalidas de origem de prompt sao
recusadas com `422` de forma estruturada.

### RF-012 — Correcao editorial em modo acrescento

`PATCH` corrige **apenas** o texto da narrativa. Os metadados de geracao
permanecem inalterados, e e criada uma revisao editorial que guarda o texto
anterior, o texto revisto, o editor e o instante.

O historico de revisoes lista da mais antiga para a mais recente, com o editor.
Texto vazio ou so com espacos e recusado com `422`.

### RF-013 — Isolamento por registo

Ler, corrigir ou listar revisoes de uma narrativa sob um registo que nao e o seu
responde `404`.

### RF-014 — Superficie HTTP

Todos os caminhos abaixo assentam em `/api/v1/cidoc-mapping/in-situ-visit`, sao
staff-only e respondem `404` quando a narrativa nao pertence ao registo indicado
(RF-013).

| Endpoint | Requisito |
| --- | --- |
| `POST /{recordId}/narrative` | RF-001 — gerar e persistir |
| `POST /{recordId}/narrative/preview` | RF-011 — pre-visualizar sem persistir |
| `GET /{recordId}/narratives` | RF-010 — historico paginado, mais recente primeiro (`page`, `size`, maximo 100) |
| `GET /{recordId}/narratives/{narrativeId}` | RF-010 — uma geracao guardada; `404` se desconhecida |
| `PATCH /{recordId}/narratives/{narrativeId}` | RF-012 — corrigir o texto e criar revisao |
| `GET /{recordId}/narratives/{narrativeId}/revisions` | RF-012 — revisoes paginadas, mais antiga primeiro |

A leitura devolve a narrativa tal como esta — texto corrigido incluido — com os
metadados de geracao originais intactos: quem le depois consegue distinguir o
que o modelo produziu do que uma pessoa corrigiu.

### RF-015 — Mapeamento de falhas do modelo

| Situacao | Codigo |
| --- | --- |
| Modelo indisponivel | `503` |
| Sem prompt publicado | `503` |
| Saida do modelo em branco | `503` |
| Tempo esgotado | `504` |
| Temperatura fora do intervalo | `422` |
| Chamador `EXTERNAL` | `403` |

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Nenhuma narrativa e gerada sem o grafo passar a porta semantica |
| INV-002 | O modelo nunca recebe IRIs CIDOC nem JSON-LD expandido |
| INV-003 | Toda a narrativa identifica a versao de prompt e o modelo que a produziram |
| INV-004 | O instantaneo de factos usado e congelado com a narrativa |
| INV-005 | Publicar um prompt novo nao altera narrativas ja geradas |
| INV-006 | Uma correcao manual nunca altera metadados de geracao |
| INV-007 | O historico editorial e acrescento puro |
| INV-008 | Achados de invencao marcam para revisao humana, nunca alteram o texto |
| INV-009 | Nao existe prompt embutido no codigo |

## 6. Criterios de aceitacao

### CA-001 — Tipo por omissao e tipo explicito
→ `test_api.py::test_default_type_returns_institutional`, `::test_explicit_type_echoed_in_meta`, `test_use_case.py::test_omitted_type_defaults_to_institutional_and_persists`, `::test_explicit_type_is_used_with_request_body_source`, `::test_unsupported_type_raises_and_persists_nothing`, `test_api.py::test_invalid_type_is_400`

### CA-002 — Porta semantica e suas falhas
→ `test_api.py::test_semantic_failure_is_422`, `::test_missing_record_is_404`, `test_use_case.py::test_fact_snapshot_freezes_cidoc_gate_output_used_for_generation`

### CA-003 — Prompt do registo publicado, sem recurso embutido
→ `test_use_case.py::test_generation_uses_published_prompt_registry_output`, `::test_missing_published_prompt_fails_without_hardcoded_fallback`, `::test_existing_narrative_keeps_prompt_version_after_new_publish`, `test_api.py::test_missing_published_prompt_is_503`, `test_prompt_acl.py::test_prompt_acl_rejects_version_from_another_narrative_type`

### CA-004 — Instantaneo de factos congelado e entrada canonica
→ `test_use_case.py::test_fact_snapshot_freezes_payload_used_for_generation`, `::test_user_prompt_receives_canonical_facts_and_declared_absence`

### CA-005 — Deteccao de invencoes
→ `test_use_case.py::test_narrative_with_invented_date_is_marked_for_review`, `::test_planned_date_as_execution_is_marked_for_review`, `::test_date_inside_planned_interval_is_allowed`, `::test_invented_person_object_and_place_are_marked_for_review`

### CA-006 — Persistencia e historico
→ `test_api.py::test_post_persists_and_returns_identifiers`, `::test_listed_newest_first_after_two_generations`, `::test_get_stored_narrative_by_id`, `::test_get_unknown_narrative_is_404`, `test_use_case.py::test_list_and_get_use_cases`, `::test_get_missing_narrative_raises`

### CA-007 — Pre-visualizacao sem persistir
→ `test_api.py::test_preview_returns_draft_metadata_without_persisting`, `::test_preview_accepts_ad_hoc_content_with_null_prompt_version_id`, `::test_preview_rejects_invalid_prompt_source_payloads_with_422_shape`, `::test_preview_rejects_prompt_version_for_another_narrative_type`, `test_use_case.py::test_preview_uses_prompt_version_without_persisting_narrative`, `::test_preview_uses_ad_hoc_content_without_persisting`, `::test_preview_rejects_invalid_prompt_source_combinations`

### CA-008 — Correcao editorial e revisoes
→ `test_api.py::test_patch_updates_narrative_text`, `::test_list_revisions_empty_for_never_edited_narrative`, `::test_list_revisions_returns_original_text_first_and_editor`, `::test_patch_empty_narrative_is_422`, `::test_patch_whitespace_narrative_is_422`, `test_use_case.py::test_update_narrative_edits_text_and_persists`, `::test_list_revisions_returns_chronological_editorial_history`, `test_repository.py::test_repository_lists_revisions_oldest_first_with_editor`

### CA-009 — Isolamento por registo
→ `test_api.py::test_get_under_wrong_record_is_404`, `::test_list_revisions_under_wrong_record_is_404`, `::test_patch_under_wrong_record_is_404`, `test_use_case.py::test_get_under_wrong_record_raises`, `::test_update_under_wrong_record_raises`

### CA-010 — Falhas do modelo com codigo proprio
→ `test_api.py::test_model_unavailable_is_503`, `::test_model_timeout_is_504`, `::test_blank_model_output_is_503`, `::test_temperature_above_one_is_422`, `test_model_ollama.py::test_identifies_ollama_response_error`, `::test_does_not_identify_other_response_error`

### CA-011 — Autorizacao staff-only
→ `test_api.py::test_external_caller_is_403`, `::test_list_forbidden_for_external`, `::test_patch_forbidden_for_external`, `::test_list_revisions_forbidden_for_external`

### CA-012 — Leitura do historico e de uma geracao
Dado duas geracoes sobre o mesmo registo
Quando o historico e lido, e depois uma delas pelo seu identificador
Entao a lista vem da mais recente para a mais antiga e a leitura devolve a geracao pedida; um identificador desconhecido responde `404`
→ `test_api.py::test_listed_newest_first_after_two_generations`, `::test_get_stored_narrative_by_id`, `::test_get_unknown_narrative_is_404`

### CA-013 — Correcao editorial cria revisao
Dado uma narrativa gerada
Quando o texto e corrigido por `PATCH`
Entao a narrativa passa a devolver o texto novo e as revisoes guardam o texto anterior, o revisto e o editor; texto vazio ou so com espacos responde `422`
→ `test_api.py::test_patch_updates_narrative_text`, `::test_list_revisions_returns_original_text_first_and_editor`, `::test_list_revisions_empty_for_never_edited_narrative`, `::test_patch_empty_narrative_is_422`, `::test_patch_whitespace_narrative_is_422`, `test_use_case.py::test_update_narrative_edits_text_and_persists`, `::test_list_revisions_empty_for_never_edited_narrative`

### CA-014 — Isolamento por registo em todas as leituras
Dado uma narrativa de um registo
Quando e lida, corrigida ou tem as revisoes listadas sob outro registo
Entao todas respondem `404`
→ `test_api.py::test_get_under_wrong_record_is_404`, `::test_list_revisions_under_wrong_record_is_404`, `::test_patch_under_wrong_record_is_404`, `::test_patch_unknown_narrative_is_404`, `test_use_case.py::test_get_missing_narrative_raises`, `::test_update_missing_narrative_raises`

## 7. Requisitos nao funcionais

- **Postura advisory**: a narrativa e material de trabalho sujeito a revisao humana; achados de validacao acompanham-na.
- **Modelo local**: geracao com Llama 3.1:8b via Ollama; latencia e disponibilidade sao do ambiente.
- **Fronteiras**: o contexto le o mapeamento por `app.cidoc_crm.public` e os prompts pela linguagem publicada.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Factos canonicos e verificacoes (RF-008, RF-009) | `app/ai/museum_narrative/application/` |
| Porta semantica (RF-003, RF-004) | `app/cidoc_crm/in_situ_visit_mapping/application/cidoc/reasoning.py` via `app.cidoc_crm.public` |
| Prompt publicado (RF-005) | `app/ai/museum_narrative/infrastructure/` (ACL de prompts) |
| Adaptador do modelo (RF-015) | `app/ai/museum_narrative/infrastructure/` (Ollama) |
| Endpoints de leitura e correcao (RF-014) | `app/ai/museum_narrative/presentation/routes.py` |
| Historico e revisoes (RF-010, RF-012) | `app/ai/museum_narrative/domain/`, `infrastructure/repositories.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 9. Questoes em aberto

1. Um achado de invencao deve poder bloquear a publicacao externa da narrativa, e quem decide isso?
2. O conjunto de verificacoes deterministicas cobre datas, pessoas, objetos e lugares: que outras categorias merecem verificacao (quantidades, instituicoes, tecnicas)?
