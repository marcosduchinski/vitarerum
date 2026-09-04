# SPEC-002 — Vigilancia de retorno cientifico e cadencia de revisao

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-002 |
| Estado | Implementado |
| Contexto delimitado | `app/scientific_return` |
| Escrita a partir de | `app/scientific_return/domain/models.py`, `application/use_cases.py`, `presentation/routes.py`, `test/scientific_return/test_scientific_return.py` |
| Specs relacionadas | [SPEC-003](../003-pipeline-deterministico-bibliografico/spec.md), [SPEC-004](../004-decisao-candidato-publicacao/spec.md) |

## 1. Problema

Um projeto de acesso a colecoes termina, o investigador publica meses ou anos
depois, e o museu nao sabe. O retorno cientifico do acervo fica por registar
porque ninguem tem mandato nem cadencia para o procurar.

## 2. Objetivo

Permitir que o staff ative uma **vigilancia** sobre um projeto concluido, com
uma cadencia de revisao explicita, ancorada num **snapshot imutavel** do projeto
no momento da ativacao.

## 3. Atores

| Ator | Papel |
| --- | --- |
| `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION` | Ativam, pausam, fecham e re-cadenciam vigilancias |
| `SYS_ADMIN` | Leitura diagnostica e metricas; sem accao curatorial |
| Cloud Scheduler / Cloud Run job | Percorre as vigilancias vencidas |

## 4. Linguagem ubiqua

- **Vigilancia (`watch`)**: compromisso de procurar periodicamente publicacoes decorrentes de um projeto concluido. Estados `ACTIVE`, `PAUSED`, `CLOSED`.
- **Snapshot de projeto**: copia imutavel de investigador, referencia do projeto e objetos consultados, com hash do conteudo e versao do construtor.
- **Cadencia (`reviewIntervalDays`)**: quanto tempo decorre entre uma pesquisa e a seguinte.
- **Vencimento (`nextRunAt`)**: instante a partir do qual a vigilancia esta em divida de revisao.
- **Varrimento**: passagem periodica que executa as vigilancias vencidas.

## 5. Escopo

**Dentro:** ativacao, leitura, mudanca de estado, re-cadencia, vencimento,
varrimento agendado, metricas operacionais.

**Fora:** o que a pesquisa faz com as fontes (SPEC-003) e o que acontece aos
candidatos (SPEC-004).

---

## 6. Requisitos funcionais

### RF-001 — Ativar vigilancia

`POST /api/v1/scientific-return/projects/{projectId}/watch`

```json
{ "reviewIntervalDays": 90 }
```

Responde `201` com a vigilancia. Pre-condicoes cumulativas:

1. o projeto existe e esta `COMPLETED`;
2. o nome do investigador esta resolvido e nao vazio;
3. o projeto tem pelo menos um objeto consultado;
4. cada objeto consultado tem numero de inventario e nome de objeto.

Qualquer pre-condicao em falta impede a ativacao. A justificacao e material: uma
vigilancia sem esses dados nao consegue formular uma unica consulta util.

### RF-002 — Ativacao idempotente

Repetir o pedido para um projeto ja vigiado devolve a vigilancia existente, sem
criar segundo snapshot e sem alterar a cadencia em vigor.

### RF-003 — Snapshot imutavel

A ativacao cria um snapshot com o conteudo do projeto, um hash do payload e a
versao do construtor. O snapshot nunca e reescrito: se o projeto mudar depois, a
vigilancia continua a procurar o que foi efetivamente consultado.

O snapshot e cifrado em repouso com a chave de cifragem de campo da aplicacao,
protegendo a associacao entre investigador, projeto e objetos consultados.

### RF-004 — Vencimento inicial

Uma vigilancia recem-ativada vence de imediato (`nextRunAt` = instante da
ativacao). A primeira revisao nao espera um intervalo.

### RF-005 — Ler a vigilancia de um projeto

`GET /api/v1/scientific-return/projects/{projectId}/watch`

### RF-006 — Alterar estado e cadencia

`PATCH /api/v1/scientific-return/watches/{watchId}` aceita `status`,
`reviewIntervalDays` ou ambos. Um corpo sem nenhum dos dois responde `422`.

### RF-007 — Intervalo valido

`reviewIntervalDays` situa-se entre 1 e 365, tanto na ativacao como na
re-cadencia. Fora do intervalo, o pedido e recusado.

### RF-008 — Re-cadencia ancorada na data escolhida

As revisoes assentam numa **grelha fixa** medida a partir de
`scheduleAnchorAt`, a data que o curador escolheu na ativacao: o proximo
vencimento e o primeiro ponto da grelha estritamente posterior ao momento atual,
`ancora + n x intervalo`.

Mudar a cadencia re-deriva a grelha **a partir da mesma ancora**, nunca a partir
de agora. Consequencias deliberadas:

- encurtar a cadencia pode tornar a vigilancia vencida imediatamente;
- alargar a cadencia nao concede um periodo completo novo;
- uma vigilancia que nunca correu permanece vencida na sua data de ativacao.

Re-cadenciar nao e uma forma de adiar uma revisao ja em divida.

A ancora e o que faz "de 90 em 90 dias a partir de 1 de marco" continuar a
significar isso mesmo quando uma execucao arranca com atraso.

### RF-009 — Fecho irreversivel

Uma vigilancia `CLOSED` nao pode ser reaberta nem re-cadenciada. `ACTIVE` e
`PAUSED` alternam livremente.

### RF-010 — Registo de execucao

Concluida uma pesquisa, a vigilancia regista `lastRunAt` e o proximo vencimento
passa a ser o ponto seguinte da grelha da ancora — **nao** `lastRunAt +
intervalo`. Uma execucao atrasada nao empurra a serie para a frente; uma
interrupcao longa retoma no primeiro ponto futuro da grelha, sem tentar
recuperar as revisoes perdidas uma a uma.

### RF-011 — Varrimento agendado

```bash
uv run python -m app.jobs.scientific_return run-due --limit 25
```

O comando executa apenas vigilancias vencidas e `ACTIVE`. Toma um *advisory
lock* transacional do PostgreSQL por vigilancia, impedindo execucao concorrente
da mesma vigilancia por dois varrimentos. Emite notificacao de projeto **apenas**
quando a execucao cria candidatos novos.

O ponto de entrada e `app.jobs.scientific_return`, nao o modulo de comandos do
contexto: o registo dos mapeadores ORM pertence a raiz de composicao, porque a
chave estrangeira do candidato para `use_of_collections` nao resolve de outra
forma.

### RF-012 — Duas cadencias distintas

A cadencia do agendador decide com que frequencia o sistema **olha**; a cadencia
da vigilancia decide se ela esta **vencida** quando o varrimento chega. Um
varrimento diario sobre vigilancias de 90 dias nao contacta nenhuma fonte em 89
de cada 90 dias.

### RF-013 — Metricas operacionais

`GET /api/v1/scientific-return/metrics` devolve vigilancias ativas, total de
execucoes, execucoes falhadas e contagens de candidatos pendentes, confirmados e
descartados.

### RF-014 — Consulta em lote por projeto

`POST /api/v1/scientific-return/watches/lookup` recebe uma lista de
`projectIds` e devolve, para cada um: a vigilancia existente quando ha,
`eligible`, e `ineligibilityReason` quando o projeto nao pode ser vigiado.
Identificadores repetidos sao respondidos uma vez. Restrito a staff.

Existe para que uma listagem de projetos mostre o estado de vigilancia sem uma
chamada por projeto. Um projeto sem vigilancia **nao** e omitido da resposta:
vem com `watch` nulo e a razao pela qual nao e elegivel — a ausencia de
vigilancia e informacao, nao falta de resultado.

`GET /api/v1/scientific-return/projects/{projectId}/watch` responde a mesma
pergunta para um projeto so.

---

## 7. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | O snapshot de um projeto vigiado nunca e reescrito |
| INV-002 | Uma vigilancia fechada nunca volta a estar ativa |
| INV-003 | `reviewIntervalDays` permanece sempre em 1..365 |
| INV-004 | Re-cadenciar nunca adia uma revisao ja vencida |
| INV-005 | O snapshot e o texto exato das consultas estao cifrados em repouso |
| INV-006 | Duas execucoes da mesma vigilancia nunca correm em simultaneo |

## 8. Criterios de aceitacao

### CA-001 — Nova cadencia re-derivada da ancora, nao de agora
Dado uma vigilancia que ja pesquisou
Quando a cadencia e alterada
Entao a ancora mantem-se e o proximo vencimento e `ancora + novo intervalo`; uma vigilancia que nunca correu continua vencida
→ `test_scientific_return.py::test_a_new_interval_is_re_derived_from_the_anchor_not_from_now`, `::test_a_new_interval_leaves_a_never_run_watch_due`

### CA-002 — A grelha nao escorrega com atrasos
Dado uma vigilancia cuja execucao arranca depois da hora
Quando a execucao e registada
Entao a serie continua medida a partir da ancora, e uma interrupcao longa retoma no primeiro ponto futuro
→ `test_scientific_return.py::test_a_late_search_does_not_push_the_series_later`, `::test_a_long_outage_resumes_at_the_next_future_slot`, `::test_a_future_anchor_postpones_the_first_review`

### CA-003 — Vigilancia nunca executada permanece vencida
Dado uma vigilancia sem execucoes
Quando a cadencia e alargada
Entao continua vencida na data de ativacao
→ `test_scientific_return.py::test_a_new_interval_leaves_a_never_run_watch_due`

### CA-004 — Fecho irreversivel
Dado uma vigilancia `CLOSED`
Quando se tenta re-cadencia-la
Entao o pedido e recusado
→ `test_scientific_return.py::test_a_closed_watch_cannot_be_rescheduled`

### CA-005 — Intervalo fora do dominio
Dado um intervalo de 0 ou 366 dias
Quando a cadencia e definida
Entao o pedido e recusado
→ `test_scientific_return.py::test_an_interval_outside_the_allowed_range_is_refused`

### CA-006 — Consulta em lote publicada no contrato
Dado o esquema OpenAPI publicado
Quando e inspecionado
Entao a consulta em lote de vigilancias aparece entre as rotas operacionais
→ `test_api_contract.py::test_openapi_excludes_bench_and_keeps_operational_scientific_return`

## 9. Requisitos nao funcionais

- **Seguranca**: JWT + `X-Permission-Id`; mutacoes restritas aos tres grupos curatoriais.
- **Concorrencia**: lock por vigilancia no varrimento (RF-011).
- **Confidencialidade**: cifragem de campo no snapshot e nas consultas (RF-003).
- **Custo**: o varrimento so contacta fontes para vigilancias vencidas (RF-012).

## 10. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Agregado da vigilancia (RF-007..RF-010) | `app/scientific_return/domain/models.py` |
| Ativacao e re-cadencia (RF-001..RF-008) | `app/scientific_return/application/use_cases.py` |
| Endpoints (RF-001, RF-005, RF-006, RF-013) | `app/scientific_return/presentation/routes.py` |
| Varrimento agendado (RF-011) | `app/jobs/scientific_return.py`, `app/scientific_return/presentation/commands.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 11. Questoes em aberto

1. Deve existir fecho automatico de vigilancias sem candidatos ao fim de N anos?
2. A cadencia devia variar com o perfil do projeto (ex.: taxonomia descritiva versus emprestimo pontual)?
