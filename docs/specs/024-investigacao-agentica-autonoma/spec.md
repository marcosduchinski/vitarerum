# SPEC-024 — Investigacao agentica autonoma (full-agentic)

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-024 |
| Estado | Implementado |
| Contexto delimitado | `app/scientific_return` |
| Modo de execucao | Assincrono, executado por trabalhador fora do pedido |
| Postura | Autonoma na descoberta, humana na decisao |
| Specs relacionadas | [SPEC-001](../001-investigacao-agentica-assistida/spec.md), [SPEC-002](../002-vigilancia-retorno-cientifico/spec.md), [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-025](../025-base-de-conhecimento-curatorial/spec.md) |
| Documentos relacionados | `docs/api_contracts/README.md` |
| Escrita a partir de | `app/scientific_return/application/full_agentic.py`, `presentation/routes.py`, `test/scientific_return/test_full_agentic_*.py`, `test_provenance_contract.py`, `test_sweep_fan_out.py` |

---

## 1. Problema

O ciclo assistido de [SPEC-001](../001-investigacao-agentica-assistida/spec.md)
corre dentro do pedido HTTP: alguem carrega, espera, ve o resultado. Isso limita
a investigacao ao que cabe num pedido e obriga uma pessoa a estar presente.

Uma varredura de retorno cientifico sobre todos os objetos de um projeto demora
mais do que um pedido pode durar e nao tem de ser vista a acontecer. Mas
executar fora do pedido levanta o que um pedido resolvia sozinho: quem autoriza,
o que impede duas execucoes sobre o mesmo alvo, o que acontece quando o
trabalhador morre a meio, e como se recusa comecar quando o sistema ja esta a
produzir mau resultado.

## 2. Objetivo

Executar investigacao de retorno cientifico de forma autonoma e retomavel, com
o mesmo limite epistemico do ciclo assistido — o agente **descobre e propoe**,
nunca decide — e com refusas tipadas antes de gastar seja o que for.

## 3. Atores

| Ator | Papel |
| --- | --- |
| `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION` | Iniciam e cancelam investigacoes |
| Restante staff | Leem estado, trajetoria e prontidao; nao iniciam nada |
| Agendador | Inicia investigacoes por cadencia, sem chamador humano |
| Trabalhador | Executa a investigacao enfileirada, sob concessao temporaria |
| Modelo de linguagem | Planeia consultas; nunca decide o candidato |

## 4. Linguagem ubiqua

- **Investigacao autonoma**: unidade de trabalho enfileirada sobre um alvo. Estados `QUEUED`, `RUNNING`, `CANCEL_REQUESTED`, `COMPLETED`, `FAILED`, `CANCELLED`; os tres ultimos sao terminais.
- **Alvo**: a combinacao de vigilancia, candidato e objeto consultado a que a investigacao se refere.
- **Concessao (lease)**: direito temporario de um trabalhador executar uma investigacao. Expira.
- **Recuperacao**: retoma de uma investigacao cuja concessao expirou, contabilizada e limitada.
- **Prontidao**: diagnostico por fonte, dizendo se esta operacional — sem revelar credenciais.
- **Disjuntor (circuit breaker)**: recusa de novas investigacoes quando a precisao historica cai abaixo do limiar.
- **Trajetoria**: sequencia persistida de eventos tipados do que a investigacao fez.

## 5. Escopo

### Dentro

- Enfileiramento, execucao retomavel e cancelamento de investigacoes.
- Refusas tipadas antes de gastar recursos.
- Leitura de estado, trajetoria e prontidao das fontes.
- Fan-out de uma vigilancia pelos objetos consultados do projeto.

### Fora

- A decisao curatorial sobre os candidatos produzidos ([SPEC-004](../004-decisao-candidato-publicacao/spec.md)).
- A cadencia que aciona as investigacoes ([SPEC-002](../002-vigilancia-retorno-cientifico/spec.md)).
- A memoria curatorial que informa o agente ([SPEC-025](../025-base-de-conhecimento-curatorial/spec.md)).

---

## 6. Requisitos funcionais

### RF-001 — Iniciar uma investigacao autonoma

`POST /scientific-return/watches/{watchId}/full-agentic-investigations` enfileira
uma investigacao e responde `202` com o seu estado inicial. Exige cabecalho
`Idempotency-Key` e um `objective`; aceita `candidateId` opcional.

Restrito a `CURATORIAL`, `COLLECTIONS_MANAGEMENT` e `DIRECTION`. A resposta e
`202` e nao `201` porque nada foi ainda investigado: so aceite.

### RF-002 — Refusas antes de gastar

Verificadas por esta ordem, todas antes de enfileirar:

| Situacao | Resposta |
| --- | --- |
| Chave de idempotencia reutilizada para outro alvo | `422` |
| Fluxo desligado por configuracao | `409` `FULL_AGENTIC_DISABLED` |
| Ja existe investigacao viva sobre o mesmo alvo | `409` `FULL_AGENTIC_ALREADY_RUNNING` |
| Precisao historica abaixo do limiar | `503` `FULL_AGENTIC_CIRCUIT_OPEN` |
| Fonte pedida sem configuracao operacional possivel | `503` `FULL_AGENTIC_SOURCE_CONFIGURATION_INVALID` |
| Vigilancia inexistente | `404` `SCIENTIFIC_RETURN_WATCH_NOT_FOUND` |
| `candidateId` que nao pertence a vigilancia | `422` |
| `objectId` que nao e objeto consultado do instantaneo | `422` |

Uma configuracao de fontes impossivel e recusada **antes** do enfileiramento, e
nao descoberta pelo trabalhador: uma investigacao que nunca poderia produzir
nada nao chega a existir.

### RF-003 — Idempotencia por alvo

A mesma chave sobre o mesmo alvo devolve a investigacao existente. A mesma chave
sobre outro alvo e recusada com `422`. A chave identifica o pedido, nao o
chamador.

### RF-004 — Exclusividade por alvo

Nao existe mais do que uma investigacao viva por alvo. Um alvo ja vivo nao
impede os restantes alvos da mesma vigilancia de arrancar.

### RF-005 — Disjuntor por precisao observada

Com pelo menos `circuit_min_decisions` decisoes humanas registadas, a precisao
e a fracao de candidatos confirmados sobre candidatos decididos. Abaixo do
limiar configurado, novas investigacoes sao recusadas com `503`.

O disjuntor conta **apenas** desfechos humanos de investigacoes autonomas: o
sinal de qualidade e a decisao curatorial, nao a auto-avaliacao do agente.

### RF-006 — Isolamento institucional

Uma vigilancia de outra instituicao e recusada. O objeto tem de pertencer ao
instantaneo da propria vigilancia, e uma investigacao ve apenas o seu objeto.

### RF-007 — Execucao retomavel

A execucao corre fora do pedido, sob concessao temporaria. Um trabalhador nao
toma a concessao viva de outro. Uma concessao expirada e recuperavel, e cada
recuperacao e contabilizada; esgotado o limite, a investigacao termina em vez de
recuperar para sempre.

Uma investigacao terminada nunca deixa a sua execucao de pesquisa em aberto.

### RF-008 — Cancelamento

`POST /scientific-return/full-agentic-investigations/{investigationId}/cancel`
marca `CANCEL_REQUESTED` e, quando o trabalho para, `CANCELLED`. Restrito aos
mesmos grupos de RF-001. Cancelar duas vezes e idempotente. Uma investigacao ja
terminal responde `422`.

### RF-009 — Leitura de estado e trajetoria

| Endpoint | Devolve |
| --- | --- |
| `GET /scientific-return/full-agentic-investigations/{investigationId}` | Estado, contagem de recuperacoes, limite de recuperacoes e expiracao da concessao |
| `GET /scientific-return/watches/{watchId}/full-agentic-investigations` | Investigacoes da vigilancia, `limit` entre 1 e 100 (por omissao 20) |
| `GET /scientific-return/full-agentic-investigations/{investigationId}/trajectory` | Eventos tipados por ordem de sequencia, com o instante |

Todas restritas a staff. A trajetoria e persistida passo a passo: uma falha a
meio deixa registo parcial legivel, nao nada.

### RF-010 — Prontidao das fontes

`GET /scientific-return/full-agentic-readiness` devolve, por fonte pedida, se
esta operacional. Restrito a staff. **Nunca** devolve credenciais nem parte
delas — uma fonte configurada e uma fonte com chave valida sao coisas
diferentes, e so a primeira e observavel aqui.

### RF-011 — Fan-out por objeto

Uma varredura de vigilancia gera uma investigacao por objeto consultado, cada
uma com a sua propria chave de idempotencia. Objetos acima do tecto configurado
sao **registados**, nao descartados em silencio.

### RF-012 — Execucao interna nao publica

`POST /scientific-return/internal/full-agentic/execute` e a porta do
trabalhador. Exige `X-Worker-Token` comparado em tempo constante e esta
**excluida do esquema OpenAPI**. Ao concluir com candidatos novos, notifica quem
criou a vigilancia; uma falha a notificar nao desfaz a investigacao.

---

## 7. Invariantes

- **INV-001**: uma investigacao terminal nao volta a mudar de estado.
- **INV-002**: no maximo uma investigacao viva por alvo.
- **INV-003**: uma chave de idempotencia pertence a um alvo unico.
- **INV-004**: cada chamada ao modelo e debitada e confirmada **antes** de comecar; uma morte subita deixa-a gasta, nunca por gastar.
- **INV-005**: esgotado o orcamento, o modelo nao e contactado.
- **INV-006**: nenhum modo de falha deixa uma investigacao viva indefinidamente.
- **INV-007**: a prontidao nunca expoe credenciais.
- **INV-008**: a decisao sobre um candidato e sempre humana; o agente propoe.

---

## 8. Criterios de aceitacao

### CA-001 — Configuracao impossivel recusada antes do enfileiramento
Dado uma fonte pedida sem configuracao operacional possivel
Quando uma investigacao e iniciada
Entao e recusada com `503` e nada e enfileirado
→ `test_full_agentic_flow.py::test_invalid_operational_source_configuration_fails_before_enqueue`, `test_provenance_contract.py::test_an_impossible_source_configuration_is_refused_before_enqueue`

### CA-002 — Chave de idempotencia presa ao alvo
Dado uma chave ja usada
Quando e reutilizada para outro alvo
Entao o pedido e recusado
→ `test_full_agentic_flow.py::test_idempotency_key_cannot_be_reused_for_another_target`

### CA-003 — Disjuntor conta so desfechos humanos
Dado historico de decisoes curatoriais sobre candidatos autonomos
Quando a precisao cai abaixo do limiar
Entao novas investigacoes sao recusadas, e apenas desfechos humanos entram no calculo
→ `test_full_agentic_flow.py::test_circuit_breaker_uses_only_full_agentic_human_outcomes`

### CA-004 — Concessao exclusiva e recuperacao limitada
Dado uma investigacao com concessao viva
Quando outro trabalhador tenta toma-la
Entao e recusado; e uma investigacao recuperada repetidamente acaba terminada
→ `test_full_agentic_flow.py::test_second_worker_cannot_take_a_live_lease`, `::test_a_repeatedly_recovered_investigation_is_terminated`, `::test_the_reaper_closes_only_investigations_past_their_age`

### CA-005 — Orcamento debitado antes da chamada
Dado uma chamada ao modelo prestes a comecar
Quando o processo morre a meio
Entao a chamada reservada fica gasta, e um orcamento esgotado nunca chega ao modelo
→ `test_full_agentic_flow.py::test_every_model_call_is_charged_and_committed_before_it_starts`, `::test_a_hard_death_leaves_the_reserved_call_spent`, `::test_an_exhausted_budget_never_reaches_the_model`

### CA-006 — Nenhuma investigacao fica viva para sempre
Dado qualquer modo de falha
Quando o tempo passa
Entao a investigacao termina e nao deixa a sua execucao de pesquisa aberta
→ `test_full_agentic_flow.py::test_no_failure_mode_keeps_an_investigation_alive_forever`, `::test_a_terminated_investigation_never_leaves_its_run_open`

### CA-007 — Cancelamento idempotente
Dado uma investigacao ja com cancelamento pedido
Quando o cancelamento e repetido
Entao o resultado e o mesmo
→ `test_full_agentic_flow.py::test_repeated_cancel_request_is_idempotent`

### CA-008 — Prontidao sem credenciais
Dado fontes configuradas e fontes pedidas mas nao operacionais
Quando a prontidao e lida
Entao reporta o estado de cada uma sem devolver credenciais
→ `test_provenance_contract.py::test_readiness_reports_operational_sources_without_credentials`, `::test_readiness_reports_a_source_that_is_requested_but_not_operational`

### CA-009 — Fan-out por objeto com tecto visivel
Dado um projeto com varios objetos consultados
Quando a vigilancia e varrida
Entao cada objeto gera a sua investigacao com chave propria, os objetos acima do tecto ficam registados e um objeto ja vivo nao trava os outros
→ `test_sweep_fan_out.py::test_one_investigation_per_object_with_a_key_of_its_own`, `::test_objects_beyond_the_ceiling_are_recorded_not_dropped`, `::test_one_object_already_live_does_not_stop_the_others`

### CA-010 — Isolamento por objeto e por instantaneo
Dado uma vigilancia com varios objetos
Quando uma investigacao corre
Entao ve apenas o seu objeto, e um objeto fora do instantaneo e recusado
→ `test_full_agentic_flow.py::test_an_investigation_sees_only_its_own_object`, `::test_an_object_outside_the_snapshot_is_refused`, `::test_two_objects_of_one_project_are_two_targets`, `::test_a_snapshot_narrowed_to_a_missing_object_is_refused`

### CA-011 — Trajetoria persistida e legivel
Dado uma investigacao executada
Quando a trajetoria e lida
Entao os eventos estao persistidos por sequencia, com a versao do prompt que correu
→ `test_full_agentic_flow.py::test_plan_events_record_the_prompt_version_that_ran`, `test_investigation_repository.py::test_the_whole_trajectory_survives_the_database`

### CA-012 — Provenencia do candidato preservada
Dado candidatos produzidos por investigacao autonoma
Quando a fila e a decisao sao lidas
Entao cada candidato expoe a sua provenencia e a decisao guarda o que o curador viu
→ `test_provenance_contract.py::test_the_queue_exposes_the_provenance_of_every_candidate`, `::test_the_decision_snapshot_keeps_what_the_curator_was_shown`

### CA-013 — Endpoint interno fora do contrato publico
Dado o esquema OpenAPI publicado
Quando e inspecionado
Entao a porta do trabalhador nao aparece, e as rotas operacionais aparecem
→ `test_api_contract.py::test_openapi_excludes_bench_and_keeps_operational_scientific_return`

---

## 9. Requisitos nao funcionais

- **Seguranca**: JWT + `X-Permission-Id` nas rotas publicas; a porta do trabalhador usa um segredo proprio comparado em tempo constante.
- **Custo**: orcamento por investigacao em iteracoes, consultas, resultados, candidatos e chamadas ao modelo; o disjuntor evita gastar num sistema a produzir mau resultado.
- **Isolamento transacional**: nenhuma transacao aberta enquanto um modelo ou uma fonte responde.
- **Auditabilidade**: trajetoria persistida passo a passo, com a versao de prompt de cada plano.
- **Arquitetura**: dominio e aplicacao livres de FastAPI e SQLAlchemy; contratos import-linter preservados.

## 10. Rastreabilidade

| Elemento da spec | Localizacao |
| --- | --- |
| Estados e agregado (INV-001) | `app/scientific_return/domain/enums.py`, `domain/full_agentic_models.py` |
| Arranque, refusas e disjuntor (RF-001..RF-006) | `app/scientific_return/application/full_agentic.py` (`StartFullAgenticScientificReturn`) |
| Concessao, recuperacao e ceifeira (RF-007) | `app/scientific_return/application/full_agentic.py` |
| Cancelamento e leituras (RF-008, RF-009) | `app/scientific_return/application/full_agentic.py` (`CancelFullAgenticInvestigation`, `GetFullAgenticInvestigation`) |
| Ancoragem de afirmacoes | `app/scientific_return/application/full_agentic_grounding.py` |
| Estrategia de pesquisa | `app/scientific_return/application/full_agentic_strategy.py` |
| Endpoints (RF-001, RF-008..RF-012) | `app/scientific_return/presentation/routes.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 11. Questoes em aberto

1. O limiar do disjuntor e por instituicao ou global? Hoje a metrica e agregada.
2. Uma investigacao terminada em `FAILED` por esgotamento de recuperacoes deve reentrar na fila por decisao humana, ou exigir novo pedido?
3. O tecto de objetos por varredura devia ser por projeto ou por instituicao?
