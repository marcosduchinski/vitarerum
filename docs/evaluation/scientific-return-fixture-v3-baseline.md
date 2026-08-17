# Baseline do retorno cientifico sobre a fixture ampliada

Data: 2026-08-17

Substitui, como referencia, a baseline de cinco casos documentada em
[`scientific-return-phase0-crossref-baseline.md`](scientific-return-phase0-crossref-baseline.md).
Corresponde ao passo 2 da ordem de implementacao do plano evolutivo.

## Configuracao

- fixture: `scientific-return-eval-fixture-v3`, doze casos;
- fontes: Crossref e Europe PMC, esta ultima com texto integral;
- OpenAlex nao exercitada: sem chave de API configurada;
- limite: 20 resultados por query;
- estrategias exatas: inventario, autor + inventario, inventario + objeto e
  autor + objeto;
- adaptacao: inventario + genero e autor + genero somente quando as quatro
  estrategias exatas nao produziram candidato acionavel;
- 124 queries, zero erros HTTP.

Comando:

```bash
uv run python -m app.scientific_return.presentation.commands \
  evaluate-phase0 --sources crossref,europe_pmc --result-limit 20
```

## O que passou a ser medido

A baseline anterior media apenas se o DOI esperado aparecia em alguma lista de
resultados. Isso e insuficiente: uma publicacao recuperada que nao passa o gate
acionavel nunca chega a um humano e, para efeitos de retorno cientifico, nao foi
encontrada. Passam a existir duas medidas independentes:

- **estado**: `RESOLVED` quando a publicacao esperada se torna candidato
  acionavel; `GAP` caso contrario;
- **evidencia de inventario**: se esse candidato possui evidencia primaria de
  inventario.

O cruzamento das duas produz o objetivo agentic de cada caso, calculado e nao
declarado: `GAP` e alvo de `DISCOVER_CANDIDATE`; `RESOLVED` sem evidencia de
inventario e alvo de `ENRICH_CANDIDATE`.

## Resultado

| Caso | Estado | Evidencia inventario | Melhor posicao | Candidatos acionaveis | Queries | Objetivo agentic |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `rhoptropus-2025` | RESOLVED | nao | 1 | 1 | 10 | `ENRICH_CANDIDATE` |
| `acontias-2023` | RESOLVED | nao | 1 | 2 | 8 | `ENRICH_CANDIDATE` |
| `pachydactylus-2025` | RESOLVED | nao | 2 | 11 | 10 | `ENRICH_CANDIDATE` |
| `serra-da-neve-checklist-2024` | RESOLVED | sim | 1 | 1 | 10 | - |
| `sao-tome-barcode-2023` | RESOLVED | sim | 1 | 1 | 10 | - |
| `cynoscion-regalis-2017` | GAP | nao | 9 | 0 | 12 | `DISCOVER_CANDIDATE` |
| `sao-tome-fishes-2019` | GAP | nao | - | 0 | 12 | `DISCOVER_CANDIDATE` |
| `ophichthus-rufus-2020` | RESOLVED | nao | 1 | 1 | 10 | `ENRICH_CANDIDATE` |
| `lipogenys-2024` | RESOLVED | nao | 1 | 1 | 10 | `ENRICH_CANDIDATE` |
| `xenopus-petersii-2024` | RESOLVED | sim | 1 | 1 | 10 | - |
| `nembrotha-cristata-2026` | GAP | nao | 1 | 2 | 10 | `DISCOVER_CANDIDATE` |
| `trichoniscoides-machadoi-2025` | GAP | nao | - | 0 | 12 | `DISCOVER_CANDIDATE` |

Metricas globais:

- casos que chegam a fila humana: `8/12 = 0,67`;
- recall de recuperacao, criterio antigo: `10/12 = 0,83`;
- candidatos acionaveis deduplicados: `21`;
- proxy de precisao sobre casos conhecidos: `8/21 = 0,38`;
- casos com evidencia primaria de inventario: `3/12 = 0,25`.

Por fonte:

| Fonte | Recuperados | Recall | Candidatos acionaveis | Proxy de precisao | Queries |
| --- | ---: | ---: | ---: | ---: | ---: |
| Crossref | 6 | 0,50 | 17 | 0,29 | 60 |
| Europe PMC | 6 | 0,50 | 4 | 0,75 | 64 |

As duas fontes recuperam seis casos cada, mas nao os mesmos. Europe PMC produz
muito menos ruido porque so ela devolve texto integral e, portanto, so ela
consegue confirmar inventario fora dos metadados.

## Casos de lacuna

Quatro casos nao chegam a fila humana, por dois motivos distintos:

- **nao recuperados**: `sao-tome-fishes-2019`, publicado na Cybium, e
  `trichoniscoides-machadoi-2025`, cujas entradas de material examinado usam
  exclusivamente a forma `MNHNC:MB11:001283`;
- **recuperados mas rejeitados pelo gate acionavel**: `cynoscion-regalis-2017`,
  na posicao 9, e `nembrotha-cristata-2026`, na posicao 1. Ambos citam o codigo
  de colecao sem prefixo institucional, pelo que nenhuma evidencia de inventario
  e extraida e nenhum outro sinal e suficiente.

O segundo grupo e o mais relevante: a publicacao correta esta no resultado da
pesquisa e ainda assim e descartada em silencio.

Cinco casos chegam a fila mas sem evidencia de inventario. Sao candidatos que o
staff recebe apoiado apenas em autor e taxon, que e exatamente a situacao que o
objetivo `ENRICH_CANDIDATE` existe para resolver.

## Juizo

A fixture deixou de estar saturada. A baseline de cinco casos recuperava cinco
de cinco e nao permitia demonstrar ganho algum; a fixture ampliada deixa quatro
lacunas de descoberta e cinco de enriquecimento, e E1 passa a ter alvo
mensuravel para os seus dois objetivos.

Das nove lacunas, cinco tem causa documentada no texto publicado e sao
alcancaveis pelo gerador de variantes de inventario:
`cynoscion-regalis-2017`, `ophichthus-rufus-2020`, `lipogenys-2024`,
`nembrotha-cristata-2026` e `trichoniscoides-machadoi-2025`. A verificacao de
que cada forma citada corresponde a uma variante gerada e automatica e corre com
os testes.

`sao-tome-fishes-2019` nao e alcancavel por variantes: a revista nao aparece nos
indices consultados com estes termos. Fica registada como lacuna de cobertura de
fonte, nao de formato, e e um argumento para avaliar novas fontes em E2 e E6.

As tres lacunas de enriquecimento mais antigas ficam com causa `UNKNOWN` porque
os artigos correspondentes nao foram inspecionados. O facto medido, ausencia de
evidencia de inventario, esta registado; a causa nao foi inventada.

## Reproducibilidade

O relatorio JSON completo, incluindo a `reviewQueue` com 21 candidatos por
classificar, e produzido pelo comando acima com `--output`. As declaracoes da
fixture sao recalculadas em cada execucao e qualquer divergencia aparece em
`baselineDeclarationMetrics.mismatched_case_ids`. Nesta execucao esse conjunto
esta vazio.
