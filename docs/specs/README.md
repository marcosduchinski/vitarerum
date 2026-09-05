---
status: current
---

# Especificacoes (specs)

Uma spec descreve **o que o sistema faz e sob que regras**, a partir do
comportamento ja implementado. Distingue-se dos documentos vizinhos:

| Pasta | Responde a |
| --- | --- |
| `docs/api_contracts/` | Como se fala com o sistema (regras transversais de HTTP) |
| `docs/proposals/` | O que se pretende fazer e ainda nao existe |
| `docs/specs/` | O que o sistema garante (requisitos, invariantes, criterios verificaveis) |

## Estrutura

```text
docs/specs/NNN-nome-curto/
  spec.md      # requisitos, invariantes, criterios de aceitacao
  plan.md      # opcional: desenho tecnico, quando a spec e escrita antes do codigo
  tasks.md     # opcional: decomposicao executavel
```

## Convencoes

- Requisitos numerados `FR-nnn`; invariantes `INV-nnn`; criterios de aceitacao
  `AC-nnn`; lacunas declaradas `GAP-nnn`.
- Nem todas as specs numeram os criterios: oito delas (014–020 e 022)
  apresentam a aceitacao como tabela *capacidade → evidencia automatizada*, por
  vezes seguida de cenarios numerados. As duas formas sao aceites; o que nao e
  aceite e um criterio sem evidencia identificavel.
- Cada criterio de aceitacao aponta para o teste que o verifica. Um criterio sem
  teste e uma lacuna **declarada**, nao uma omissao silenciosa.
- Cada spec declara as suas lacunas de implementacao em `GAP-nnn` — propriedades
  do repositorio atual, nao trabalho hipotetico futuro.
- A spec nao descreve implementacao; a rastreabilidade para o codigo vive numa
  seccao final propria.
- Cada spec termina com questoes em aberto — decisoes que o codigo nao responde.
- As specs estao escritas em ingles; este indice e os nomes das pastas mantem-se
  em portugues sem acentos.

## O que o numero significa

O `NNN` e um **identificador, nao uma posicao**. E atribuido pela ordem por que
as specs foram escritas — o retorno cientifico primeiro, por ser o objeto do
trabalho — e nunca muda, porque e citado por outras specs, pela arquitetura,
pelos ADR e por trabalho externo a este repositorio.

Nao le como ordem de desenvolvimento nem como ordem de dependencia, e nao
podia:

- **Cronologia**: o que esta numerado 001–006 e o **ultimo** a ser construido
  (2026-08-14). O primeiro (2026-06-27) e o conjunto 007, 008, 009, 010, 013,
  015, 017, 022 e 023 — nove specs sobre sete contextos que nasceram no mesmo
  commit inicial, portanto sem ordem nenhuma entre si.
- **Dependencia**: o grafo de citacoes entre specs **nao e aciclico**. Ha 32
  pares mutuamente dependentes (008↔009, 013↔015, 024↔025, entre outros), porque
  uma proposta aprovada *torna-se* um projeto e uma visita *produz* um relatorio.
  Nao existe ordenacao linear para codificar num numero.

As duas leituras que um numero nao consegue dar estao abaixo: um percurso de
leitura e o grafo de dependencias. A coluna "Contexto desde" no inventario da a
cronologia.

## Percurso de leitura

Para quem chega ao sistema, por camadas. Dentro de cada camada a ordem e a
sugerida; entre camadas, cada uma assenta nas anteriores.

| # | Camada | Ler por esta ordem |
| --- | --- | --- |
| 1 | **Fundacoes** — quem pode agir, e sob que garantias | [007](007-identidade-e-acesso/spec.md) identidade → [022](022-cifragem-e-armazenamento/spec.md) cifragem → [023](023-fronteiras-e-envelope-de-erro/spec.md) fronteiras e erro |
| 2 | **Fluxo institucional** — o ciclo de vida central | [010](010-submissao-publica/spec.md) submissao publica → [008](008-proposta-uso-de-colecoes/spec.md) proposta → [009](009-projeto-uso-de-colecoes/spec.md) projeto → [019](019-numeros-de-referencia/spec.md) numeros de referencia |
| 3 | **Capacidades de apoio** — servem o fluxo sem participar nele | [014](014-catalogo-e-indice-de-objetos/spec.md) catalogo → [012](012-modelos-de-documento/spec.md) modelos → [011](011-perguntas-ao-museu/spec.md) perguntas → [018](018-notificacoes/spec.md) notificacoes |
| 4 | **Patrimonio e IA** — o que a visita produz | [013](013-mapeamento-cidoc-crm/spec.md) CIDOC-CRM → [015](015-relatorio-visita-in-situ/spec.md) relatorio → [016](016-prompts-versionados/spec.md) prompts → [017](017-narrativa-museologica/spec.md) narrativa → [020](020-publicacao-externa/spec.md) publicacao externa |
| 5 | **Retorno cientifico** — o objeto do trabalho | [001](001-investigacao-agentica-assistida/spec.md) ciclo assistido → [002](002-vigilancia-retorno-cientifico/spec.md) vigilancia → [003](003-pipeline-deterministico-bibliografico/spec.md) pipeline → [004](004-decisao-candidato-publicacao/spec.md) decisao → [006](006-avaliacao-retorno-cientifico/spec.md) avaliacao → [024](024-investigacao-agentica-autonoma/spec.md) ciclo autonomo → [005](005-analise-agentica-de-candidato/spec.md) analise e retorno → [025](025-base-de-conhecimento-curatorial/spec.md) memoria curatorial |

Fora do percurso: [021](021-resumos-de-painel/spec.md) especifica o que ainda
nao existe.

### Como as camadas dependem umas das outras

```mermaid
flowchart TD
    F["1 · Fundacoes<br/>007 · 022 · 023"]
    I["2 · Fluxo institucional<br/>010 · 008 · 009 · 019"]
    C["3 · Capacidades de apoio<br/>014 · 012 · 011 · 018"]
    P["4 · Patrimonio e IA<br/>013 · 015 · 016 · 017 · 020"]
    R["5 · Retorno cientifico<br/>001..006 · 024 · 025"]

    I -->|8| F
    C -->|5| I
    F -->|5| I
    C -->|4| F
    F -->|3| C
    P -->|3| I
    R -->|3| F
    P -->|2| R
    R -->|2| P
    C -->|1| R
    F -->|1| P
    F -->|1| R
    I -->|1| P
    I -->|1| R
    P -->|1| F
    R -->|1| I
```

As setas contam citacoes entre specs das duas camadas. Que apontem nos dois
sentidos e o ponto: as camadas **compoem-se**, nao se empilham. Uma spec de
fundacoes cita o fluxo porque e ai que a garantia se manifesta.

### Dependencias declaradas, por spec

Extraidas das citacoes `SPEC-NNN` dentro de cada spec.

| Spec | Cita |
| --- | --- |
| 001 | 002, 003, 004, 005, 016, 022, 024 |
| 002 | 001, 003, 004 |
| 003 | 001, 002, 004, 006, 024 |
| 004 | 001, 002, 003, 009, 024 |
| 005 | 001, 002, 004, 016, 024, 025 |
| 006 | 001, 003, 024 |
| 007 | — |
| 008 | 007, 009, 010, 019, 022, 023 |
| 009 | 004, 008, 013, 019, 022, 023 |
| 010 | 007, 008, 019, 022, 023 |
| 011 | 010, 018, 022 |
| 012 | 008, 010, 022 |
| 013 | 009, 015, 017 |
| 014 | 007, 008 |
| 015 | 009, 013, 016, 017 |
| 016 | 001, 005, 015, 017 |
| 017 | 013, 015, 016 |
| 018 | 002, 007, 008, 011 |
| 019 | 008, 009, 010 |
| 020 | 009, 013, 015, 017, 023 |
| 021 | 007, 008, 009, 011, 014, 018 |
| 022 | 002, 008, 009, 010, 011, 012, 014, 019, 023 |
| 023 | 007, 019, 020, 022 |
| 024 | 001, 002, 004, 022, 025 |
| 025 | 001, 004, 022, 024 |

As mais citadas sao **022** (9 vezes), **001**, **008** e **009** (8), **002** e
**004** (7): sao as specs a ler antes de mexer em qualquer outra. A unica que
nao cita nenhuma e a **007** — o ponto de entrada do sistema, de que tudo o
resto depende.

## Inventario

"Contexto desde" e a data do primeiro commit que introduziu o contexto
delimitado que a spec descreve — a cronologia real de construcao, que o numero
da spec nao da. As specs 024 e 025 trazem a data da propria funcionalidade, por
terem chegado ao contexto `scientific_return` depois de ele existir.


### Retorno cientifico (`scientific_return`)

| Spec | Ambito | Estado | Contexto desde |
| --- | --- | --- | --- |
| [SPEC-001](001-investigacao-agentica-assistida/spec.md) | Ciclo agentic assistido (E1) | Implementado | 2026-08-14 |
| [SPEC-002](002-vigilancia-retorno-cientifico/spec.md) | Vigilancia e cadencia de revisao | Implementado | 2026-08-14 |
| [SPEC-003](003-pipeline-deterministico-bibliografico/spec.md) | Pipeline deterministico de descoberta | Implementado | 2026-08-14 |
| [SPEC-004](004-decisao-candidato-publicacao/spec.md) | Decisao curatorial e registo de publicacao | Implementado | 2026-08-14 |
| [SPEC-005](005-analise-agentica-de-candidato/spec.md) | Analise agentica de candidato e retorno curatorial | Implementado | 2026-08-14 |
| [SPEC-006](006-avaliacao-retorno-cientifico/spec.md) | Avaliacao reprodutivel | Implementado | 2026-08-14 |
| [SPEC-024](024-investigacao-agentica-autonoma/spec.md) | Ciclo agentic autonomo (full-agentic) | Implementado | 2026-08-24 |
| [SPEC-025](025-base-de-conhecimento-curatorial/spec.md) | Base de conhecimento curatorial | Implementado | 2026-08-24 |

### Fluxo institucional

| Spec | Contexto | Estado | Contexto desde |
| --- | --- | --- | --- |
| [SPEC-007](007-identidade-e-acesso/spec.md) | `identity` | Implementado | 2026-06-27 |
| [SPEC-008](008-proposta-uso-de-colecoes/spec.md) | `use_of_collections` — fase de proposta | Implementado | 2026-06-27 |
| [SPEC-009](009-projeto-uso-de-colecoes/spec.md) | `use_of_collections` — fase de projeto e diarios | Implementado | 2026-06-27 |
| [SPEC-010](010-submissao-publica/spec.md) | `public_submission` | Implementado | 2026-06-27 |
| [SPEC-011](011-perguntas-ao-museu/spec.md) | `museum_questions` | Implementado (com uma lacuna declarada) | 2026-07-05 |
| [SPEC-012](012-modelos-de-documento/spec.md) | `document_templates` | Implementado | 2026-07-02 |
| [SPEC-014](014-catalogo-e-indice-de-objetos/spec.md) | `collection_object_index` | Implementado | 2026-07-04 |
| [SPEC-019](019-numeros-de-referencia/spec.md) | `reference_numbers` | Implementado | 2026-07-24 |
| [SPEC-018](018-notificacoes/spec.md) | `notifications` | Implementado | 2026-07-30 |

### Patrimonio, IA e difusao

| Spec | Contexto | Estado | Contexto desde |
| --- | --- | --- | --- |
| [SPEC-013](013-mapeamento-cidoc-crm/spec.md) | `cidoc_crm.in_situ_visit_mapping` | Implementado | 2026-06-27 |
| [SPEC-015](015-relatorio-visita-in-situ/spec.md) | `reports.in_situ_visit` | Implementado | 2026-06-27 |
| [SPEC-016](016-prompts-versionados/spec.md) | `ai.prompts` | Implementado | 2026-07-18 |
| [SPEC-017](017-narrativa-museologica/spec.md) | `ai.museum_narrative` | Implementado | 2026-06-27 |
| [SPEC-020](020-publicacao-externa/spec.md) | `external_publications` | Implementado | 2026-07-30 |

### Transversais

| Spec | Ambito | Estado | Contexto desde |
| --- | --- | --- | --- |
| [SPEC-022](022-cifragem-e-armazenamento/spec.md) | Cifragem em repouso, armazenamento e autorizacao partilhada | Implementado | 2026-06-27 |
| [SPEC-023](023-fronteiras-e-envelope-de-erro/spec.md) | Fronteiras de contexto, camadas e envelope de erro | Implementado | 2026-06-27 |

### Por implementar

| Spec | Ambito | Estado | Contexto desde |
| --- | --- | --- | --- |
| [SPEC-021](021-resumos-de-painel/spec.md) | Resumos de painel (dashboard) | **Especificado, nao implementado** | — |

## Verificacao

O inventario cobre todos os contextos delimitados ativos listados em
`AGENTS.md`.

Em 2026-08-18, ao escrever as specs:

- **Referencias a testes**: 692 referencias `ficheiro::teste` conferidas contra
  `vitarerum-api/test/`; zero inexistentes.
- **Fronteiras arquiteturais**: `uv run lint-imports` — 36 contratos, 0 quebrados
  ([SPEC-023](023-fronteiras-e-envelope-de-erro/spec.md), AC-001).

Em 2026-09-04, ao acrescentar a cobertura dos endpoints em falta (SPEC-024,
SPEC-025 e acrescentos a SPEC-009, SPEC-014, SPEC-015 e SPEC-017) e ao
reconciliar as specs com o codigo (divergencias 3 a 5):

- **Referencias a testes**: conferidas por `scripts/check_docs.py`; **zero
  inexistentes**. O verificador ja nao tolera nenhuma.
- **Cobertura de endpoints**: todos os endpoints documentados foram comparados
  com os citados nestas specs, incluindo o contrato local do backend que
  escapara a consolidacao. Lacuna: zero.

Em 2026-09-05, na revisao global das 25 specs (divergencias 6 a 13):

- **Verificador de documentacao**: `python3 scripts/check_docs.py` — ligacoes,
  referencias a testes, estado, diagramas, citacoes de codigo e rotas nomeadas
  por uma spec: tudo ok.
- **Testes do backend**: `uv run pytest` — 1373 passam, zero falham.
- **Testes do frontend**: `npx ng test --no-watch` — 833 passam, **3 falham**,
  todas agora declaradas (divergencia 13).
- **Fronteiras arquiteturais**: 36 contratos `import-linter`, 14 contratos de
  camadas — os numeros que a [SPEC-023](023-fronteiras-e-envelope-de-erro/spec.md)
  afirma.
- **Valores conferidos contra o codigo**: limites e defaults das SPEC-001,
  SPEC-003, SPEC-007, SPEC-014, SPEC-019 e SPEC-025 (`app/config.py`,
  politicas de palavra-passe, limites de ritmo, mascaras semeadas na migracao
  `0041`, fixture de avaliacao v3 com 12 casos e 6 publicacoes nao mapeadas).

## Divergencias encontradas entre contrato e codigo

Levantadas ao escrever as specs, em 2026-08-18:

1. `GET /museum-questions/summary` estava documentado no contrato 14 mas **nao
   existe** — sem rota, caso de uso ou teste
   ([SPEC-011](011-perguntas-ao-museu/spec.md), FR-017 e GAP-012). Alem disso,
   tal como as rotas estao declaradas, `summary` seria capturado por
   `GET /museum-questions/{questionId}`.
   *Resolvido: os contratos numerados foram consolidados em
   [`docs/api_contracts/README.md`](../api_contracts/README.md), que ja nao
   menciona o endpoint; a SPEC-011 mantem-no como requisito reservado.*
2. Nenhum dos quatro endpoints do contrato 17 (resumos de painel) existe
   ([SPEC-021](021-resumos-de-painel/spec.md)).
   *Resolvido: o contrato 17 foi movido para
   [`docs/proposals/`](../proposals/17Dashboard-Summary-API.md) e marcado como
   proposta nao implementada.*
Levantadas em 2026-09-04, ao conferir as referencias a testes, e **todas
resolvidas** na mesma data:

3. A SPEC-005 descrevia a geracao em sombra, removida no commit `a571392`.
   Reescrita como [SPEC-005 — Analise agentica de candidato e retorno
   curatorial](005-analise-agentica-de-candidato/spec.md): a geracao saiu, o
   registo da analise do leitor e o feedback curatorial ficaram, porque
   continuam em codigo.
4. A SPEC-004 documentava o adiamento (`SNOOZE`, estado `SNOOZED`), removido no
   commit `7ab131f` — retirado, com os requisitos e criterios renumerados. A
   [SPEC-002](002-vigilancia-retorno-cientifico/spec.md) descrevia a cadencia
   ancorada em `lastRunAt`, substituida no commit `e4a4ce0` pela grelha fixa a
   partir de `scheduleAnchorAt` — FR-008, FR-010 e os criterios reescritos.
5. O fluxo de revisao da Direcao (`refer-to-direction`, `return-to-staff`)
   estava implementado e testado sem spec nenhuma, documentado apenas num
   contrato local do backend. Absorvido pela
   [SPEC-008](008-proposta-uso-de-colecoes/spec.md) (FR-014) e o
   contrato removido.

Levantadas em 2026-09-05, na revisao global das specs, e **todas resolvidas** na
mesma data:

6. Os identificadores estavam em duas convencoes — `RF`/`CA` em onze specs e
   `FR`/`AC` em catorze — depois da traducao para ingles. Normalizados para
   `FR`/`INV`/`AC`/`GAP` em todo o corpo, e as convencoes acima reescritas para
   descrever o que as specs fazem mesmo.
7. A SPEC-008 (FR-004) dizia que a proposta recebe `VRP-YYYYMMDD-XXXX` e o
   projeto `CUP-XXXXXXXX`. As mascaras semeadas pela migracao
   `0041_reference_number_policies` sao `PP-MUHNAC/COL/YYYY/XXXX` e
   `PR-MUHNAC/COL/YYYY/XXXX`; `VRP`/`CUP` sao formatos legados, como ja diziam a
   [SPEC-009](009-projeto-uso-de-colecoes/spec.md) e a
   [SPEC-019](019-numeros-de-referencia/spec.md). Corrigido.
8. A SPEC-003 punha "investigacao autonoma (SPEC-001)" fora de ambito; a
   SPEC-001 e o ciclo *assistido*. Corrigido, com a SPEC-024 acrescentada.
9. A SPEC-023 (FR-012) citava "SPEC-022, RF-003 e RF-008" para as respostas de
   corrupcao; o requisito e o FR-011 da SPEC-022. Corrigido.
10. Esta tabela de dependencias, a contagem de pares mutuos, as specs mais
    citadas e o grafo de camadas estavam desatualizados face as citacoes reais.
    Regenerados.

Levantadas na mesma revisao e **por resolver** — ficam declaradas nas specs:

11. `app/ai/museum_question_triage` mantem metadados ORM e duas tabelas de uma
    funcionalidade removida, sem spec, sem contrato e sem decisao de retencao
    ([SPEC-023](023-fronteiras-e-envelope-de-erro/spec.md), lacuna 10, e
    [SPEC-011](011-perguntas-ao-museu/spec.md), GAP-006).
12. `docs/architecture/module-boundaries.md` e `vitarerum-api/AGENTS.md` nao
    listam todos os contextos ativos: falta `external_publications` e
    `reference_numbers` em ambos, e `notifications` no AGENTS.md
    ([SPEC-023](023-fronteiras-e-envelope-de-erro/spec.md), lacuna 8).
13. Tres testes de componente Angular falham: dois ja declarados pela
    [SPEC-008](008-proposta-uso-de-colecoes/spec.md) (GAP-014) e um terceiro,
    o controlo de fora de ambito escondido, agora declarado pela
    [SPEC-011](011-perguntas-ao-museu/spec.md) (GAP-008).
