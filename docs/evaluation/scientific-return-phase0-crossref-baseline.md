---
status: current
---

# Baseline Crossref do retorno cientifico

Data: 2026-08-14

## Configuracao

- fonte: Crossref;
- casos conhecidos: 5;
- limite: 10 resultados por query;
- estrategias exatas: inventario, autor + inventario, inventario + objeto e
  autor + objeto;
- adaptacao: inventario + genero e autor + genero somente quando as quatro
  estrategias exatas nao produziram candidato acionavel;
- erros HTTP: nenhum nas 24 chamadas realizadas.

Comando:

```bash
uv run python -m app.scientific_return.presentation.commands \
  evaluate-phase0 --result-limit 10
```

## Resultado

| Caso | Recuperado | Melhor posicao | Candidatos acionaveis | Queries |
| --- | ---: | ---: | ---: | ---: |
| `rhoptropus-2025` | sim | 1 | 1 | 4 |
| `acontias-2023` | sim | 1 | 1 | 4 |
| `pachydactylus-2025` | sim | 2 | 9 | 4 |
| `serra-da-neve-checklist-2024` | nao | - | 0 | 6 |
| `sao-tome-barcode-2023` | nao | - | 0 | 6 |

Metricas:

- recall conhecido: `3/5 = 0,60`;
- candidatos acionaveis deduplicados: `11`;
- proxy de precisao sobre casos conhecidos: `3/11 = 0,273`.

A proxy nao substitui precisao revista por humanos. Ela considera correto apenas
o DOI esperado de cada fixture e deve ser recalculada depois da classificacao
dos demais candidatos pelo staff.

## Juizo

Crossref recupera bem os tres artigos taxonomicos especificos, mas nao recupera
os dois trabalhos em que o specimen ID esta apenas no texto integral ou numa
tabela extensa. Ampliar o taxon para o genero nao resolveu esses dois casos.

O caso `pachydactylus-2025` gerou nove candidatos acionaveis para um resultado
conhecido. Portanto, `autor + objeto` e coincidencia de genero precisam continuar
sob revisao humana e devem ser comparados com filtros de uma segunda fonte.

Decisao inicial:

- manter Crossref para descoberta e enriquecimento por DOI;
- medir OpenAlex com a mesma baseline quando a API key estiver configurada;
- priorizar uma fonte de texto integral para os casos ZooKeys;
- nao ampliar a autonomia de confirmacao enquanto a precisao humana nao estiver
  medida;
- preservar o gate humano e a explicacao por evidencia.

## Evidencia dos objetos das fixtures

O texto integral aberto confirma `Afroedura praedicta` para
`MUNHAC/MB03-001552` no [checklist da Serra da Neve](https://pmc.ncbi.nlm.nih.gov/articles/PMC11109511/)
e `Leptopelis palmatus` para `MB04-000792` na [biblioteca de DNA barcodes de Sao
Tome e Principe](https://pmc.ncbi.nlm.nih.gov/articles/PMC10320720/).

## Comparacao Crossref + Europe PMC

Atualizacao executada em 2026-08-16 com limite de 10 resultados por query.
A Europe PMC foi avaliada com metadados `core` e enriquecimento transitorio pelo
XML de texto integral aberto. O texto integral e usado apenas para extrair
evidencias e nao e persistido no candidato.

Comando:

```bash
uv run python -m app.scientific_return.presentation.commands \
  evaluate-phase0 \
  --sources crossref,europe_pmc \
  --result-limit 10 \
  --output /caminho/seguro/scientific-return-phase0-review.json
```

Resultado por fonte:

| Fonte | Recuperados | Recall | Candidatos acionaveis | Casos conhecidos acionaveis | Proxy conhecida | Queries | Erros |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Crossref | 3/5 | 0,60 | 11 | 3 | 0,273 | 24 | 0 |
| Europe PMC | 3/5 | 0,60 | 3 | 2 | 0,667 | 24 | 0 |
| Combinado e deduplicado | 5/5 | 1,00 | 14 | 5 | 0,357 | 48 | 0 |

A uniao das fontes recuperou os cinco casos conhecidos. A Europe PMC tornou
acionaveis, por evidencia no texto integral, o checklist da Serra da Neve e a
biblioteca de DNA barcodes de Sao Tome e Principe. Tambem criou um candidato
adicional para o caso `acontias-2023`: o checklist da Serra da Neve menciona o
inventario e o taxon correspondentes no texto integral e precisa de avaliacao
curatorial, pois nao e o DOI conhecido usado como ground truth da fixture.

O relatorio agora inclui:

- metricas separadas por fonte;
- trajetorias e erros por caso;
- candidatos deduplicados com evidencias e origem da evidencia;
- `review_id` estavel por caso e candidato;
- campos `human_decision`, `human_justification`, `reviewer` e `reviewed_at`;
- cobertura e precisao da revisao humana.

O staff deve preencher `human_decision` com `CONFIRMED`, `DISMISSED` ou
`UNCERTAIN`, sempre com justificacao, revisor e data. Depois, a avaliacao pode
ser repetida usando o relatorio revisto:

```bash
uv run python -m app.scientific_return.presentation.commands \
  evaluate-phase0 \
  --reviews /caminho/seguro/scientific-return-phase0-review.json \
  --output /caminho/seguro/scientific-return-phase0-reviewed.json
```

Essa finalizacao nao repete chamadas externas: preserva as trajetorias do
relatorio revisto e apenas valida as decisoes e recalcula as metricas humanas.

A precisao humana permanece pendente ate essa classificacao. A baseline
OpenAlex tambem permanece pendente porque o ambiente da execucao nao possuia
`OPENALEX_API_KEY` configurada. O avaliador aceita `--sources all` e inclui
OpenAlex automaticamente quando a chave estiver disponivel.
