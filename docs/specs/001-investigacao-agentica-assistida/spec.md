# SPEC-001 — Investigacao agentica assistida (retorno cientifico)

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-001 |
| Estado | Implementado (E1) |
| Contexto delimitado | `app/scientific_return` |
| Incremento de origem | E1 do plano evolutivo |
| Modo de execucao | Sincrono, acionado manualmente |
| Postura | Advisory / human-in-the-loop |
| Documentos relacionados | `docs/api_contracts/README.md` |
| Escrita a partir de | Codigo em `app/scientific_return`, testes em `test/scientific_return`, commit `b63b68b` |

Esta especificacao descreve **comportamento observavel e regras**, nao desenho de
implementacao. Nomes de ficheiros aparecem apenas na seccao de rastreabilidade.

---

## 1. Problema

A vigilancia deterministica de retorno cientifico consulta fontes bibliograficas
com combinacoes fixas de autor, numero de inventario e nome de objeto. Quando
essas combinacoes nao produzem candidato acionavel, o processo termina sem
resposta e sem registo do porque. Duas lacunas ficam por cobrir:

1. publicacoes que citam o especime numa variante de inventario que o plano
   deterministico nao gera (`MUHNAC/MB11-001283` vs `MB11-001283`);
2. candidatos pendentes cuja evidencia e fraca e que ninguem consegue reforcar
   sem repetir manualmente pesquisas ja feitas.

## 2. Objetivo

Permitir que um membro do staff acione um **ciclo agentic limitado** sobre uma
vigilancia — opcionalmente sobre um candidato — que observe o estado, proponha
uma accao, a valide contra uma politica deterministica, a execute dentro de um
orcamento fixo, reavalie a evidencia pelas mesmas regras do pipeline
deterministico e termine com uma razao tipada.

**Nao objetivo:** transferir para o modelo qualquer decisao curatorial.

## 3. Atores

| Ator | Papel |
| --- | --- |
| Staff curatorial (`CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION`) | Aciona a investigacao e decide os candidatos resultantes |
| `SYS_ADMIN` | Leitura diagnostica; sem accao curatorial |
| Modelo de linguagem | Propoe **uma** accao tipada e, no maximo, o objeto consultado a que se refere |
| Politica de accao | Autoriza ou recusa a accao e deriva o que sera efetivamente executado |
| Politica de paragem | Determina o fim do ciclo e a razao tipada |
| Fontes bibliograficas | Europe PMC, Crossref, OpenAlex (sujeitas a allowlist e a roteamento) |

## 4. Linguagem ubiqua

- **Investigacao**: ciclo agentic delimitado sobre uma vigilancia e, opcionalmente, um candidato. Agregado com maquina de estados propria.
- **Iteracao**: uma passagem por observar -> planear -> validar -> agir -> reavaliar -> refletir.
- **Objetivo**: `DISCOVER_CANDIDATE` (descoberta) ou `ENRICH_CANDIDATE` (enriquecimento).
- **Orcamento de execucao**: limites de iteracoes, accoes, consultas, resultados por consulta e candidatos criados.
- **Delta de evidencia**: diferenca entre a evidencia antes e depois da execucao, com hash de ambos os estados.
- **Razao de paragem**: valor tipado que explica o fim do ciclo.
- **Modo**: `DISABLED`, `SHADOW`, `POLICY_ONLY`, `SUPERVISED`, `SCHEDULED`.

## 5. Escopo

### Dentro

- Investigacao de descoberta a partir de uma vigilancia.
- Investigacao de enriquecimento a partir de um candidato `PENDING`.
- Uma accao executavel: `SEARCH_INVENTORY_VARIANTS`.
- Duas accoes terminais sem contacto externo: `PRESENT_FOR_REVIEW`, `STOP_INSUFFICIENT_EVIDENCE`.
- Persistencia integral da trajetoria e leitura posterior.
- Idempotencia por chave do cliente.

### Fora

- Execucao assincrona, dispatcher, heartbeat e concorrencia otimista (E3/E4).
- Multiplas iteracoes por investigacao (o agregado ja permite; a configuracao nao).
- Accoes `SEARCH_AUTHOR_VARIANTS`, `SEARCH_TAXON_VARIANTS`, `SEARCH_FULL_TEXT`, `DEPRIORITIZE`.
- Qualquer alteracao automatica de titulo, autores, DOI, URL ou estado de candidato.

---

## 6. Requisitos funcionais

### RF-001 — Iniciar investigacao de descoberta

`POST /api/v1/scientific-return/watches/{watchId}/investigations`

Cria uma investigacao com objetivo `DISCOVER_CANDIDATE`, sem candidato
associado. Responde `201` com a trajetoria completa e ja terminal.

Pre-condicoes: a vigilancia existe, esta `ACTIVE`, tem snapshot de projeto e ja
teve pelo menos uma execucao deterministica.

### RF-002 — Iniciar investigacao de enriquecimento

`POST /api/v1/scientific-return/candidates/{candidateId}/investigations`

Cria uma investigacao com objetivo `ENRICH_CANDIDATE` sobre um candidato
`PENDING`. Um candidato `CONFIRMED` ou `DISMISSED` e recusado.

### RF-003 — Idempotencia por chave do cliente

O cabecalho `Idempotency-Key` e opcional. Com a mesma chave, o pedido devolve a
investigacao que essa chave ja produziu, sem contactar nenhuma fonte e sem criar
novo candidato. Sem chave, cada pedido inicia nova investigacao.

### RF-004 — Exclusividade por alvo

Enquanto existir investigacao nao terminal para a mesma combinacao de
vigilancia, objetivo e candidato, um novo pedido responde `409`
(`SCIENTIFIC_RETURN_INVESTIGATION_RUNNING`). O alvo do bloqueio de descoberta e
distinto do de enriquecimento.

### RF-005 — Observacao

A iteracao apresenta ao modelo apenas: investigador, referencia do projeto,
objetos consultados (id, numero de inventario, nome), consultas ja tentadas e a
lista de accoes permitidas. Nao inclui credenciais, endpoints, chaves de API nem
dados de outros projetos.

### RF-006 — Plano do modelo

O modelo devolve exatamente um plano estruturado: objetivo da iteracao, tipo de
accao, `objectId` opcional, resumo do raciocinio e evidencia esperada. Campos
excedidos em tamanho ou listas excedidas em comprimento sao recusados. Um plano
malformado encerra a investigacao com `INVALID_PLAN`.

### RF-007 — Validacao deterministica da accao

A politica de accao autoriza ou recusa, e quando autoriza **deriva** as
consultas, as fontes e o limite de resultados. O modelo nunca fornece nenhum
desses valores. Recusas produzidas:

| Situacao | Motivo de recusa |
| --- | --- |
| Investigacao fora de `VALIDATING` | `INVESTIGATION_NOT_ACTIONABLE` |
| Candidato ja decidido durante o ciclo | `CANDIDATE_ALREADY_DECIDED` |
| Accao fora da allowlist configurada | `ACTION_NOT_ALLOWED` |
| Accao sem executor neste incremento | `ACTION_NOT_ALLOWED` |
| Modo que nao executa ferramentas | `MODE_FORBIDS_EXECUTION` |
| Orcamento esgotado | `BUDGET_EXHAUSTED` / `CANDIDATE_LIMIT_REACHED` |
| Accao de pesquisa sem `objectId` | `OBJECT_ID_REQUIRED` |
| `objectId` ausente do snapshot | `OBJECT_NOT_IN_SNAPSHOT` |
| Objeto sem numero de inventario | `INVENTORY_MISSING` |
| Nenhuma fonte capaz de correspondencia exata | `SOURCE_NOT_ALLOWED` |
| Todas as variantes ja consultadas | `NO_NEW_QUERY_VARIANT` |

### RF-008 — Roteamento por capacidade de correspondencia exata

Apenas fontes que honram uma frase exata recebem uma consulta de inventario.
Neste incremento, apenas Europe PMC. A ordem de prioridade e Europe PMC,
Crossref, OpenAlex. Crossref esta excluida por medicao: devolve resultados
ordenados por relevancia mesmo para codigos inexistentes.

### RF-009 — Geracao de variantes de inventario

As consultas derivam do numero de inventario registado no snapshot, por
variantes tipadas (`EXACT`, `WITHOUT_INSTITUTION`, `NUMBER_PADDING`,
`INSTITUTION_ALIAS`, `SEPARATOR`), excluindo as ja tentadas e limitadas pelo
orcamento restante de consultas.

### RF-010 — Reavaliacao de evidencia

A evidencia dos resultados e recalculada pelas mesmas regras deterministicas do
pipeline agendado. A iteracao regista o hash da evidencia antes e depois e o
delta (`added`, `preserved`, `removed`).

### RF-011 — Reflexao

Apos a execucao, o modelo produz progresso, resumo do delta, lacunas restantes,
recomendacao de paragem e resumo do raciocinio. A recomendacao e conselho: a
paragem e sempre decidida pela politica. Se a reflexao falhar, a iteracao
retrocede para uma reflexao derivada do delta.

### RF-012 — Encerramento com razao tipada

Toda a investigacao terminal tem uma razao de paragem. `EVIDENCE_SUFFICIENT` e
a unica razao de caminho feliz; as restantes registam porque o ciclo terminou
sem acrescentar nada e nenhuma bloqueia a fila de revisao humana.

Razoes: `EVIDENCE_SUFFICIENT`, `NO_RESULTS`, `NO_EVIDENCE_ADDED`, `NO_PROGRESS`,
`ACTION_REJECTED`, `QUERY_REPEATED`, `BUDGET_EXHAUSTED`,
`ITERATION_LIMIT_REACHED`, `CANDIDATE_LIMIT_REACHED`, `REASONER_UNAVAILABLE`,
`INVALID_PLAN`, `TOOL_UNAVAILABLE`, `TOOL_FAILED`, `CANDIDATE_ALREADY_DECIDED`,
`PRESENTED_FOR_REVIEW`, `INSUFFICIENT_EVIDENCE`.

### RF-013 — Telemetria por iteracao

Cada iteracao regista o modelo, a versao do prompt publicado e as latencias de
plano, reflexao e total. Investigacoes anteriores a existencia da telemetria, ou
que nunca alcancaram o modelo, apresentam `telemetry: null`.

### RF-014 — Leitura da trajetoria

`GET /watches/{watchId}/investigations`, `GET /candidates/{candidateId}/investigations`
e `GET /investigations/{investigationId}` sao estritamente de leitura. Nunca
continuam, repetem ou reiniciam um ciclo.

### RF-015 — Controlo por modo de operacao

`SUPERVISED` executa ferramentas. `SHADOW` e `POLICY_ONLY` param antes da
execucao. `DISABLED` recusa o pedido com `503`
(`SCIENTIFIC_RETURN_AGENT_DISABLED`). O valor por omissao e `DISABLED`.

---

## 7. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | O ciclo nunca escreve no `PublicationLog` do projeto |
| INV-002 | O ciclo nunca confirma, descarta nem adia um candidato |
| INV-003 | O enriquecimento nunca altera titulo, autores, DOI, URL ou estado do candidato |
| INV-004 | Toda a consulta enviada deriva de dados do snapshot imutavel do projeto |
| INV-005 | Nenhum texto de publicacao pode alterar as regras de evidencia — texto externo e dado, nao instrucao |
| INV-006 | Uma investigacao terminal nao reabre; repetir e criar nova investigacao ligada a anterior |
| INV-007 | Um resultado de ferramenta so pode ser registado se a execucao foi autorizada |
| INV-008 | O orcamento e debitado antes da execucao, nunca depois |
| INV-009 | Toda a investigacao terminal tem razao de paragem |
| INV-010 | Uma accao recusada produz reflexao e razao de paragem, tal como uma execucao |
| INV-011 | Falhas registam identificadores, nunca conteudo de projeto ou de publicacao |
| INV-012 | O bloqueio do alvo e sempre libertado, inclusive quando o ciclo falha |

## 8. Maquina de estados

```text
CREATED -> OBSERVING -> PLANNING -> VALIDATING -> EXECUTING -> REFLECTING
                                              \-> REFLECTING (accao recusada)
REFLECTING -> AWAITING_HUMAN_REVIEW | STOPPED | OBSERVING (reservado a E3)
qualquer estado nao terminal -> FAILED
```

Estados terminais: `AWAITING_HUMAN_REVIEW`, `STOPPED`, `FAILED`.
Estados de iteracao: `RUNNING`, `COMPLETED`, `FAILED`.

## 9. Configuracao

| Definicao | Omissao | Efeito |
| --- | --- | --- |
| `SCIENTIFIC_RETURN_AGENT_MODE` | `DISABLED` | Modo de operacao (RF-015) |
| `SCIENTIFIC_RETURN_AGENT_MAX_ITERATIONS` | `1` | Iteracoes por investigacao |
| `SCIENTIFIC_RETURN_AGENT_MAX_ACTIONS` | `1` | Accoes executaveis por investigacao |
| `SCIENTIFIC_RETURN_AGENT_MAX_QUERIES` | `4` | Consultas externas por investigacao |
| `SCIENTIFIC_RETURN_AGENT_MAX_RESULTS` | `10` | Resultados por consulta |
| `SCIENTIFIC_RETURN_AGENT_MAX_NEW_CANDIDATES` | `5` | Candidatos criados por investigacao |
| `SCIENTIFIC_RETURN_AGENT_ALLOWED_ACTIONS` | `SEARCH_INVENTORY_VARIANTS` | Allowlist de accoes |
| `SCIENTIFIC_RETURN_AGENT_ALLOWED_SOURCES` | `EUROPE_PMC` | Allowlist de fontes |

Nenhum valor vindo do cliente ou do modelo alarga estes limites.

---

## 10. Criterios de aceitacao

Formato: `Dado / Quando / Entao`, com o teste que o verifica.

### CA-001 — Descoberta com evidencia suficiente
Dado uma vigilancia ativa com execucao deterministica anterior
Quando o staff inicia uma investigacao de descoberta e a fonte devolve uma obra que cita o inventario
Entao e criado um candidato, a razao e `EVIDENCE_SUFFICIENT` e o estado e `AWAITING_HUMAN_REVIEW`
→ `test_run_investigation.py::test_a_discovery_creates_a_candidate_and_awaits_a_human`

### CA-002 — Enriquecimento nao toca no candidato
Dado um candidato `PENDING`
Quando o enriquecimento acrescenta evidencia verificada
Entao a evidencia e acrescentada e titulo, autores, DOI, URL e estado permanecem inalterados
→ `test_run_investigation.py::test_enrichment_adds_evidence_without_touching_the_candidate`

### CA-003 — A decisao continua humana
Dado uma investigacao terminada com candidato
Quando a resposta e devolvida
Entao o candidato continua `PENDING` e nao existe entrada no `PublicationLog`
→ `test_run_investigation.py::test_the_candidate_still_requires_a_human_decision`, `test_agent_security.py::test_the_cycle_has_no_route_to_the_publication_log`

### CA-004 — Objeto inventado nao chega a fonte
Dado um plano cujo `objectId` nao pertence ao snapshot
Quando a politica avalia a accao
Entao a accao e recusada com `OBJECT_NOT_IN_SNAPSHOT` e nenhuma fonte e contactada
→ `test_agent_security.py::test_the_model_cannot_investigate_an_object_it_invented`

### CA-005 — Accao inventada ou fora da allowlist
Dado um plano com um tipo de accao inexistente ou nao configurado
Quando o ciclo valida o plano
Entao nenhuma fonte e contactada e a investigacao termina com razao tipada
→ `test_agent_security.py::test_an_invented_action_never_reaches_a_source`, `::test_an_action_outside_the_allowlist_never_reaches_a_source`

### CA-006 — Texto injetado nao move nada
Dado texto de publicacao com instrucoes embutidas
Quando a evidencia e recalculada
Entao as regras de evidencia mantem-se e nenhum candidato muda de estado
→ `test_agent_security.py::test_injected_text_cannot_move_a_candidate`, `::test_injected_text_does_not_change_the_evidence_rules`

### CA-007 — Orcamento de consultas respeitado
Dado um orcamento de N consultas
Quando o ciclo executa
Entao o numero de consultas enviadas nunca excede N e o debito ocorre antes da execucao
→ `test_agent_security.py::test_one_investigation_cannot_exceed_its_query_budget`, `test_investigation_aggregate.py::test_the_budget_is_charged_before_the_tool_runs`

### CA-008 — Teto de candidatos
Dado o limite de candidatos criados por investigacao
Quando os resultados excedem esse limite
Entao a criacao para no teto e a razao e `CANDIDATE_LIMIT_REACHED`
→ `test_run_investigation.py::test_the_candidate_ceiling_is_respected`

### CA-009 — Idempotencia
Dado um `Idempotency-Key` ja utilizado
Quando o pedido e repetido
Entao a investigacao anterior e devolvida, nenhuma fonte e contactada e nenhum candidato e criado
→ `test_run_investigation.py::test_the_same_client_key_never_contacts_a_source_twice`, `::test_a_repeated_key_creates_no_second_candidate`, `::test_a_command_without_a_key_is_not_deduplicated`

### CA-010 — Fonte sem correspondencia exata e recusada
Dado que apenas Crossref esta na allowlist de fontes
Quando uma pesquisa de inventario e planeada
Entao a accao e recusada com `SOURCE_NOT_ALLOWED`
→ `test_run_investigation.py::test_a_source_that_cannot_match_exactly_is_refused`, `test_agent_policies.py::test_only_sources_that_honour_an_exact_phrase_are_routed_to`

### CA-011 — Indisponibilidade nao bloqueia a fila
Dado um modelo ou uma fonte indisponivel
Quando a investigacao e iniciada
Entao termina com `REASONER_UNAVAILABLE` ou `TOOL_UNAVAILABLE` e a fila de revisao permanece intacta
→ `test_run_investigation.py::test_an_unavailable_reasoner_leaves_the_queue_untouched`, `::test_an_unavailable_source_is_audited_without_blocking_review`

### CA-012 — Modo desativado
Dado `SCIENTIFIC_RETURN_AGENT_MODE=DISABLED`
Quando o staff inicia uma investigacao
Entao a resposta e `503` com `SCIENTIFIC_RETURN_AGENT_DISABLED`
→ `test_run_investigation.py::test_a_disabled_mode_refuses_to_start`

### CA-013 — Autorizacao
Dado um chamador fora de `CURATORIAL`, `COLLECTIONS_MANAGEMENT` ou `DIRECTION`
Quando inicia uma investigacao
Entao o pedido e recusado com `403`
→ `test_run_investigation.py::test_a_caller_outside_the_review_groups_is_refused`

### CA-014 — Trajetoria auditavel
Dado uma investigacao concluida
Quando a trajetoria e lida
Entao cada passo esta persistido individualmente, com hashes de evidencia, telemetria e decisao de politica
→ `test_run_investigation.py::test_the_trajectory_is_persisted_step_by_step`, `::test_the_full_trajectory_is_readable_afterwards`, `::test_the_iteration_records_which_model_and_prompt_produced_it`

### CA-015 — Bloqueio sempre libertado
Dado um ciclo que falha a meio
Quando o pedido termina
Entao o bloqueio do alvo esta libertado
→ `test_run_investigation.py::test_the_lock_is_released_even_when_the_cycle_fails`, `::test_a_held_lock_stops_the_cycle_before_anything_runs`

### CA-016 — Ausencia de fuga em registos
Dado uma falha durante o ciclo
Quando o erro e registado
Entao o registo contem identificadores e nao conteudo de projeto ou de publicacao
→ `test_agent_security.py::test_a_failure_logs_the_identifier_not_the_content`, `::test_an_unexpected_failure_logs_no_project_data`

## 11. Requisitos nao funcionais

- **Seguranca**: JWT + `X-Permission-Id`; `401` so para autenticacao, `403` para autorizacao. O snapshot do projeto e o texto exato das consultas sao cifrados em repouso.
- **Custo**: uma investigacao contacta no maximo `MAX_QUERIES` vezes uma fonte externa; a idempotencia impede repeticao pelo mesmo pedido.
- **Auditabilidade**: a trajetoria e persistida passo a passo; uma falha a meio deixa registo parcial legivel, nao nada.
- **Isolamento transacional**: nenhuma transacao permanece aberta enquanto um modelo ou uma fonte responde.
- **Arquitetura**: dominio e aplicacao livres de FastAPI e SQLAlchemy; contratos import-linter preservados.

## 12. Rastreabilidade

| Elemento da spec | Localizacao |
| --- | --- |
| Agregado e maquina de estados (seccao 8, INV-006/007) | `app/scientific_return/domain/investigation_models.py` |
| Politicas de accao e paragem (RF-007, RF-008, RF-012) | `app/scientific_return/domain/agent_policies.py` |
| Variantes de inventario (RF-009) | `app/scientific_return/domain/inventory_variants.py` |
| Delta e hash de evidencia (RF-010) | `app/scientific_return/domain/evidence_delta.py` |
| Orquestracao do ciclo (RF-001..RF-006, RF-011, RF-013) | `app/scientific_return/application/run_investigation.py` |
| Contrato do plano do modelo (RF-006) | `app/scientific_return/application/agent_contracts.py` |
| Execucao de ferramentas | `app/scientific_return/application/agent_tools.py` |
| Endpoints (RF-001, RF-002, RF-014) | `app/scientific_return/presentation/routes.py` |
| Configuracao e orcamento (seccao 9) | `app/config.py`, `app/scientific_return/presentation/dependencies.py` |
| Bloqueio por alvo (RF-004, INV-012) | `app/scientific_return/infrastructure/investigation_lock.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 13. Questoes em aberto

1. Qual o criterio de promocao de OpenAlex para a allowlist de correspondencia exata? Exige a mesma medicao empirica feita a Crossref.
2. Com multiplas iteracoes (E3), qual o criterio de paragem por retorno decrescente, para alem do orcamento?
3. A telemetria por iteracao deve alimentar uma metrica agregada de custo por candidato confirmado?
