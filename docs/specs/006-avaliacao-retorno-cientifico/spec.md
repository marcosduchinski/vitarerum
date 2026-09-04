# SPEC-006 — Avaliacao reprodutivel do retorno cientifico

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-006 |
| Estado | Implementado |
| Contexto delimitado | `app/scientific_return` |
| Escrita a partir de | `application/evaluation.py`, `application/agentic_evaluation.py`, `presentation/commands.py`, `test/scientific_return/test_evaluation_fixture.py`, `test_agentic_evaluation.py` |
| Specs relacionadas | [SPEC-003](../003-pipeline-deterministico-bibliografico/spec.md), [SPEC-001](../001-investigacao-agentica-assistida/spec.md) |

## 1. Problema

Uma funcionalidade que procura publicacoes so pode crescer em autonomia se
alguem souber, com numeros, o que ela ja acerta e o que lhe escapa. Sem medicao,
"o agente ajuda" e opiniao, e qualquer promocao de autonomia e um ato de fe.

Ha ainda um risco especifico: uma fixture cujas declaracoes divergem da
realidade e pior do que nenhuma fixture, porque os criterios de promocao leem
essas declaracoes.

## 2. Objetivo

Medir, de forma reproduzivel e sem escrever na base de dados, o que o pipeline
deterministico e o ciclo agentic conseguem sobre um conjunto versionado de
publicacoes reais do MUHNAC cujo resultado esperado e conhecido.

## 3. Linguagem ubiqua

- **Caso**: publicacao conhecida, com autor, numero de inventario, objeto, titulo e DOI esperados.
- **Fixture**: conjunto versionado de casos, mais as publicacoes ainda nao exprimiveis como caso.
- **Estado de baseline**: `RESOLVED`, `GAP` ou `UNVERIFIED`.
- **Lacuna esperada (`expectedGap`)**: causa declarada pela qual a baseline falha o caso.
- **Alvo agentic**: `DISCOVER_CANDIDATE` ou `ENRICH_CANDIDATE`, **derivado** da medicao, nunca declarado.
- **Fila de revisao**: candidatos do relatorio que aguardam decisao humana para calcular precisao.

---

## 4. Requisitos funcionais

### RF-001 — Executar a baseline deterministica

```bash
uv run python -m app.jobs.scientific_return evaluate-phase0 \
  --sources all --result-limit 20 --output relatorio.json
```

`--sources` aceita `crossref`, `openalex`, `europe_pmc` ou `all` (omissao).
`all` ignora OpenAlex com aviso quando a chave nao esta configurada. Sem
`--output`, o relatorio JSON e escrito no `stdout`.

### RF-002 — Avaliacao sem efeitos colaterais

A avaliacao nao cria vigilancias, candidatos nem decisoes. Constroi o snapshot
de cada caso em memoria e usa as mesmas funcoes de planeamento, evidencia e
acionabilidade do pipeline em producao.

### RF-003 — Criterio estrito de recuperacao

Um caso so conta como `RESOLVED` quando a publicacao esperada **chega a fila
humana**, isto e, passa o criterio de acionabilidade. Aparecer numa lista de
resultados sem produzir evidencia acionavel conta como nao encontrada: para
efeitos de retorno cientifico, ninguem a veria.

### RF-004 — Metricas por fonte

Para cada fonte: numero de casos, recuperados, *recall*, candidatos acionaveis,
correspondencias acionaveis conhecidas, *proxy* de precisao sobre casos
conhecidos, consultas emitidas e erros.

### RF-005 — Verificacao das declaracoes da fixture

O relatorio compara o que a fixture declara com o que a execucao observou e
publica: contagens declaradas e observadas, `mismatched_case_ids`,
`unverified_case_ids`, alvos de descoberta, alvos de enriquecimento e casos de
lacuna por formato de inventario.

Divergencias sao reportadas caso a caso, para a fixture ser corrigida **antes**
de qualquer criterio de promocao ser avaliado.

### RF-006 — Derivacao do alvo agentic

O alvo agentic de um caso e derivado da baseline medida, nunca declarado: um
caso que a baseline nunca transforma em candidato revisivel e alvo de
descoberta; um que chega a fila sem evidencia de inventario e alvo de
enriquecimento. Assim, a classificacao nao envelhece.

### RF-007 — Integridade da fixture

A fixture recusa: identificadores duplicados, estados de baseline nao
suportados, ficheiro vazio e campos obrigatorios em falta. Alem disso:

- um caso totalmente resolvido nao pode declarar lacuna;
- um caso resolvido sem evidencia de inventario **pode** declarar lacuna;
- um caso de lacuna tem de declarar a sua causa;
- um caso `UNVERIFIED` nao pode reclamar uma medicao.

### RF-008 — Alcancabilidade declarada das lacunas

As formas de inventario citadas nas publicacoes de lacuna tem de ser alcancaveis
pelo gerador de variantes ([SPEC-001](../001-investigacao-agentica-assistida/spec.md),
RF-009) e dentro do orcamento de consultas configurado. Uma lacuna que o
incremento nao consegue sequer tentar fechar e declarada como tal, nao
silenciada.

### RF-009 — Publicacoes ainda nao mapeadas

Publicacoes do corpus que ainda nao sao exprimiveis como caso — tipicamente
porque falta o numero de inventario do lado do museu — ficam listadas com a sua
razao. A fixture nao finge cobertura total.

### RF-010 — Metricas humanas em segunda passagem

O relatorio inclui uma fila de revisao. Depois de o staff preencher os campos de
decisao humana:

```bash
uv run python -m app.jobs.scientific_return evaluate-phase0 --reviews relatorio.json
```

calcula cobertura de revisao e precisao humana **sem repetir** qualquer pesquisa
externa. Uma revisao exige fuso horario explicito na data.

### RF-011 — Avaliacao do ciclo agentic

```bash
uv run python -m app.jobs.scientific_return evaluate-agentic \
  --mode SUPERVISED --sources europe_pmc --output relatorio-agentic.json
```

Mede o ciclo agentic sobre a mesma fixture, sem persistir. `--mode` aceita
`SHADOW`, `POLICY_ONLY` e `SUPERVISED`. O orcamento e a allowlist vem da
configuracao do servidor, nao de argumentos.

### RF-012 — Criterio de fecho de lacuna

Uma lacuna so conta como fechada quando o caso se torna **acionavel**. Um
registo recuperado mas sem correspondencia nao fecha lacuna nenhuma.

### RF-013 — Falhas contadas, nao fatais

Um plano invalido ou uma reflexao indisponivel sao contabilizados no relatorio e
nao interrompem a avaliacao. O relatorio regista tambem a accao planeada por
cada caso, para auditoria.

### RF-014 — Proveniencia do relatorio

O relatorio regista com que configuracao foi produzido — modo, fontes, orcamento
— para que dois relatorios possam ser comparados sem ambiguidade.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | A avaliacao nunca escreve no dominio de producao |
| INV-002 | A avaliacao usa as mesmas regras de evidencia do pipeline real |
| INV-003 | Um caso nao verificado nunca reclama uma medicao |
| INV-004 | O alvo agentic e derivado da medicao, nunca declarado |
| INV-005 | Divergencias entre fixture e realidade sao publicadas, nao corrigidas em silencio |
| INV-006 | Recuperar sem ser acionavel nunca conta como sucesso |

## 6. Criterios de aceitacao

### CA-001 — A fixture publicada carrega e preserva os casos originais
→ `test_evaluation_fixture.py::test_the_shipped_fixture_loads`, `::test_the_original_cases_survive_the_extraction`

### CA-002 — Separacao entre alvos de descoberta e de enriquecimento
→ `test_evaluation_fixture.py::test_the_fixture_separates_discovery_targets_from_enrichment_targets`

### CA-003 — Integridade e coerencia das declaracoes
→ `test_evaluation_fixture.py::test_a_fully_resolved_case_may_not_declare_a_gap`, `::test_a_resolved_case_without_inventory_evidence_may_declare_a_gap`, `::test_a_gap_case_must_state_its_cause`, `::test_an_unverified_case_may_not_claim_a_measurement`, `::test_duplicated_case_ids_are_rejected`, `::test_an_unsupported_status_is_rejected`, `::test_an_empty_fixture_is_rejected`, `::test_a_missing_field_is_rejected`

### CA-004 — Lacunas alcancaveis pelo gerador e pelo orcamento
→ `test_evaluation_fixture.py::test_declared_inventory_gaps_are_reachable_by_the_variant_generator`, `::test_declared_gaps_are_reachable_within_the_configured_query_budget`, `::test_the_recorded_form_alone_does_not_close_a_declared_gap`

### CA-005 — Publicacoes nao mapeadas documentadas
→ `test_evaluation_fixture.py::test_unmapped_papers_are_documented`

### CA-006 — Metricas por fonte e fila de revisao
→ `test_scientific_return.py::test_evaluation_reports_per_source_metrics_and_review_queue`, `::test_phase_zero_review_requires_a_timezone`

### CA-007 — Modos do ciclo na avaliacao
→ `test_agentic_evaluation.py::test_shadow_mode_asks_the_model_and_executes_nothing`, `::test_policy_only_decides_but_still_executes_nothing`, `::test_supervised_mode_executes_the_authorised_action`

### CA-008 — Criterio de fecho de lacuna
→ `test_agentic_evaluation.py::test_a_gap_counts_as_closed_only_when_the_case_becomes_actionable`, `::test_a_retrieved_but_unmatched_record_does_not_close_the_gap`

### CA-009 — Falhas contadas e proveniencia registada
→ `test_agentic_evaluation.py::test_an_invalid_plan_is_counted_not_fatal`, `::test_an_unavailable_reflection_is_counted_not_fatal`, `::test_the_report_records_what_it_was_run_with`, `::test_the_plan_action_is_reported_for_auditing`

### CA-010 — O ciclo parte do que o pipeline ja tentou
→ `test_agentic_evaluation.py::test_the_cycle_starts_from_what_the_pipeline_already_tried`

## 7. Requisitos nao funcionais

- **Reprodutibilidade**: o relatorio e determinista dadas as mesmas fontes e a mesma fixture versionada em `application/fixtures/evaluation_cases.json`; as baselines publicadas em [`docs/evaluation/`](../../evaluation/) sao reexecutaveis.
- **Honestidade metodologica**: uma fonte nao exercitada e registada como tal, nunca como zero.
- **Custo**: a avaliacao contacta fontes reais; e um ato deliberado de linha de comando, nunca automatico.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Casos, fixture e integridade (RF-007..RF-009) | `app/scientific_return/application/evaluation.py`, `application/fixtures/evaluation_cases.json` |
| Execucao e metricas (RF-002..RF-006, RF-010) | `app/scientific_return/application/evaluation.py` |
| Avaliacao agentic (RF-011..RF-014) | `app/scientific_return/application/agentic_evaluation.py` |
| Linha de comando (RF-001, RF-010, RF-011) | `app/scientific_return/presentation/commands.py`, `app/jobs/scientific_return.py` |
| Baselines publicadas | [`docs/evaluation/`](../../evaluation/) |

## 9. Questoes em aberto

1. Qual o limiar de precisao humana que autoriza promover o ciclo de `SUPERVISED` para `SCHEDULED`?
2. A fixture deve crescer com casos negativos explicitos (publicacoes do mesmo autor sem relacao com o especime)?
3. Como incorporar o custo por candidato confirmado — consultas e latencia de modelo — nas metricas de promocao?
