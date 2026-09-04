# SPEC-004 — Decisao curatorial de candidato e registo de publicacao

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-004 |
| Estado | Implementado |
| Contexto delimitado | `app/scientific_return` (escreve em `use_of_collections` pela linguagem publicada) |
| Escrita a partir de | `domain/models.py`, `application/use_cases.py`, `infrastructure/acls.py`, `test/scientific_return/test_scientific_return.py` |
| Specs relacionadas | [SPEC-003](../003-pipeline-deterministico-bibliografico/spec.md), [SPEC-009](../009-projeto-uso-de-colecoes/spec.md) |

## 1. Problema

Um candidato bibliografico e uma hipotese. Transforma-la em registo
institucional — "esta publicacao resultou deste projeto" — e um ato curatorial
com consequencias para relatorios, indicadores e memoria da instituicao. Esse
ato tem de ser deliberado, justificado e reconstituivel.

## 2. Objetivo

Definir a fronteira entre o que o sistema propoe e o que uma pessoa decide, e
garantir que so a decisao humana materializa uma publicacao no registo do
projeto.

## 3. Atores

| Ator | Papel |
| --- | --- |
| `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION` | Decidem candidatos |
| `SYS_ADMIN` | Le a fila e o historico; nao decide |

## 4. Linguagem ubiqua

- **Candidato**: publicacao proposta, com estado `PENDING`, `CONFIRMED`, `DISMISSED` ou `SNOOZED`.
- **Decisao**: ato tipado sobre um candidato — `CONFIRM`, `CORRECT_AND_CONFIRM`, `DISMISS`, `SNOOZE`.
- **Correcao**: alteracao de titulo, DOI, URL ou autores feita por uma pessoa no momento da confirmacao.
- **Entrada de publicacao**: registo no `PublicationLog` do projeto, no contexto `use_of_collections`.
- **Instantaneo de evidencia**: copia da evidencia tal como estava visivel no momento da decisao.

---

## 5. Requisitos funcionais

### RF-001 — Fila de revisao por projeto e global

- `GET /api/v1/scientific-return/projects/{projectId}/candidates?status=PENDING&page=0&size=20`
- `GET /api/v1/scientific-return/candidates?status=PENDING&source=CROSSREF&evidenceStrength=PRIMARY&page=0&size=20`

Cada candidato traz metadados bibliograficos normalizados e a lista ordenada de
evidencias, cada uma com tipo, forca, valor, campo de origem e explicacao.
`objectId` liga a evidencia ao objeto consultado. Os itens da fila global
acrescentam `projectId`. Filtros sao opcionais; `status` assume `PENDING`.

A forca da evidencia e informacao para leitura humana, **nao** uma pontuacao de
confianca automatica.

### RF-002 — Decidir um candidato

`POST /api/v1/scientific-return/candidates/{candidateId}/decision`

| Decisao | Exigencia | Efeito |
| --- | --- | --- |
| `CONFIRM` | — | Cria a entrada no `PublicationLog` e marca `CONFIRMED` |
| `CORRECT_AND_CONFIRM` | `correction` | Aplica a correcao, cria a entrada e marca `CONFIRMED` |
| `DISMISS` | `justification` nao vazia | Marca `DISMISSED` |
| `SNOOZE` | `snoozedUntil` no futuro | Marca `SNOOZED` ate a data |

### RF-003 — Materializacao transacional

`CONFIRM` e `CORRECT_AND_CONFIRM` criam a `PublicationLogEntry` **na mesma
transacao** da decisao e devolvem o seu identificador em
`confirmedPublicationEntryId`. Nao existe estado intermedio em que o candidato
esta confirmado sem entrada, nem o contrario.

A escrita atravessa a linguagem publicada de `use_of_collections`; o contexto de
retorno cientifico nunca escreve diretamente nas tabelas desse contexto.

### RF-004 — Correcao delimitada

Uma correcao pode alterar titulo, DOI, URL e autores. Campos omitidos preservam
o valor original. Nenhuma outra propriedade do candidato e editavel.

### RF-005 — Decisoes finais nao se revisitam

Um candidato `CONFIRMED` ou `DISMISSED` recusa nova decisao. `SNOOZED` e
`PENDING` continuam decidiveis.

### RF-006 — Adiamento com regresso automatico

Um candidato `SNOOZED` cujo prazo expirou volta a `PENDING` quando a execucao
seguinte o reencontra ([SPEC-003](../003-pipeline-deterministico-bibliografico/spec.md), RF-012).

### RF-007 — Historico auditavel

`GET /api/v1/scientific-return/candidates/{candidateId}/decisions` devolve cada
decisao com tipo, justificacao, autor, instante, correcao aplicada e o
instantaneo da evidencia visivel no momento da decisao.

O instantaneo existe porque a evidencia pode crescer depois — por execucao
posterior ou por investigacao assistida. Sem ele, ninguem consegue reconstituir
com que fundamento a pessoa decidiu.

---

## 6. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Nenhuma entrada no `PublicationLog` existe sem uma confirmacao humana explicita |
| INV-002 | Confirmacao e entrada de publicacao sao criadas na mesma transacao |
| INV-003 | Um descarte exige justificacao registada |
| INV-004 | Um adiamento exige data futura |
| INV-005 | Uma decisao final e definitiva |
| INV-006 | Toda a decisao guarda a evidencia que a fundamentou |
| INV-007 | Nenhum processo automatico — pipeline, analise LLM ou ciclo agentic — decide um candidato |

## 7. Criterios de aceitacao

### CA-001 — Confirmacao materializa e audita
Dado um candidato `PENDING` com evidencia
Quando um curador confirma
Entao e criada a entrada de publicacao no projeto e a decisao guarda o instantaneo da evidencia
→ `test_scientific_return.py::test_confirm_materializes_publication_and_audits_evidence`

### CA-002 — Adiamento exige data futura
→ `test_scientific_return.py::test_snooze_requires_a_future_date`

### CA-003 — Descarte sobrevive as execucoes seguintes
→ `test_scientific_return.py::test_dismissed_candidate_is_remembered_on_later_run`

### CA-004 — Nenhum automatismo decide
→ `test_agent_security.py::test_no_candidate_is_ever_decided_by_the_cycle`, `::test_the_cycle_has_no_route_to_the_publication_log`, `test_run_investigation.py::test_the_candidate_still_requires_a_human_decision`

## 8. Requisitos nao funcionais

- **Postura**: a funcionalidade e advisory; resultados bibliograficos sao candidatos ate uma pessoa os confirmar.
- **Transacionalidade**: RF-003 e INV-002.
- **Fronteiras**: escrita cruzada apenas por `use_of_collections.public`; contratos import-linter preservados.

## 9. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Estados e transicoes do candidato (RF-002, RF-005, RF-006) | `app/scientific_return/domain/models.py` |
| Caso de uso da decisao (RF-002..RF-004, RF-007) | `app/scientific_return/application/use_cases.py` |
| Escrita no `PublicationLog` (RF-003) | `app/scientific_return/infrastructure/acls.py` |
| Endpoints e filtros (RF-001, RF-007) | `app/scientific_return/presentation/routes.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 10. Questoes em aberto

1. Deve existir reversao supervisionada de uma confirmacao errada, ou a correcao pertence ao `PublicationLog` do projeto?
2. Um descarte devia poder ser tipado (fora de ambito, homonimia de autor, especime distinto) para alimentar a avaliacao?
