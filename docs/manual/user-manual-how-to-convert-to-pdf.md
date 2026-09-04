---
status: current
---

# Como gerar o PDF do Manual do Utilizador

Este procedimento destina-se a agentes que precisem de atualizar
`vitarerum-manual-utilizador.pdf` depois de uma alteração ao manual ou às suas
imagens. A fonte de verdade é sempre o Markdown; o PDF é um artefacto derivado
e não deve ser editado diretamente.

## Ficheiros envolvidos

| Finalidade | Caminho |
| --- | --- |
| Fonte do conteúdo | [`user-manual.md`](./user-manual.md) |
| Imagens e infográficos | [`assets/`](./assets/) |
| PDF final | [`vitarerum-manual-utilizador.pdf`](./vitarerum-manual-utilizador.pdf) |
| Área de trabalho temporária | `tmp/pdfs/` |

Os quatro infográficos atualmente usados pelo manual são:

- `assets/infografico-submissao-publica.svg`;
- `assets/infografico-projeto.svg`;
- `assets/infografico-pergunte-museu.svg`;
- `assets/infografico-prompts-ia.svg`.

Não recupere os antigos diagramas técnicos para o manual do utilizador. Se o
fluxo funcional tiver mudado, atualize primeiro o texto e o respetivo
infográfico, verificando ambos contra a aplicação, as especificações e os
testes atuais.

## Regras para a geração

1. Leia integralmente `user-manual.md` e confirme que todos os recursos locais
   referidos no documento existem.
2. Leia e siga a *skill* de PDF disponível no ambiente do agente. Ela define o
   processo de geração, renderização e inspeção visual. Se não estiver
   disponível, aplique as verificações descritas neste documento.
3. Preserve a ordem e a hierarquia dos títulos, as tabelas, as listas, as notas,
   os links externos e a posição das imagens no Markdown.
4. Use formato A4, orientação vertical, margens adequadas à impressão, tipografia
   com suporte integral a Unicode/PT-PT, cabeçalho discreto e número de página.
5. Inclua capa, índice navegável, marcadores (*bookmarks*) e links clicáveis.
   Entradas do índice devem apontar para a secção correta dentro do PDF.
6. Dimensione as imagens proporcionalmente, sem as esticar, cortar ou tornar o
   texto ilegível. Nunca deixe uma legenda separada da imagem correspondente.
7. Evite títulos isolados no fim da página, páginas vazias, linhas órfãs e
   conteúdo sobreposto ao cabeçalho ou rodapé.
8. Gere primeiro um candidato em `tmp/pdfs/`. Substitua o PDF final apenas
   depois de todas as verificações passarem.

## Preparar o ambiente

Não instale dependências no ambiente global do projeto. Crie um ambiente
temporário e use um diretório de cache fora do repositório:

```sh
mkdir -p tmp/pdfs
UV_CACHE_DIR=/tmp/vitarerum-pdf-uv-cache uv venv tmp/pdfs/.venv
UV_CACHE_DIR=/tmp/vitarerum-pdf-uv-cache uv pip install \
  --python tmp/pdfs/.venv/bin/python \
  reportlab pymupdf pypdf pdfplumber pillow
```

Se as dependências já estiverem disponíveis, não é necessário reinstalá-las.
Uma falha de rede ou de permissões deve ser tratada pelo mecanismo de aprovação
do ambiente; não altere as dependências permanentes da aplicação por causa da
documentação.

O `rsvg-convert` pode ser usado para rasterizar os SVG quando a biblioteca de
PDF escolhida não os aceitar diretamente:

```sh
for source_svg in docs/manual/assets/infografico-*.svg; do
  rsvg-convert -w 1800 "$source_svg" \
    -o "tmp/pdfs/$(basename "${source_svg%.svg}").png"
done
```

Prefira incorporar os SVG diretamente quando a ferramenta preservar bem os
vetores. Caso seja necessária rasterização, use resolução suficiente para que
o texto continue nítido numa página A4 impressa.

## Gerar o documento

Use o conversor de documentos disponível no ambiente ou um gerador temporário
com ReportLab. O gerador deve interpretar, no mínimo:

- títulos de níveis 1 a 4;
- parágrafos, ênfase, código em linha e citações;
- listas ordenadas, listas não ordenadas e listas aninhadas;
- tabelas com repetição do cabeçalho quando ocuparem mais de uma página;
- links internos e externos;
- imagens nas posições em que aparecem no Markdown;
- quebras de página necessárias para manter blocos relacionados juntos.

Não codifique o conteúdo do manual no gerador. O texto, os títulos, os links e
as referências às imagens devem ser lidos de `user-manual.md`, para que futuras
alterações não exijam modificar o conversor.

Gere o candidato com este caminho:

```text
tmp/pdfs/vitarerum-manual-utilizador.pdf
```

Os metadados devem identificar o documento como **Manual do Utilizador —
Vitarerum**, indicar Vitarerum como autor institucional e usar a versão/data
declarada no início do Markdown. Não introduza uma data diferente apenas porque
o PDF foi novamente compilado.

## Verificar a aderência antes da conversão

Execute as verificações de documentação do repositório:

```sh
python3 scripts/check_docs.py --links --tests
```

Se uma alteração afetar um fluxo apresentado num infográfico, confronte-a com
as especificações em `docs/specs/`, com o código e com os testes do contexto
correspondente. O desenho deve simplificar o fluxo para o utilizador final sem
inventar estados, permissões ou resultados.

## Verificar o PDF candidato

A existência do ficheiro não basta. Faça todas estas verificações:

1. Abra o PDF com `pypdf` ou PyMuPDF e confirme que não está corrompido, que tem
   metadados, índice/marcadores e anotações de link.
2. Confirme que os links externos do Markdown permanecem clicáveis e que cada
   entrada do índice conduz à secção esperada.
3. Extraia o texto com `pdfplumber` ou PyMuPDF e procure páginas sem texto nem
   imagem, caracteres substituídos e secções ausentes.
4. Renderize **todas** as páginas como PNG com PyMuPDF ou Poppler. Inspecione uma
   folha de contacto e, em tamanho legível, a capa, o índice, todas as tabelas e
   todas as páginas com infográficos.
5. Confirme visualmente que não há cortes, sobreposições, texto minúsculo,
   imagens deformadas, páginas vazias ou quebras de página inadequadas.
6. Execute `git diff --check` para detetar problemas de formatação nos ficheiros
   de origem alterados.

Exemplo de renderização com PyMuPDF:

```sh
tmp/pdfs/.venv/bin/python -c '
import pathlib
import fitz

source = pathlib.Path("tmp/pdfs/vitarerum-manual-utilizador.pdf")
target = pathlib.Path("tmp/pdfs/rendered")
target.mkdir(parents=True, exist_ok=True)
with fitz.open(source) as document:
    for number, page in enumerate(document, start=1):
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        pixmap.save(target / f"page-{number:03}.png")
'
```

Use a ferramenta de visualização de imagens do ambiente para inspecionar os
PNG. Não considere a validação concluída apenas com extração automática de
texto.

## Publicar a versão validada

Depois de o candidato passar por todas as verificações, copie-o para o destino
final:

```sh
cp tmp/pdfs/vitarerum-manual-utilizador.pdf \
  docs/manual/vitarerum-manual-utilizador.pdf
```

Faça uma última leitura do PDF no destino final e confirme no `git status` que
apenas os ficheiros esperados foram alterados. Os artefactos de `tmp/pdfs/` são
temporários e não devem ser adicionados ao repositório.

## Critério de conclusão

A atualização está concluída somente quando:

- o PDF foi gerado a partir da versão atual de `user-manual.md`;
- texto e infográficos estão aderentes ao comportamento atual da aplicação;
- índice, marcadores e links funcionam;
- todas as páginas foram renderizadas e inspecionadas visualmente;
- não existem cortes, sobreposições, páginas vazias ou imagens ilegíveis;
- o ficheiro validado está em `docs/manual/vitarerum-manual-utilizador.pdf`;
- os ficheiros temporários não foram incluídos no controlo de versão.
