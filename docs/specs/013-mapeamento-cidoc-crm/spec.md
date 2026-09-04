# SPEC-013 — Mapeamento CIDOC-CRM de visitas in situ

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-013 |
| Estado | Implementado |
| Contexto delimitado | `app/cidoc_crm/in_situ_visit_mapping` |
| Escrita a partir de | `domain/models.py`, `application/cidoc/`, `test/cidoc_crm/`, contrato 08 |
| Specs relacionadas | [SPEC-009](../009-projeto-uso-de-colecoes/spec.md), [SPEC-015](../015-relatorio-visita-in-situ/spec.md) |

## 1. Problema

O registo interno de uma visita in situ e util para o museu, mas ininteligivel
para o exterior. Para que a informacao possa ser partilhada, agregada ou
publicada como dados do patrimonio, tem de ser expressa num modelo comum — o
CIDOC-CRM.

O risco de um mapeamento e afirmar mais do que se sabe: transformar uma data
planeada numa data de evento, ou um objeto de tipo desconhecido numa especime
biologica, produz dados formalmente validos e factualmente falsos.

## 2. Objetivo

Guardar registos de mapeamento de visitas in situ como **instantaneos** e
projeta-los em JSON-LD conforme ao CIDOC-CRM 7.1.3, afirmando apenas o que a
evidencia suporta.

## 3. Linguagem ubiqua

- **Registo de visita (`InSituVisitRecord`)**: raiz do agregado; instantaneo de uma visita executada.
- **Filhos**: `requestedObjects`, `inSituOccurrences`, `inSituLogs`, `inSituPublications`; os tres ultimos possuem anexos.
- **Evidencia de execucao**: prova de que a visita ocorreu — tipo, instante e autor do registo.
- **Lacunas de evidencia**: o que faltou para afirmar a execucao com plenitude.
- **Projecao**: documento JSON-LD gerado a partir do registo segundo as regras de mapeamento.

---

## 4. Requisitos funcionais

### RF-001 — Criacao do registo com o grafo completo

`POST /api/v1/cidoc-mapping/in-situ-visit` persiste o registo e todos os filhos
numa unica chamada e responde `201`. Todo o grafo e uma unica fronteira de
consistencia: cria-se junto e le-se inteiro.

Campos obrigatorios: `code`, `visitBeginDate`, `visitEndDate`, `visitorName`,
`placeName`. As colecoes de filhos sao opcionais e assumem lista vazia.

### RF-002 — Identificadores e instantes atribuidos pelo servidor

O identificador do agregado, os identificadores de todos os filhos e anexos, e
`generatedAt` sao atribuidos pelo servidor. O cliente **nunca** os fornece: um
instantaneo cuja identidade venha de fora nao e um instantaneo.

### RF-003 — Ordenacao explicita

Cada filho e cada anexo carrega `sourceId` e `position`. A ordem e dado, nao
consequencia da ordem de insercao.

### RF-004 — Exportacao a partir de um projeto

`POST /collection-use-projects/{id}/export-in-situ-visit-record` traduz um
projeto de uso de colecoes num registo de mapeamento
([SPEC-009](../009-projeto-uso-de-colecoes/spec.md), RF-017).

Recusas:

| Situacao | Codigo |
| --- | --- |
| Projeto inexistente | `404` |
| Tipo de uso diferente de `IN_SITU_VISIT` | `409` |
| Projeto sem evidencia de execucao | `409` |
| Chamador `EXTERNAL` | `403` |

### RF-005 — Evidencia de execucao como pre-condicao

So um projeto `COMPLETED` com evento de conclusao constitui evidencia de visita
executada. Um projeto planeado, ou em curso, **nao** e uma visita.

### RF-006 — Datas planeadas nunca viram intervalo do evento

As datas planeadas sao guardadas como tal e nao sao afirmadas como o intervalo
temporal da visita. O intervalo do evento deriva da evidencia de execucao.

Sem evidencia, o mapeamento **omite** o intervalo em vez de o inventar.

### RF-007 — Tipagem conservadora dos objetos

Os objetos pretendidos sao tipados genericamente (`crm:E19_Physical_Object`) e
nao como objetos biologicos. Afirmar `crm:E20_Biological_Object` exigiria saber
que o objeto e um especime, o que o registo nao garante.

### RF-008 — Alvo e contexto do vocabulario

A projecao tem por alvo o CIDOC-CRM 7.1.3. O contexto JSON-LD e **incorporado**
no documento: o contexto oficial 7.1.3 mais os prefixos locais. O documento nao
depende de a rede resolver um contexto remoto no momento da leitura.

### RF-009 — Autoria do grafo vem do registo

O criador do grafo e a instituicao registada no proprio registo, nao um valor
fixo das regras de mapeamento. Sem instituicao no registo, a afirmacao de autoria
e **omitida**.

### RF-010 — Ligacao ao objeto relacionado

Ocorrencias, entradas de diario, publicacoes e respetivos anexos ligam-se ao
objeto que documentam sempre que essa relacao existe no registo. A traducao do
identificador de objeto de origem para o identificador relacionado e feita por
uma camada anti-corrupcao.

### RF-011 — Anexos como documentos

Cada anexo transporta o seu localizador de conteudo e a sua descricao como nota.

### RF-012 — Contexto de atividade dos diarios

Quem acrescentou uma entrada de diario e quando sao modelados como contexto de
atividade, nao como propriedades soltas do objeto.

### RF-013 — Leitura da projecao com validacao por omissao

`GET` da projecao CIDOC de um registo valida por omissao contra as *shapes* SHACL
e responde `422` quando a validacao falha. A validacao pode ser explicitamente
dispensada pelo chamador.

Validar por omissao e a escolha certa quando o produto e um documento destinado
a ser consumido por terceiros: sair silenciosamente com um grafo invalido custa
mais do que falhar cedo.

### RF-014 — Validacao sem materializar o grafo expandido

A verificacao de conformidade reporta o resultado sem devolver nem materializar
o grafo expandido.

### RF-015 — Autorizacao

Todos os endpoints deste contexto sao acoes de staff: `CURATORIAL`,
`COLLECTIONS_MANAGEMENT`, `DIRECTION` e `SYS_ADMIN`. Chamadores `EXTERNAL`
recebem `403`.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | O registo e um instantaneo: identidade e instante sao do servidor |
| INV-002 | O grafo do registo e criado e lido como um todo |
| INV-003 | Nenhuma data planeada e afirmada como data de evento |
| INV-004 | Nenhum objeto e tipado alem do que a evidencia sustenta |
| INV-005 | O contexto do vocabulario e incorporado, nao referenciado remotamente |
| INV-006 | A autoria do grafo vem do registo ou e omitida |
| INV-007 | Uma visita so e mapeavel com evidencia de execucao |
| INV-008 | O contexto so acede a `use_of_collections` por camada anti-corrupcao |

## 6. Criterios de aceitacao

### CA-001 — Exportacao e suas recusas
→ `test_export_in_situ_visit_api.py::test_export_happy_path_returns_201_with_mapped_record`, `::test_export_forbidden_for_external`, `::test_export_project_not_found_404`, `::test_export_wrong_use_type_409`, `::test_export_without_execution_evidence_409`, `test_export_in_situ_visit_use_case.py::test_export_maps_project_into_record_and_persists`, `::test_export_rejects_non_in_situ_visit_use_type`, `::test_export_rejects_in_situ_visit_without_execution_evidence`

### CA-002 — Datas planeadas nao viram intervalo do evento
→ `test_cidoc_mapping.py::test_planned_dates_are_not_asserted_as_visit_timespan_without_evidence`, `::test_visit_timespan_uses_execution_evidence_not_planned_interval`

### CA-003 — Tipagem conservadora
→ `test_cidoc_mapping.py::test_requested_objects_are_typed_generically_not_as_biological_objects`

### CA-004 — Alvo 7.1.3 com contexto incorporado
→ `test_cidoc_mapping.py::test_targets_cidoc_713`, `::test_context_is_inlined_official_713_plus_local_prefixes`

### CA-005 — Autoria do grafo
→ `test_cidoc_mapping.py::test_graph_creator_comes_from_the_record_not_from_the_mapping_rules`, `::test_graph_creator_is_omitted_when_the_record_has_no_institution`

### CA-006 — Expansao completa e ligacoes
→ `test_cidoc_mapping.py::test_full_expansion_emits_a_node_per_child`, `::test_visit_links_to_actor_place_and_type`, `::test_occurrence_and_log_link_to_related_object_when_present`, `::test_publication_information_object_links_to_related_object_when_present`, `::test_attachments_link_to_related_object_when_parent_has_one`

### CA-007 — Anexos e contexto de atividade
→ `test_cidoc_mapping.py::test_attachments_carry_content_url`, `::test_attachments_carry_description_as_note`, `::test_access_log_added_at_and_added_by_are_modelled_as_activity_context`, `::test_enriched_snapshot_fields_shape_cidoc_labels_and_occurrence_context`

### CA-008 — Validacao SHACL por omissao
→ `test_cidoc_api.py::test_get_cidoc_crm_validates_by_default`, `::test_get_cidoc_crm_returns_422_when_default_validation_fails`, `::test_get_cidoc_crm_can_skip_validation_explicitly`, `test_jsonld_validation.py::test_document_is_valid_rdf_with_resolved_terms`, `::test_generated_graph_conforms_to_crm_shapes`, `::test_shapes_reject_a_domain_range_violation`, `::test_validate_cidoc_reports_conformance_without_returning_expanded_graph`, `::test_validate_cidoc_does_not_materialise_expanded_graph`

### CA-009 — Camada anti-corrupcao entre contextos
→ `test_context_acl.py::test_acl_translates_object_source_id_into_related_object_source_id`, `test_export_in_situ_visit_use_case.py::test_export_propagates_related_object_source_id`

### CA-010 — Persistencia integral do instantaneo
→ `test_in_situ_visit_repository.py::test_repository_round_trips_enriched_snapshot_fields`

## 7. Requisitos nao funcionais

- **Conformidade**: o grafo gerado e verificado contra *shapes* SHACL derivadas do CRM; violacoes de dominio/alcance sao detetadas.
- **Independencia de rede**: a projecao nao depende de resolucao remota de contexto.
- **Nomenclatura**: as classes ORM deste contexto usam sufixo `...Orm`, porque o dominio ja possui os nomes `...Record`.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Agregado e filhos (RF-001..RF-003) | `app/cidoc_crm/in_situ_visit_mapping/domain/models.py` |
| Regras de mapeamento (RF-006..RF-012) | `app/cidoc_crm/in_situ_visit_mapping/application/cidoc/in_situ_visit_to_cidoc.json`, `engine.py` |
| Contexto e *shapes* (RF-008, RF-013) | `application/cidoc/cidoc_context_7.1.3.jsonld`, `application/cidoc/shapes/` |
| Validacao e raciocinio (RF-013, RF-014) | `application/cidoc/reasoning.py` |
| Camada anti-corrupcao (RF-010) | `infrastructure/context_acl.py` |
| Endpoints (RF-001, RF-013, RF-015) | `presentation/routes.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |
| Modelo visual | `docs/diagrams/cidoc-crm-in-situ-visit-record-model.svg` |

## 9. Questoes em aberto

1. A projecao deve ser publicada num ponto de acesso permanente (URI resolvivel por registo), e com que politica de versao?
2. Que criterio autoriza tipar um objeto como `crm:E20_Biological_Object` — a colecao de origem basta?
