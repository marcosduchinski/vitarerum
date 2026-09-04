# SPEC-003 — Pipeline deterministico de descoberta bibliografica

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-003 |
| Estado | Implementado |
| Contexto delimitado | `app/scientific_return` |
| Escrita a partir de | `application/analysis.py`, `application/use_cases.py`, `infrastructure/{crossref,openalex,europe_pmc}.py`, `test/scientific_return/` |
| Specs relacionadas | [SPEC-002](../002-vigilancia-retorno-cientifico/spec.md), [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md) |

## 1. Problema

Procurar publicacoes decorrentes de um projeto exige formular consultas a varias
fontes, reconhecer o que e relevante, nao repetir trabalho ja feito e conseguir
justificar, mais tarde, porque e que um resultado foi apresentado ao staff.

## 2. Objetivo

Executar uma pesquisa **deterministica e auditavel** a partir do snapshot do
projeto: mesmas entradas, mesmas consultas, mesmas evidencias. O que a pesquisa
produz sao **candidatos com evidencia explicada**, nunca decisoes.

## 3. Linguagem ubiqua

- **Execucao (`run`)**: uma passagem completa da pesquisa sobre uma vigilancia.
- **Consulta (`query`)**: um pedido a uma fonte, com texto exato, tipo, fonte, contagem de resultados e estado.
- **Estrategia**: combinacao de termos que origina uma consulta (`INVENTORY`, `AUTHOR_INVENTORY`, `INVENTORY_OBJECT`, `AUTHOR_OBJECT`).
- **Candidato**: registo bibliografico normalizado que reuniu evidencia acionavel.
- **Evidencia**: razao tipada e explicada pela qual um registo se relaciona com o projeto, com forca `PRIMARY`, `SUPPORTING` ou `WEAK`.
- **Chave de deduplicacao**: identidade estavel de um registo entre consultas, fontes e execucoes.

## 4. Escopo

**Dentro:** planeamento de consultas, adaptacao ao genero, execucao contra as
fontes, normalizacao, deduplicacao, construcao de evidencia, criterio de
acionabilidade, auditoria da execucao.

**Fora:** cadencia (SPEC-002), decisao humana (SPEC-004), ciclo agentic
(SPEC-001).

---

## 5. Requisitos funcionais

### RF-001 — Executar e inspecionar pesquisas

- `POST /api/v1/scientific-return/watches/{watchId}/runs`
- `GET /api/v1/scientific-return/watches/{watchId}/runs?page=0&size=10`

A execucao so ocorre sobre uma vigilancia `ACTIVE` com snapshot presente.

### RF-002 — Planeamento a partir do snapshot

Para cada objeto consultado, o planeador gera exatamente quatro estrategias:

| Tipo | Termos |
| --- | --- |
| `INVENTORY` | numero de inventario |
| `AUTHOR_INVENTORY` | investigador + numero de inventario |
| `INVENTORY_OBJECT` | numero de inventario + nome do objeto |
| `AUTHOR_OBJECT` | investigador + nome do objeto |

Cada termo e enviado como frase exata. Consultas duplicadas entre objetos sao
eliminadas mantendo a ordem. Nenhum outro dado do projeto entra numa consulta.

### RF-003 — Adaptacao ao genero

Quando as estrategias exatas de uma fonte nao produzem candidato novo, sao
acrescentadas ate duas estrategias que substituem o nome binomial do objeto pelo
seu genero (`INVENTORY_OBJECT` e `AUTHOR_OBJECT`). Nomes nao binomiais nao geram
adaptacao. A adaptacao e auditada como qualquer outra consulta.

### RF-004 — Fontes ativas

| Fonte | Condicao |
| --- | --- |
| Crossref | sempre ativa |
| OpenAlex | quando `OPENALEX_API_KEY` esta configurada |
| Europe PMC | quando `EUROPE_PMC_ENABLED=true` |

O texto integral em acesso aberto do Europe PMC e inspecionado transitoriamente
para produzir evidencia e **nao e persistido**.

### RF-005 — Encaminhamento do autor

Quando a estrategia inclui o investigador, o nome viaja tambem num campo
proprio, para que uma fonte que indexa autores fora do indice de texto livre o
possa encaminhar sem adivinhar qual frase citada e uma pessoa. O texto da
consulta auditada continua a ser o que foi efetivamente enviado.

### RF-006 — Teto de consultas por execucao

`SCIENTIFIC_RETURN_MAX_QUERIES_PER_RUN` (40 por omissao) limita o total de
consultas de uma execucao. O teto e **partilhado entre fontes**, nao por fonte.

### RF-007 — Civismo e resiliencia perante as fontes

- `CROSSREF_MAILTO` identifica a instalacao perante o *polite pool*.
- As chamadas sao serializadas com intervalo minimo configuravel.
- `429`, `500`, `502`, `503` e `504` sao repetidas com recuo exponencial ou com o `Retry-After` do servidor, ate `CROSSREF_MAX_RETRIES`.
- Erros permanentes de cliente nao sao repetidos.

### RF-008 — Normalizacao para comparacao

O numero de inventario e comparado numa forma compacta que ignora separadores e
caixa, corrige a troca conhecida `MUNHAC` por `MUHNAC` e colapsa segmentos de
codigo de colecao repetidos. Os textos sao comparados sem acentos e sem
pontuacao. Alem da forma compacta, e tentada a forma reduzida ao codigo de
colecao.

### RF-009 — Deduplicacao

A identidade de um registo e o DOI normalizado quando existe; caso contrario,
um hash de titulo, data de publicacao e primeiro autor. O mesmo registo
encontrado por varias estrategias ou fontes produz um unico candidato.

### RF-010 — Construcao de evidencia

| Evidencia | Forca | Condicao |
| --- | --- | --- |
| `AUTHOR` | `SUPPORTING` | Os tokens do investigador estao contidos nos de um autor |
| `INVENTORY_NUMBER` | `PRIMARY` | Uma variante do inventario ocorre nos metadados ou no texto indexado |
| `OBJECT_NAME` | `SUPPORTING` | O nome exato do objeto ocorre no texto |
| `OBJECT_NAME` | `WEAK` | Apenas o genero do taxon ocorre no texto |
| `AUTHOR_INVENTORY` | `PRIMARY` | Autor e inventario coincidem no mesmo registo |
| `INVENTORY_OBJECT` | `PRIMARY` | Inventario e objeto coincidem no mesmo registo |
| `AUTHOR_OBJECT` | `SUPPORTING` | Autor e objeto (ou genero) coincidem no mesmo registo |

Cada evidencia regista o campo de origem (`title_or_abstract`, texto indexado, ou
combinacao) e uma explicacao legivel. Evidencias especificas de objeto guardam o
`objectId` correspondente.

### RF-011 — Criterio de acionabilidade

Um registo so se torna candidato quando reune pelo menos uma evidencia de
`INVENTORY_NUMBER`, `AUTHOR_INVENTORY`, `INVENTORY_OBJECT` ou `AUTHOR_OBJECT`.

Consequencia deliberada: coincidencia de autor isolada, ou de nome de objeto
isolada, **nao** cria candidato. Um taxonomista publica dezenas de artigos sobre
o mesmo genero sem tocar no especime consultado.

### RF-012 — Reaparecimento de candidato conhecido

Um registo ja conhecido nao gera candidato novo. Se estiver `SNOOZED` com prazo
expirado, volta a `PENDING`. Candidatos `DISMISSED` permanecem descartados: a
memoria da decisao humana sobrevive as execucoes seguintes.

### RF-013 — Auditoria da execucao

Cada consulta e persistida com fonte, texto exato, tipo, instante, contagem de
resultados, estado (`COMPLETED`/`FAILED`) e mensagem de erro quando aplicavel.
A execucao regista numero de fontes, `candidateCount` (candidatos tocados,
incluindo conhecidos) e `newCandidateCount` (descobertas dessa execucao).

### RF-014 — Estado da execucao perante falhas

Uma execucao so e `FAILED` quando **todas** as consultas falharam. Falhas
parciais produzem `COMPLETED` com as mensagens de erro registadas: resultados
parciais uteis nao sao descartados por causa de uma fonte indisponivel.

---

## 6. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Toda a consulta enviada deriva exclusivamente do snapshot imutavel |
| INV-002 | O texto exato de cada consulta enviada e persistido e cifrado em repouso |
| INV-003 | Nenhum candidato e criado sem evidencia acionavel |
| INV-004 | O pipeline nunca decide, confirma ou descarta um candidato |
| INV-005 | O texto integral consultado transitoriamente nao e persistido |
| INV-006 | Um registo identico nunca produz dois candidatos na mesma vigilancia |
| INV-007 | O teto de consultas nunca e excedido, qualquer que seja o numero de fontes |

## 7. Criterios de aceitacao

### CA-001 — O planeador usa apenas autor, inventario e objeto
→ `test_scientific_return.py::test_planner_uses_only_author_inventory_and_object`

### CA-002 — A adaptacao so alarga nomes binomiais para o genero
→ `test_scientific_return.py::test_adaptive_planner_broadens_only_binomial_object_to_genus`

### CA-003 — A adaptacao ocorre depois de as consultas exatas nada produzirem
→ `test_scientific_return.py::test_pipeline_uses_adaptive_query_after_exact_queries_fail`

### CA-004 — Normalizacao de prefixo de museu e segmentos repetidos
→ `test_scientific_return.py::test_evidence_normalizes_museum_prefix_and_repeated_inventory_segments`

### CA-005 — Deduplicacao entre trajetorias de consulta
→ `test_scientific_return.py::test_pipeline_deduplicates_same_record_across_query_trajectories`

### CA-006 — Teto de consultas por execucao e partilha entre fontes
→ `test_scientific_return.py::test_pipeline_caps_external_queries_per_run`, `::test_pipeline_query_cap_is_shared_across_sources`

### CA-007 — Memoria de descarte entre execucoes
→ `test_scientific_return.py::test_dismissed_candidate_is_remembered_on_later_run`

### CA-008 — Crossref repete `429` respeitando `Retry-After` e nao repete erro permanente
→ `test_crossref.py::test_crossref_retries_429_using_retry_after`, `::test_crossref_does_not_retry_permanent_client_error`

### CA-009 — OpenAlex mapeia DOI, autores e resumo invertido, e encaminha o autor
→ `test_openalex.py::test_openalex_maps_doi_authors_and_inverted_abstract`, `::test_openalex_routes_the_author_out_of_the_free_text_search`, `::test_openalex_searches_by_author_alone_when_no_terms_remain`, `::test_openalex_requires_api_key`

### CA-010 — Europe PMC enriquece com texto integral e evita repetir o pedido
→ `test_europe_pmc.py::test_europe_pmc_enriches_record_with_open_access_full_text`, `::test_europe_pmc_caches_full_text_between_queries`

## 8. Requisitos nao funcionais

- **Reprodutibilidade**: as mesmas entradas produzem as mesmas consultas e evidencias; a avaliacao depende disso ([SPEC-006](../006-avaliacao-retorno-cientifico/spec.md)).
- **Explicabilidade**: nenhuma evidencia e apresentada sem campo de origem e explicacao legivel.
- **Custo e civismo**: teto de consultas, serializacao e identificacao perante as fontes.
- **Isolamento**: nenhuma transacao aberta enquanto uma fonte responde.

## 9. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Planeamento e adaptacao (RF-002, RF-003) | `app/scientific_return/application/analysis.py` |
| Normalizacao, deduplicacao, evidencia, acionabilidade (RF-008..RF-011) | `app/scientific_return/application/analysis.py` |
| Orquestracao da execucao (RF-001, RF-006, RF-012..RF-014) | `app/scientific_return/application/use_cases.py` |
| Adaptadores de fonte (RF-004, RF-005, RF-007) | `app/scientific_return/infrastructure/{crossref,openalex,europe_pmc}.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 10. Questoes em aberto

1. O criterio de acionabilidade devia ponderar a data de publicacao face a data do projeto?
2. Vale a pena persistir um excerto do texto integral que fundamentou a evidencia, dado o custo de privacidade e de armazenamento?
