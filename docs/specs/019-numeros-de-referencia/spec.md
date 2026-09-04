# SPEC-019 — Numeros de referencia com politica configuravel

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-019 |
| Estado | Implementado |
| Contexto delimitado | `app/reference_numbers` |
| Escrita a partir de | `domain/models.py`, `application/`, `public.py`, `test/reference_numbers/` |
| Specs relacionadas | [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-009](../009-projeto-uso-de-colecoes/spec.md) |

## 1. Problema

Cada documento institucional precisa de um numero de referencia legivel
(`VRP-20250115-0001`, `CUP-1A2B3C4D`). O formato e uma convencao administrativa
que muda com o tempo, e mudar convencao nao pode invalidar o que ja foi emitido
nem exigir um *deploy*.

## 2. Objetivo

Gerar numeros de referencia a partir de **politicas configuraveis por tipo de
documento**, com sequencias controladas, mantendo validos os numeros emitidos sob
politicas anteriores e sob formatos legados.

## 3. Linguagem ubiqua

- **Tipo (`ReferenceKind`)**: `PROPOSAL`, `COLLECTION_USE_PROJECT`, `OBJECT_ACCESS_LOG`, `OBJECT_OCCURRENCE_LOG`, `PUBLICATION_LOG`.
- **Politica**: mascara e ambito de sequencia para um tipo. Estados `DRAFT`, `ACTIVE`, `INACTIVE`, `RETIRED`.
- **Mascara**: padrao com literais, marcas de data e uma corrida final de sequencia (`X`).
- **Ambito de sequencia**: `GLOBAL`, `YEAR`, `MONTH` ou `DAY`.
- **Formato legado**: forma antiga aceite em validacao, sem ser gerada.
- **Evento de politica**: `CREATED`, `ACTIVATED`, `DEACTIVATED`, `RETIRED`.

---

## 4. Requisitos funcionais

### RF-001 — Geracao pela linguagem publicada

Os outros contextos geram numeros por `app.reference_numbers.public`, indicando
tipo e data. Nunca constroem numeros por si.

### RF-002 — Estrutura da mascara

Uma mascara valida:

- contem apenas letras, digitos, `/`, `_` e `-`;
- contem **exatamente uma** corrida de sequencia;
- essa corrida e o **ultimo** elemento;
- a largura da sequencia respeita o tecto maximo.

### RF-003 — Interpretacao conservadora das marcas de data

Uma corrida maxima de letras so se torna marca de data se decompuser
**inteiramente** em `YYYY`, `YY`, `MM` ou `DD`. Caso contrario, permanece
literal.

Sem esta regra, o `MM` dentro de um prefixo literal como `COMM` seria lido como
mes, corrompendo a renderizacao e a validacao. Marcas de data concatenadas
continuam a ser interpretadas corretamente.

### RF-004 — Ambito derivado da mascara

O ambito da sequencia deriva das marcas presentes: uma mascara com ano
reinicia a sequencia por ano.

### RF-005 — Transicoes de politica

| De | Para | Permitido |
| --- | --- | --- |
| `DRAFT` | `ACTIVE` | sim |
| `DRAFT` | desativacao | nao |
| `ACTIVE` | `INACTIVE` | sim |
| `INACTIVE` | `ACTIVE` | sim (reativacao) |
| `ACTIVE` | `ACTIVE` | nao (ja ativa) |
| `RETIRED` | `ACTIVE` | nao |

Existe no maximo uma politica ativa por tipo; ativar uma nova desativa a
anterior, e o conflito de ativacao concorrente e detetado.

### RF-006 — Pre-visualizacao antes de ativar

`SYS_ADMIN` pode pre-visualizar o resultado de uma mascara antes de criar ou
ativar a politica. A pre-visualizacao e vedada a quem nao seja `SYS_ADMIN`.

### RF-007 — Autorizacao exclusiva de `SYS_ADMIN`

Ler e alterar politicas de referencia e exclusivo de `SYS_ADMIN`. Outros grupos
de staff nao leem nem alteram.

### RF-008 — Validacao independente da geracao

Validar um numero existente usa a politica que estava em vigor e os formatos
legados declarados. Uma politica em rascunho que nunca foi ativada **nao** e
usada para validar.

Um numero antigo em formato hexadecimal so e valido se existir um formato legado
declarado que o cubra; uma mascara numerica por si nao o valida.

### RF-009 — Numeros longos validos por politica

O invólucro de numero de referencia aceita valores longos desde que a politica os
considere validos: o limite e a politica, nao uma constante do codigo.

### RF-010 — Esgotamento de sequencia explicito

Exceder a largura da sequencia levanta erro tipado de esgotamento, em vez de
truncar ou de repetir um numero.

### RF-011 — Historico de politica sem quebrar integridade

Criar, ativar e desativar politicas registam eventos sem violar a chave
estrangeira do registo de eventos: o historico e escrito na ordem que a
integridade referencial exige.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Existe no maximo uma politica ativa por tipo |
| INV-002 | A corrida de sequencia e unica e final |
| INV-003 | Uma corrida de letras que nao decomponha em marcas de data permanece literal |
| INV-004 | Um numero ja emitido continua valido apos mudanca de politica |
| INV-005 | Uma politica nunca ativada nao valida nada |
| INV-006 | Uma politica retirada nunca volta a estar ativa |
| INV-007 | Esgotar a sequencia falha de forma explicita |
| INV-008 | Apenas `SYS_ADMIN` le ou altera politicas |

## 6. Criterios de aceitacao

### CA-001 — Renderizacao e ambito derivado
→ `test_domain.py::test_mask_renders_and_derives_year_scope`

### CA-002 — Estrutura da mascara
→ `test_domain.py::test_mask_rejects_sequence_that_is_not_final_token`, `::test_mask_sequence_width_is_hard_ceiling`

### CA-003 — Interpretacao conservadora das marcas
→ `test_domain.py::test_literal_text_containing_a_date_token_substring_is_not_misparsed`, `::test_concatenated_date_tokens_still_parse_correctly`

### CA-004 — Validacao de formatos legados
→ `test_domain.py::test_numeric_mask_does_not_validate_legacy_hex_without_legacy_format`, `::test_reference_number_wrapper_allows_policy_valid_long_values`

### CA-005 — Transicoes de politica
→ `test_domain.py::test_inactive_policy_can_be_reactivated_but_active_cannot_be_activated_again`, `::test_cannot_activate_a_retired_policy`, `::test_cannot_deactivate_a_draft_policy`

### CA-006 — Rascunho nunca ativado nao valida
→ `test_application.py::test_validate_reference_number_ignores_never_activated_draft_policy`

### CA-007 — Historico sem violar integridade
→ `test_application.py::test_add_policy_does_not_violate_the_event_foreign_key`, `::test_activate_and_deactivate_do_not_violate_the_event_foreign_key`

### CA-008 — Autorizacao exclusiva de `SYS_ADMIN`
→ `test_api.py::test_sys_admin_can_preview_and_create_reference_policy`, `::test_staff_cannot_read_or_mutate_reference_policies`, `test_application.py::test_preview_reference_policy_requires_sys_admin`

## 7. Requisitos nao funcionais

- **Concorrencia**: a atribuicao de sequencia tolera concorrencia; quem consome trata o conflito repetindo a geracao ([SPEC-010](../010-submissao-publica/spec.md), RF-009).
- **Fronteiras**: geracao apenas por linguagem publicada.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Mascara, politica e transicoes (RF-002..RF-005, RF-010) | `app/reference_numbers/domain/models.py` |
| Casos de uso e validacao (RF-006..RF-008, RF-011) | `app/reference_numbers/application/` |
| Sequencias e persistencia | `app/reference_numbers/infrastructure/` |
| Linguagem publicada (RF-001) | `app/reference_numbers/public.py` |
| Politicas ilustradas | `docs/diagrams/reference-number-policies.svg` |

## 9. Questoes em aberto

1. Deve existir simulacao de impacto antes de ativar uma politica (quantos numeros passariam a ser invalidos na validacao)?
2. O tecto de largura de sequencia devia ser por tipo, em vez de global?
