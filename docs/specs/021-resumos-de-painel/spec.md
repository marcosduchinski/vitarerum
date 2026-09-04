# SPEC-021 — Resumos de painel (dashboard)

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-021 |
| Estado | **Especificado, nao implementado** |
| Contextos envolvidos | `use_of_collections`, `museum_questions`, `collection_object_index` |
| Escrita a partir de | contrato 17 e verificacao do codigo em 2026-08-18 |
| Specs relacionadas | [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-009](../009-projeto-uso-de-colecoes/spec.md), [SPEC-011](../011-perguntas-ao-museu/spec.md), [SPEC-014](../014-catalogo-e-indice-de-objetos/spec.md) |

> **Estado verificado.** Nenhum dos quatro endpoints deste contrato existe no
> codigo: nao ha rotas, casos de uso nem testes. Esta spec descreve o
> comportamento pretendido e serve de entrada para a implementacao. Os criterios
> de aceitacao estao declarados sem teste associado, e isso e uma lacuna
> assumida, nao uma omissao.

## 1. Problema

O painel inicial mostra hoje valores estaticos. Obter os numeros reais custaria
uma chamada HTTP por cartao — cinco chamadas so para as propostas — e um dos
cartoes (backlog de reindexacao do catalogo) nao tem hoje **nenhuma** forma de
ser obtido sem abrir colecao a colecao.

## 2. Objetivo

Fornecer agregacoes de leitura, delimitadas pelo papel do chamador, sobre dados
que os contextos ja persistem. Nenhum conceito de dominio novo, nenhuma tabela
nova.

## 3. Principio de desenho

Cada balde tem de **reproduzir exatamente** o filtro que o ecra correspondente ja
usa. Um resumo que conte de forma diferente do ecra que abre a seguir e pior do
que nao ter resumo.

---

## 4. Requisitos funcionais

### RF-001 — Resumo de propostas

`GET /api/v1/proposals/summary`

| Balde | Filtro equivalente |
| --- | --- |
| `newProposals` | `status=SUBMITTED` |
| `myAssignments` | `status=PENDING` e atribuida ao chamador |
| `othersAssignments` | `status=PENDING` e atribuida a outra pessoa |
| `approved` | `status=APPROVED` |
| `rejectedOrCancelled` | `status` em `REJECTED` ou `CANCELLED` |

`othersAssignments` e calculado **no servidor sobre o conjunto completo**. Hoje o
ecra fa-lo no cliente, sobre uma pagina — o que produz um numero errado.

### RF-002 — Ambito e nulos com significado

Este resumo — ao contrario dos restantes — tambem serve chamadores `EXTERNAL`,
com contagens limitadas as suas proprias propostas.

Para esses chamadores, `newProposals`, `myAssignments` e `othersAssignments` sao
`null`, **nao** `0`: nao existe conceito de atribuicao do ponto de vista deles, e
zero afirmaria que existem zero, o que e falso.

### RF-003 — Resumo de projetos

`GET /api/v1/collection-use-projects/summary` com baldes que correspondem um a um
a `UseStatus`: `pending` (`CREATED`), `inProgress`, `completed`, `cancelled`.

Staff ve todos os projetos; `EXTERNAL` ve apenas os que requereu.

### RF-004 — Resumo de perguntas ao museu

`GET /api/v1/museum-questions/summary`, apenas staff, com baldes que
correspondem um a um a `MuseumQuestionStatus`: `submitted`, `answered`,
`outOfScope`, `closed`.

**Nota de implementacao:** a rota tem de ser declarada **antes** de
`GET /museum-questions/{questionId}`, ou `summary` sera interpretado como
identificador de pergunta.

### RF-005 — Resumo do catalogo de colecoes

`GET /api/v1/admin/collection-data-sources/summary` devolve numero de colecoes,
documentos vivos, documentos por estado e `documentsPendingReindex`.

`documentsPendingReindex` conta documentos vivos com
`contentMatchesSearchableColumns = false`
([SPEC-014](../014-catalogo-e-indice-de-objetos/spec.md), RF-009). E o unico
numero deste conjunto que hoje **nao tem nenhuma outra via de visibilidade no
produto**.

### RF-006 — Ambito do resumo do catalogo

Reproduz o ambito ja usado na listagem de colecoes geriveis:

| Grupo | Ambito |
| --- | --- |
| `SYS_ADMIN`, `COLLECTIONS_MANAGEMENT` | Catalogo inteiro |
| `CURATORIAL` | Apenas as colecoes que curadoria |
| `DIRECTION` | Como um curador sem colecoes: tudo a zero |

O numero e deliberadamente "o que eu posso corrigir", nao uma estatistica global
sobre a qual o curador nao pode agir.

### RF-007 — Somente leitura, sem parametros

Nenhum destes endpoints introduz paginacao, filtragem ou escrita. Sao agregados
de leitura sem parametros, exceto o ambito derivado do chamador.

Necessidades futuras — recortes por intervalo de datas, por colecao — sao
endpoints novos, nao extensoes destes.

### RF-008 — Cartoes que nao precisam de trabalho novo

Os cartoes seguintes ja sao servidos por endpoints existentes e **nao** devem
originar endpoint de resumo:

| Cartao | Endpoint existente | Campo |
| --- | --- | --- |
| Relatorios de visita recentes | `GET /reports/collection-use/in_situ_visit` | `totalElements` |
| Utilizadores | `GET /users` | `totalElements` |
| Grupos | `GET /groups` | comprimento da lista |
| Instituicoes | `GET /institutions` | `totalElements` |
| Modelos de prompt | `GET /ai/prompts` | comprimento da lista |

### RF-009 — Autorizacao pelos padroes existentes

A autorizacao usa os mesmos padroes de verificacao de grupo dos endpoints que
cada resumo agrega.

**Nao** deve ser introduzido um sistema de permissoes por recurso para este
efeito: nao existe no codigo recurso `dashboard.view` nem camada de controlo de
acesso, e nenhum resumo precisa de mais autorizacao do que o endpoint que
agrega.

---

## 5. Invariantes pretendidas

| Id | Invariante |
| --- | --- |
| INV-001 | Cada balde conta exatamente o que o ecra correspondente lista |
| INV-002 | Um balde sem significado para o chamador e `null`, nunca `0` |
| INV-003 | Nenhum resumo escreve, pagina ou filtra |
| INV-004 | O ambito de cada resumo iguala o do endpoint que agrega |

## 6. Criterios de aceitacao *(por implementar)*

| Id | Criterio | Teste |
| --- | --- | --- |
| CA-001 | Os cinco baldes de propostas coincidem com os totais dos cinco ecras | — |
| CA-002 | `othersAssignments` e calculado sobre o conjunto completo, nao sobre uma pagina | — |
| CA-003 | Para `EXTERNAL`, os baldes de atribuicao vêm `null` e os restantes contam apenas as suas propostas | — |
| CA-004 | Os quatro baldes de projetos coincidem com os totais por `UseStatus` | — |
| CA-005 | O resumo de perguntas responde `403` a nao-staff | — |
| CA-006 | `GET /museum-questions/summary` nao e capturado pela rota por identificador | — |
| CA-007 | `documentsPendingReindex` conta documentos vivos com conteudo desatualizado | — |
| CA-008 | Um curador ve apenas as suas colecoes; `DIRECTION` ve zeros | — |

## 7. Lacunas declaradas

1. Nenhum dos quatro endpoints existe (verificado por inspecao das rotas em 2026-08-18).
2. `GET /museum-questions/summary` esta documentado no contrato 14 como se existisse ([SPEC-011](../011-perguntas-ao-museu/spec.md), RF-015).
3. O frontend nao possui modelo, servico nem simulacao de resumo; o painel e um marcador estatico.

## 8. Rastreabilidade prevista

| Elemento | Localizacao prevista |
| --- | --- |
| Resumo de propostas (RF-001, RF-002) | `app/use_of_collections/presentation/proposal_routes.py`, `application/queries.py` |
| Resumo de projetos (RF-003) | `app/use_of_collections/presentation/project_routes.py` |
| Resumo de perguntas (RF-004) | `app/museum_questions/presentation/routes.py` |
| Resumo do catalogo (RF-005, RF-006) | `app/collection_object_index/presentation/routes.py`, `application/use_cases.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 9. Questoes em aberto

1. Confirmar que o contrato 14 deve manter documentado um endpoint por implementar, ou se e preferivel marca-lo explicitamente como planeado.
2. Os resumos devem ser cacheados? Sao leituras agregadas frequentes sobre tabelas que crescem.
