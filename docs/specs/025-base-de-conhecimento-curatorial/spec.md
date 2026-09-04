# SPEC-025 — Base de conhecimento curatorial

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-025 |
| Estado | Implementado |
| Contexto delimitado | `app/scientific_return` |
| Postura | Memoria proposta pelo modelo, validada por pessoas |
| Specs relacionadas | [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-024](../024-investigacao-agentica-autonoma/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md) |
| Documentos relacionados | `docs/api_contracts/README.md` |
| Escrita a partir de | `app/scientific_return/application/knowledge.py`, `presentation/routes.py`, `test/scientific_return/test_full_agentic_knowledge.py` |

---

## 1. Problema

Um agente que investiga retorno cientifico repete os mesmos enganos: nao sabe
que naquela instituicao o numero `MB 12-345` tambem aparece escrito
`MB12.345`, nem porque e que um curador recusou determinado candidato no mes
passado. Sem memoria, cada investigacao comeca do zero e a instituicao nao
capitaliza o trabalho que ja fez.

Uma memoria que o modelo escreva sozinho e, porem, um caminho rapido para
consolidar erros: uma alucinacao guardada passa a informar todas as
investigacoes seguintes.

## 2. Objetivo

Manter uma memoria institucional que informa o agente e que **so entra em uso
depois de uma pessoa a validar**, preservando o historico de tudo o que ja foi
dito — corrigido ou retirado.

## 3. Atores

| Ator | Papel |
| --- | --- |
| `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION` | Criam, corrigem, retiram e reativam conhecimento |
| Restante staff | Le a base e o historico; nao escreve |
| Modelo de linguagem | Propoe conhecimento a partir de uma decisao curatorial; nunca o ativa |

## 4. Linguagem ubiqua

- **Item de conhecimento**: unidade de memoria da instituicao. Tipos `INVENTORY_VARIATION_EXAMPLE` (forma alternativa observada de um numero de inventario) e `CURATORIAL_LESSON` (licao em texto livre).
- **Estado**: `PROPOSED` (proposto pelo modelo, por validar), `ACTIVE` (em uso), `RETIRED` (fora de uso, preservado).
- **Sucessao**: relacao entre um item corrigido e o que o substituiu.
- **Linhagem**: cadeia completa de sucessao de um item.
- **Proposta de aprendizagem**: item derivado de uma decisao curatorial, com a explicacao dada pelo curador.

---

## 5. Requisitos funcionais

### RF-001 — Criar conhecimento curatorial

`POST /scientific-return/knowledge-items` cria um item **diretamente `ACTIVE`**,
com o autor registado tambem como validador. Restrito a `CURATORIAL`,
`COLLECTIONS_MANAGEMENT` e `DIRECTION`.

Um item escrito por uma pessoa nasce validado porque a validacao ja aconteceu:
foi a propria escrita.

### RF-002 — Propor conhecimento a partir de uma decisao

`POST /scientific-return/candidates/{candidateId}/knowledge-proposals` deriva um
item da ultima decisao curatorial sobre o candidato, com a explicacao dada pelo
curador. Sem decisao registada responde `404`
`SCIENTIFIC_RETURN_DECISION_NOT_FOUND`; explicacao vazia responde `422`.

O item nasce `PROPOSED`, guardando o modelo que o propos, a versao do prompt, o
candidato e a decisao de origem. O tipo e derivado do conteudo: com numero
registado **e** forma observada e `INVENTORY_VARIATION_EXAMPLE`; caso contrario
e `CURATORIAL_LESSON`.

### RF-003 — Listagem com filtros e contagens

`GET /scientific-return/knowledge-items` devolve pagina (`page`, `size` maximo
100) filtrada por `status`, `kind` e `q`, com as contagens por estado.

`q` procura no conteudo e nas citacoes de inventario, ignorando maiusculas e
acentos. O parametro `inventoryNumber` esta substituido por `q` e mantido para
nao quebrar clientes antigos.

Restrito a staff; exige permissao institucional ativa.

### RF-004 — Correcao preserva a historia

`PUT /scientific-return/knowledge-items/{itemId}` **nao altera** o item: cria um
sucessor `ACTIVE`, ja validado por quem corrigiu, e retira o anterior, ligando os
dois por sucessao.

Uma memoria e um registo do que a instituicao acreditou e quando. Reescrever no
sitio apagaria a razao pela qual uma investigacao antiga concluiu o que concluiu.

### RF-005 — Retirar e reativar

`DELETE /scientific-return/knowledge-items/{itemId}` passa o item a `RETIRED`;
`POST /scientific-return/knowledge-items/{itemId}/activate` devolve-o a `ACTIVE`.
Nenhuma das operacoes apaga. Reativar um item ja `ACTIVE` mantem a validacao
original — nao a substitui pela de quem reativou.

`DELETE` responde com o item no seu novo estado, nao `204`: quem retira precisa
de ver o que ficou registado.

### RF-006 — Historico de linhagem

`GET /scientific-return/knowledge-items/{itemId}/history` devolve a cadeia
completa de sucessao do item. Restrito a staff.

### RF-007 — Recuperacao pelo agente

O agente recupera **apenas** conhecimento `ACTIVE` da propria instituicao, ate
ao limite configurado (`memory_limit`, por omissao 30) contado globalmente e nao
por objeto. Itens estruturalmente semelhantes ao alvo precedem itens recentes
mas nao relacionados.

Um item `PROPOSED` ou `RETIRED` nunca informa uma investigacao. E o que torna a
validacao humana uma fronteira real e nao uma formalidade.

### RF-008 — Isolamento institucional

Um item de outra instituicao responde `404`, tanto na leitura como na escrita —
nunca `403`. A existencia de conhecimento alheio nao e revelada. Listar sem
permissao institucional ativa responde `422`.

---

## 6. Invariantes

- **INV-001**: um item criado por uma pessoa nasce `ACTIVE` e validado; um item proposto pelo modelo nasce `PROPOSED` e por validar.
- **INV-002**: nenhuma operacao apaga um item; `RETIRED` e um estado, nao uma remocao.
- **INV-003**: uma correcao cria sempre um sucessor e retira o antecessor; a cadeia de sucessao nao tem interrupcoes.
- **INV-004**: so itens `ACTIVE` sao recuperados pelo agente.
- **INV-005**: um item pertence a exatamente uma instituicao e nunca atravessa essa fronteira.
- **INV-006**: reativar preserva a validacao original.
- **INV-007**: um item `PROPOSED` guarda sempre o modelo e a versao de prompt que o produziram.

---

## 7. Criterios de aceitacao

### CA-001 — Criacao curatorial nasce ativa
Dado um curador com permissao institucional
Quando cria um exemplo textual de variacao de inventario
Entao o item fica `ACTIVE` e validado por quem o criou
→ `test_full_agentic_knowledge.py::test_curator_creates_active_textual_inventory_example`

### CA-002 — Correcao retira o anterior e preserva a sucessao
Dado um item existente
Quando e corrigido
Entao o anterior fica `RETIRED`, o sucessor fica `ACTIVE` e a ligacao entre os dois e legivel
→ `test_full_agentic_knowledge.py::test_replacement_retires_previous_and_preserves_supersession`

### CA-003 — Retirado e proposto nao informam o agente
Dado um item retirado e uma proposta por validar
Quando o agente recupera memoria
Entao nenhum dos dois aparece
→ `test_full_agentic_knowledge.py::test_retired_memory_is_not_retrieved`, `::test_discarded_proposal_stays_unvalidated_and_unretrieved`, `::test_retrieval_uses_only_active_knowledge_from_the_institution`

### CA-004 — Reativar preserva a validacao original
Dado um item ja `ACTIVE`
Quando e reativado
Entao a validacao original mantem-se
→ `test_full_agentic_knowledge.py::test_reactivating_active_knowledge_keeps_the_original_validation`

### CA-005 — Limite de memoria global
Dado varios objetos com memoria associada
Quando a recuperacao corre
Entao o limite e contado globalmente, nao por objeto, e o item estruturalmente semelhante precede o recente nao relacionado
→ `test_full_agentic_knowledge.py::test_memory_limit_is_global_across_multiple_objects`, `::test_structurally_similar_memory_precedes_unrelated_recent_item`

### CA-006 — Pesquisa por palavras, citacao e acentos
Dado licoes e exemplos de inventario
Quando a base e pesquisada
Entao encontra uma licao pelas suas proprias palavras, encontra uma citacao de inventario, ignora maiusculas e acentos e devolve vazio para um fragmento sem correspondencia
→ `test_full_agentic_knowledge.py::test_search_finds_an_agent_lesson_by_its_own_words`, `::test_search_still_matches_an_inventory_citation`, `::test_search_matches_lesson_content_ignoring_case_and_accents`, `::test_search_ignores_a_citation_fragment_that_matches_nothing`

### CA-007 — Isolamento institucional na leitura e na escrita
Dado conhecimento de outra instituicao
Quando e listado ou alterado
Entao a pagina nao o inclui e a alteracao nao o encontra
→ `test_full_agentic_knowledge.py::test_knowledge_page_is_scoped_to_the_callers_institution`, `::test_mutation_hides_another_institutions_knowledge`

### CA-008 — Listagem exige permissao institucional ativa
Dado um chamador sem instituicao ativa
Quando lista a base
Entao o pedido e recusado
→ `test_full_agentic_knowledge.py::test_institutional_listing_requires_an_active_institution`

### CA-009 — Historico devolve a cadeia completa
Dado um item corrigido mais do que uma vez
Quando o historico e lido
Entao devolve a cadeia de sucessao completa
→ `test_full_agentic_knowledge.py::test_history_returns_the_complete_supersession_chain`

### CA-010 — Contrato publico da listagem
Dado o esquema OpenAPI publicado
Quando e inspecionado
Entao a listagem e o historico de conhecimento aparecem com a sua forma
→ `test_api_contract.py::test_openapi_excludes_bench_and_keeps_operational_scientific_return`

---

## 8. Requisitos nao funcionais

- **Seguranca**: JWT + `X-Permission-Id`; escrita restrita aos grupos curatoriais, leitura a staff.
- **Custo de pesquisa**: a procura textual varre no maximo 2000 itens por consulta; acima disso a pesquisa e limitada, nao silenciosamente truncada nos resultados.
- **Arquitetura**: dominio e aplicacao livres de FastAPI e SQLAlchemy; a Identidade e usada por `identity.public`.

## 9. Rastreabilidade

| Elemento da spec | Localizacao |
| --- | --- |
| Agregado do item e estados | `app/scientific_return/domain/full_agentic_models.py`, `domain/enums.py` |
| Casos de uso (RF-001..RF-006, RF-008) | `app/scientific_return/application/knowledge.py` |
| Recuperacao pelo agente (RF-007) | `app/scientific_return/application/full_agentic.py` |
| Pesquisa e paginacao (RF-003) | `app/scientific_return/infrastructure/full_agentic_repository.py` |
| Endpoints | `app/scientific_return/presentation/routes.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 10. Questoes em aberto

1. Uma proposta do modelo que fique por validar indefinidamente deve expirar, ou acumular-se para sempre na fila?
2. O limite de 30 itens recuperados e adequado a instituicoes com historico longo, ou deve passar a ser proporcional ao acervo?
3. Deve existir revisao periodica do conhecimento `ACTIVE`, dado que uma licao correta em 2026 pode deixar de o ser?
