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
