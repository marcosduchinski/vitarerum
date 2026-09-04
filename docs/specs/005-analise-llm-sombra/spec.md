# SPEC-005 — Analise LLM em sombra sobre candidatos

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-005 |
| Estado | Implementado (Fase 3B) |
| Contexto delimitado | `app/scientific_return` |
| Escrita a partir de | `application/agent_analysis.py`, `domain/models.py`, `infrastructure/reasoner_ollama.py`, `test/scientific_return/test_scientific_return.py` |
| Specs relacionadas | [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md), [SPEC-016](../016-prompts-versionados/spec.md) |

## 1. Problema

O pipeline deterministico explica **que** sinais encontrou, mas nao ajuda o
curador a pesar sinais contraditorios: um homonimo de autor, um especime
semelhante de outra colecao, uma citacao de catalogo em vez de estudo do
material. Essa leitura consome tempo especializado.

Ao mesmo tempo, colocar um modelo de linguagem no caminho da decisao curatorial
e inaceitavel. E preciso um degrau intermedio que produza valor sem produzir
autoridade.

## 2. Objetivo

Produzir uma **analise consultiva** sobre um candidato ja criado, executada
depois do pipeline deterministico, persistida integralmente para auditoria e
sem qualquer efeito sobre o estado do candidato.

A analise "em sombra" existe para ser avaliada: gera-se, mede-se a sua
utilidade percebida, e so depois se decide se merece mais autonomia.

## 3. Linguagem ubiqua

- **Analise em sombra**: parecer estruturado de um modelo sobre um candidato, sem efeito de estado. Estados `RUNNING`, `COMPLETED`, `FAILED`.
- **Accao recomendada**: valor tipado que o modelo propoe para revisao humana; nunca executado por esta funcionalidade.
- **Feedback**: apreciacao do staff sobre a utilidade da analise — `USEFUL`, `PARTIALLY_USEFUL`, `NOT_USEFUL`.
- **Confianca advisory**: `LOW`, `MEDIUM`, `HIGH`; qualificador de leitura, nao criterio de decisao.

---

## 4. Requisitos funcionais

### RF-001 — Desativada por omissao

A funcionalidade exige configuracao explicita:

```dotenv
SCIENTIFIC_RETURN_LLM_ENABLED=true
SCIENTIFIC_RETURN_LLM_MODEL=llama3.1:8b
SCIENTIFIC_RETURN_LLM_TIMEOUT_SECONDS=60
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_API_KEY=<secret>
```

Com a bandeira desativada, o pedido responde `SCIENTIFIC_RETURN_LLM_DISABLED` e
**nenhuma chamada e feita ao fornecedor**.

### RF-002 — Gerar uma analise

`POST /api/v1/scientific-return/candidates/{candidateId}/agent-analyses`

Gera e persiste uma analise. Exige candidato existente e prompt publicado; sem
prompt ou sem raciocinador disponivel, responde
`SCIENTIFIC_RETURN_LLM_UNAVAILABLE`.

### RF-003 — Entrada minima e tipada

O modelo recebe apenas: o snapshot minimo do projeto, os metadados normalizados
do candidato, as evidencias verificadas e a trajetoria de consultas registada.

O texto da publicacao e tratado explicitamente como **dado nao confiavel**. Nada
nele altera regras, permissoes ou estados.

### RF-004 — Saida estruturada

O resultado separa: evidencia de suporte, contradicoes, evidencia em falta,
**uma** accao recomendada tipada, consultas propostas, um resumo do raciocinio e
a confianca advisory.

Restricoes de contrato:

- o resumo e o resumo do raciocinio sao obrigatorios;
- sao aceites no maximo 10 consultas propostas;
- campos fora do contrato e valores de enumeracao desconhecidos sao recusados.

### RF-005 — Persistencia para auditoria

Cada analise guarda: modelo utilizado, identificador e rotulo da versao do
prompt publicado, entrada e saida cifradas, hashes, latencia, mensagem de erro
quando aplicavel e o feedback do staff.

### RF-006 — Falha nao contamina o pipeline

Saida invalida, tempo esgotado ou falha do fornecedor produzem uma analise
`FAILED` persistida. O pipeline deterministico de candidatos nao e interrompido
nem alterado.

### RF-007 — Historico

`GET /api/v1/scientific-return/candidates/{candidateId}/agent-analyses` devolve
o historico de auditoria do candidato.

### RF-008 — Feedback uma unica vez

`POST /api/v1/scientific-return/agent-analyses/{analysisId}/feedback` regista
`USEFUL`, `PARTIALLY_USEFUL` ou `NOT_USEFUL`. Exige analise `COMPLETED` e so
pode ser registado uma vez por analise.

### RF-009 — Ausencia de efeitos

A analise em sombra **nunca**: invoca uma fonte bibliografica, altera o estado
do candidato, cria uma decisao ou escreve no `PublicationLog`. A accao proposta
e exibida para revisao; a sua execucao pertence ao ciclo agentic supervisionado
([SPEC-001](../001-investigacao-agentica-assistida/spec.md)) e exige politica
deterministica propria.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Com a bandeira desativada, nenhuma chamada chega ao fornecedor |
| INV-002 | A analise nunca contacta uma fonte bibliografica |
| INV-003 | A analise nunca altera o estado de um candidato |
| INV-004 | Uma analise falhada e persistida, nunca silenciada |
| INV-005 | Toda a analise identifica o modelo e a versao do prompt que a produziram |
| INV-006 | O feedback e irrepetivel por analise |
| INV-007 | Texto de publicacao e dado, nunca instrucao |

## 6. Criterios de aceitacao

### CA-001 — Analise auditada sem alterar o candidato
→ `test_scientific_return.py::test_shadow_analysis_is_audited_without_changing_candidate`

### CA-002 — Resposta invalida persiste como analise falhada
→ `test_scientific_return.py::test_invalid_llm_response_is_persisted_as_failed_analysis`

### CA-003 — Bandeira desativada impede a chamada
→ `test_scientific_return.py::test_shadow_analysis_feature_flag_prevents_llm_call`

### CA-004 — Feedback uma unica vez, sobre analise concluida
→ `test_scientific_return.py::test_curator_can_record_feedback_once_on_completed_analysis`

### CA-005 — O parser recusa campos fora do contrato
→ `test_scientific_return.py::test_llm_analysis_parser_rejects_fields_outside_the_contract`

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
