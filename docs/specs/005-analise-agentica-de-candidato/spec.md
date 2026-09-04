# SPEC-005 — Analise agentica de candidato e retorno curatorial

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-005 |
| Estado | Implementado |
| Contexto delimitado | `app/scientific_return` |
| Escrita a partir de | `application/agent_analysis.py`, `application/full_agentic.py`, `domain/models.py`, `test/scientific_return/test_scientific_return.py`; revista a 2026-09-04 apos a remocao da geracao em sombra (commit `a571392`) |
| Specs relacionadas | [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md), [SPEC-016](../016-prompts-versionados/spec.md), [SPEC-024](../024-investigacao-agentica-autonoma/spec.md) |

## 1. Problema

O pipeline deterministico explica **que** sinais encontrou, mas nao ajuda o
curador a pesar sinais contraditorios: um homonimo de autor, um especime
semelhante de outra colecao, uma citacao de catalogo em vez de estudo do
material. Essa leitura consome tempo especializado.

Ao mesmo tempo, colocar um modelo de linguagem no caminho da decisao curatorial
e inaceitavel. E preciso um degrau intermedio que produza valor sem produzir
autoridade.

## 2. Objetivo

Conservar, para auditoria e avaliacao, a **analise consultiva** que o leitor do
ciclo agentico produz sobre um candidato, e recolher do staff se ela foi util —
sem que nada disso toque no estado do candidato.

A geracao em sombra sob bandeira propria, que existiu na Fase 3B, foi removida
no commit `a571392`: a analise passou a nascer do leitor do ciclo autonomo
([SPEC-024](../024-investigacao-agentica-autonoma/spec.md)), nao de um pedido
avulso. O que esta spec descreve e o que restou — o registo e o retorno
curatorial.

## 3. Linguagem ubiqua

- **Analise agentica**: parecer estruturado que o leitor do ciclo agentico produz sobre um candidato, sem efeito de estado. Estados `RUNNING`, `COMPLETED`, `FAILED`.
- **Accao recomendada**: valor tipado que o modelo propoe para revisao humana; nunca executado por esta funcionalidade.
- **Feedback**: apreciacao do staff sobre a utilidade da analise — `USEFUL`, `PARTIALLY_USEFUL`, `NOT_USEFUL`.
- **Confianca advisory**: `LOW`, `MEDIUM`, `HIGH`; qualificador de leitura, nao criterio de decisao.

---

## 4. Requisitos funcionais

### RF-001 — Persistencia para auditoria

Uma analise nasce do **leitor** do ciclo agentico, identificado pelo prefixo do
prompt de leitura. Registos que nao venham do leitor nao contam como analise:
ficam fora do historico e nao aceitam feedback.

Cada analise guarda: modelo utilizado, identificador e rotulo da versao do
prompt publicado, entrada e saida cifradas, hashes, latencia, mensagem de erro
quando aplicavel e o feedback do staff.

### RF-002 — Historico

`GET /api/v1/scientific-return/candidates/{candidateId}/agent-analyses` devolve
o historico de auditoria do candidato.

### RF-003 — Feedback uma unica vez

`POST /api/v1/scientific-return/agent-analyses/{analysisId}/feedback` regista
`USEFUL`, `PARTIALLY_USEFUL` ou `NOT_USEFUL`. Exige analise `COMPLETED` e so
pode ser registado uma vez por analise.

### RF-004 — Ausencia de efeitos

A analise **nunca**: altera o estado do candidato, cria uma decisao ou escreve
no `PublicationLog`. A accao proposta e exibida para revisao; a sua execucao
pertence ao ciclo agentic supervisionado
([SPEC-001](../001-investigacao-agentica-assistida/spec.md)) e exige politica
deterministica propria.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | A analise nunca altera o estado de um candidato |
| INV-002 | Uma analise falhada e persistida, nunca silenciada |
| INV-003 | Toda a analise identifica o modelo e a versao do prompt que a produziram |
| INV-004 | O feedback e irrepetivel por analise |
| INV-005 | Texto de publicacao e dado, nunca instrucao |
| INV-006 | So um registo do leitor conta como analise |

## 6. Criterios de aceitacao

### CA-001 — Historico e feedback contam so o que veio do leitor
Dado registos de analise do leitor e de outra origem sobre o mesmo candidato
Quando o historico e lido e o feedback e registado
Entao apenas os registos do leitor aparecem e aceitam feedback
→ `test_scientific_return.py::test_analysis_history_and_feedback_exclude_non_reader_records`, `::test_non_reader_analysis_does_not_create_agentic_decision_context`

### CA-002 — Feedback uma unica vez, sobre analise concluida
Dado uma analise `COMPLETED`
Quando o staff regista a sua apreciacao
Entao e aceite uma vez e recusada a segunda
→ `test_scientific_return.py::test_curator_can_record_feedback_once_on_completed_analysis`

### CA-003 — A analise identifica o prompt publicado que a produziu
Dado uma analise persistida
Quando e lida da base de dados
Entao traz o identificador da versao de prompt realmente publicada
→ `test_full_agentic_repository_postgres.py::test_agent_analysis_accepts_the_real_published_prompt_id`

### CA-004 — A geracao em sombra saiu do contrato publico
Dado o esquema OpenAPI publicado
Quando e inspecionado
Entao nao expoe geracao em sombra e mantem a provenencia do leitor
→ `test_api_contract.py::test_openapi_removes_shadow_generation_but_keeps_reader_provenance`

### CA-005 — A remocao nao repoe dados apagados
Dado a migracao de remocao da analise em sombra
Quando e revertida
Entao restaura a estrutura mas nao os dados de analise apagados
→ `test_shadow_removal_migration.py::test_downgrade_restores_prompt_structure_but_not_deleted_analysis_data`

## 7. Requisitos nao funcionais

- **Postura legal e institucional**: a saida do modelo nunca e apresentada como autorizacao, aprovacao ou determinacao factual.
- **Confidencialidade**: entrada e saida cifradas em repouso; nenhum segredo ou credencial entra no prompt.
- **Observabilidade**: latencia e versao de prompt guardadas por analise, para comparar modelos e prompts ao longo do tempo.
- **Custo**: a analise e acionada manualmente, uma por pedido.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Casos de uso (RF-002, RF-007, RF-008) | `app/scientific_return/application/agent_analysis.py` |
| Contrato de saida (RF-004) | `app/scientific_return/application/agent_analysis.py`, `domain/models.py` |
| Agregado da analise (RF-005, RF-006, INV-006) | `app/scientific_return/domain/models.py` |
| Adaptador do fornecedor (RF-001, RF-006) | `app/scientific_return/infrastructure/reasoner_ollama.py` |
| Prompt publicado (RF-002, RF-005) | `app/scientific_return/infrastructure/prompt_acl.py`, `app/ai/prompts` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 9. Questoes em aberto

1. O feedback acumulado deve alimentar uma metrica publicada de utilidade por versao de prompt?
2. A analise em sombra continua a justificar-se agora que existe o ciclo agentic supervisionado, ou converge para ele?
