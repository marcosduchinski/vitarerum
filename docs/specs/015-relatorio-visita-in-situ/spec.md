# SPEC-015 — Relatorio de visita in situ

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-015 |
| Estado | Implementado |
| Contexto delimitado | `app/reports/in_situ_visit` |
| Escrita a partir de | `app/reports/in_situ_visit/`, `test/reports/`, contrato 10 |
| Specs relacionadas | [SPEC-013](../013-mapeamento-cidoc-crm/spec.md), [SPEC-017](../017-narrativa-museologica/spec.md), [SPEC-009](../009-projeto-uso-de-colecoes/spec.md) |

## 1. Problema

Produzir um relatorio de visita in situ exige duas operacoes ja existentes —
exportar o projeto para o modelo CIDOC-CRM e gerar a narrativa a partir desse
registo — mas nada guarda a ligacao entre as tres coisas. Sem essa ligacao, um
relatorio e um par de identificadores que alguem anotou.

## 2. Objetivo

Compor as duas operacoes numa unica chamada transacional e persistir a ligacao
entre projeto, registo exportado e narrativa gerada como um relatorio duravel e
auditavel.

## 3. Natureza do contexto

E um **orquestrador entre contextos**: possui apenas o agregado
`InSituVisitReport` e compoe os casos de uso de exportacao e de narrativa
atraves das respetivas interfaces publicadas. Nunca toca nos agregados de outro
contexto.

---

## 4. Requisitos funcionais

### RF-001 — Composicao numa unica chamada

`POST /api/v1/reports/collection-use/{projectId}/in_situ_visit`, apenas para
staff, executa por esta ordem:

1. exporta o projeto para um novo registo de visita;
2. gera uma narrativa a partir desse registo, com os parametros do corpo;
3. constroi e persiste o relatorio, carimbando autor e instante do servidor;
4. faz commit uma unica vez e responde `201`.

### RF-002 — Uma unica transacao

Toda a cadeia corre na mesma transacao de base de dados. Uma falha na geracao da
narrativa **nao deixa registo orfao**.

### RF-003 — Parametros opcionais encaminhados

O corpo aceita `target_language` (omissao `pt`), `narrative_type` (omissao
`institutional`) e `creativity_temperature` (omissao `0.3`, entre 0.0 e 1.0),
encaminhados para a geracao da narrativa.

### RF-004 — Pre-condicao herdada

O projeto tem de ter tipo de uso `IN_SITU_VISIT` e evidencia de execucao — a
mesma pre-condicao da exportacao
([SPEC-013](../013-mapeamento-cidoc-crm/spec.md), RF-005).

### RF-005 — Cada chamada e acrescento

Nao ha deduplicacao por projeto: cada chamada produz um registo novo, uma
narrativa nova e um relatorio novo. Chamar duas vezes produz dois relatorios
independentes.

A escolha e deliberada: um relatorio e um ato datado, e refazer um relatorio nao
apaga o anterior.

### RF-006 — Resposta apenas com identificadores

A resposta `201` devolve identificadores. O conteudo do registo e da narrativa e
obtido pelos respetivos endpoints.

### RF-007 — Mapeamento de erros da cadeia

| Situacao | Codigo |
| --- | --- |
| Chamador `EXTERNAL` | `403` |
| Projeto inexistente | `404` |
| Tipo de uso errado | `409` |
| Visita sem evidencia de execucao | `409` |
| Tipo de narrativa nao suportado | `400` |
| Temperatura fora de 0.0–1.0 | `422` |
| Falha de validacao semantica do grafo | `422` |
| Modelo indisponivel | `503` |
| Modelo esgotou o tempo | `504` |

Cada falha da cadeia mantem o codigo que lhe corresponde na operacao de origem:
o orquestrador nao achata tudo em `500`.

### RF-008 — Leitura do historico

- listagem de todos os relatorios, do mais recente para o mais antigo, paginada;
- listagem por projeto, isolada entre projetos;
- leitura por identificador, `404` quando o relatorio nao pertence ao projeto indicado;
- leitura detalhada com narrativa e registo embebidos.

Um projeto desconhecido devolve **pagina vazia**, nao erro: a ausencia de
relatorios e informacao legitima.

### RF-009 — Campos de apresentacao e filtros

As linhas da listagem global transportam campos de apresentacao do registo e
podem ser filtradas por metadados do registo e da geracao.

### RF-010 — Trilho de auditoria em seis fases

O detalhe de auditoria expoe as entradas de cada fase da cadeia **sem recalcular**
o documento CIDOC: o que se audita e o que foi usado, nao o que se obteria hoje.

### RF-011 — Remocao delimitada

Apagar um relatorio remove o relatorio e os artefactos da narrativa que ele
gerou — e apenas esses. O que existia antes da cadeia permanece.

### RF-012 — Rasto de auditoria de um relatorio

`GET /reports/collection-use/{projectId}/in_situ_visit/{reportId}/audit-trail`
devolve, numa leitura so, as seis entradas que produziram o relatorio, para que
depois se possa reconstituir como ele foi feito:

| Entrada | O que contem |
| --- | --- |
| `evidence` | Identificadores do registo e do projeto que serviram de origem |
| `cidoc` | O documento JSON-LD gerado e o relatorio de validacao, com `conforms` |
| `facts` | O payload factual entregue ao modelo, incluindo lacunas de evidencia |
| `generation` | Versao do prompt que correu, o seu identificador e o hash da resposta |
| `validation` | Resultado da validacao da narrativa |
| `revisions` | Historico paginado de edicoes humanas (`revisionsPage`, `revisionsSize`, maximo 100) |

Alem destas, embute o registo (`record`) e a narrativa (`narrative`) tal como
ficaram. O CIDOC **nao e recalculado** na leitura: e devolvido o documento
persistido no momento da geracao — sem isso o rasto deixaria de descrever o que
aconteceu e passaria a descrever o presente.

Restrito a staff; um chamador `EXTERNAL` recebe `403`. Um relatorio pedido sob
um projeto que nao e o seu responde `404` com `REPORT_NOT_FOUND`, e nao o
conteudo de outro projeto.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | O contexto so possui o agregado do relatorio |
| INV-002 | Os outros contextos sao alcancados apenas pelas suas interfaces publicadas |
| INV-003 | Nao existe registo ou narrativa orfaos por falha a meio da cadeia |
| INV-004 | Cada relatorio identifica projeto, registo e narrativa |
| INV-005 | A auditoria mostra as entradas efetivamente usadas, nunca recalculadas |
| INV-006 | Um relatorio nunca e visivel sob um projeto que nao o seu |

## 6. Criterios de aceitacao

### CA-001 — Composicao feliz e ligacao persistida
→ `test_in_situ_visit_report_api.py::test_happy_path_returns_201_linking_record_and_narrative`

### CA-002 — Mapeamento de erros da cadeia
→ `test_in_situ_visit_report_api.py::test_forbidden_for_external_caller`, `::test_project_not_found_maps_to_404`, `::test_wrong_use_type_maps_to_409`, `::test_visit_without_execution_evidence_maps_to_409`, `::test_unsupported_narrative_type_maps_to_400`, `::test_temperature_above_one_is_422`, `::test_semantic_validation_failure_maps_to_422`, `::test_model_unavailable_maps_to_503`, `::test_model_timeout_maps_to_504`

### CA-003 — Historico por projeto e global
→ `test_in_situ_visit_report_read_api.py::test_list_returns_project_reports_newest_first`, `::test_list_isolated_per_project`, `::test_list_unknown_project_is_empty_page`, `::test_list_all_spans_every_project_newest_first`, `::test_list_all_paginates`

### CA-004 — Leitura por identificador e isolamento por projeto
→ `test_in_situ_visit_report_read_api.py::test_get_by_id_returns_report`, `::test_get_by_id_unknown_is_404`, `::test_get_by_id_wrong_project_is_404`, `test_in_situ_visit_report_detail_api.py::test_detail_unknown_report_is_404`, `::test_detail_wrong_project_is_404`

### CA-005 — Campos de apresentacao e filtros
→ `test_in_situ_visit_report_read_api.py::test_list_all_rows_carry_record_display_fields`, `::test_list_all_filters_by_record_and_generation_metadata`

### CA-006 — Detalhe embebido e auditoria sem recalculo
→ `test_in_situ_visit_report_detail_api.py::test_detail_embeds_narrative_and_record_with_attachment`, `::test_audit_trail_embeds_six_stage_inputs_without_recomputing_cidoc`, `::test_audit_trail_wrong_project_is_404`

### CA-007 — Autorizacao staff-only
→ `test_in_situ_visit_report_read_api.py::test_list_forbidden_for_external`, `::test_list_all_forbidden_for_external`, `::test_get_by_id_forbidden_for_external`, `test_in_situ_visit_report_detail_api.py::test_audit_trail_forbidden_for_external`, `::test_detail_forbidden_for_external`

### CA-008 — Remocao delimitada
→ `test_in_situ_visit_report_detail_api.py::test_delete_removes_report_and_generated_narrative_artifacts_only`

### CA-009 — Rasto completo sem recalcular o CIDOC
Dado um relatorio gerado e depois editado por uma pessoa
Quando o rasto de auditoria e lido
Entao devolve as seis entradas, o CIDOC persistido com o seu relatorio de validacao, a versao do prompt que correu, o hash da resposta e a revisao humana com o texto anterior, o novo e quem editou
→ `test_in_situ_visit_report_detail_api.py::test_audit_trail_embeds_six_stage_inputs_without_recomputing_cidoc`

### CA-010 — Rasto fechado ao projeto errado e a quem nao e staff
Dado um relatorio de um projeto
Quando e pedido sob outro projeto, ou por um chamador `EXTERNAL`
Entao responde `404` com `REPORT_NOT_FOUND`, e `403`, respetivamente
→ `test_in_situ_visit_report_detail_api.py::test_audit_trail_wrong_project_is_404`, `::test_audit_trail_forbidden_for_external`

## 7. Requisitos nao funcionais

- **Transacionalidade**: um commit por relatorio (RF-002).
- **Fronteiras**: composicao apenas por linguagem publicada; contratos import-linter preservados.
- **Custo**: cada chamada invoca um modelo local; o acrescento sem deduplicacao e uma decisao consciente de custo.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Agregado do relatorio | `app/reports/in_situ_visit/domain/` |
| Orquestracao (RF-001, RF-002, RF-007) | `app/reports/in_situ_visit/application/` |
| Endpoints e leituras (RF-008..RF-012) | `app/reports/in_situ_visit/presentation/` |
| Composicao do rasto de auditoria (RF-012) | `app/reports/in_situ_visit/application/use_cases.py` (`GetInSituVisitReportAuditTrail`) |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 9. Questoes em aberto

1. Um relatorio deve poder ser marcado como "oficial" entre varios do mesmo projeto?
2. A cadeia sincrona e aceitavel enquanto o modelo for local; que forma toma se a geracao passar a demorar minutos?
