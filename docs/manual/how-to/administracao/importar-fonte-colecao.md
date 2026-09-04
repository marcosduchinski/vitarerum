---
status: current
---

# Como importar e mapear uma fonte de coleção

## Objetivo

Carregar um ficheiro XLSX, mapear as colunas que identificam os objetos e
disponibilizar os registos na pesquisa.

**Disponível para:** SYS_ADMIN e COLLECTIONS_MANAGEMENT em qualquer coleção;
CURATORIAL apenas nas coleções em que é curador

**Onde começar:** **“Administration”** > **“Collection Data Sources”**

**Tempo aproximado:** 10 minutos, além do tempo de indexação

## Antes de começar

- Prepare um `.xlsx` com cabeçalhos claros e uma linha por objeto.
- Confirme a área e a coleção de destino.
- Identifique a coluna canónica do número de inventário e as colunas úteis para
  pesquisa.

## Passo a passo

1. Abra a coleção de destino.
2. Selecione **“Upload .xlsx”** e escolha o ficheiro.
3. Em **“Configure columns”**, reveja as colunas detetadas.
4. Escolha **“Inventory number”** — obrigatório e único por registo.
5. Em **“Display title”**, selecione uma ou mais colunas para formar o título.
6. Escolha **“Object name”** ou mantenha **“Use display title”**.
7. Marque as **“Description columns”** relevantes.
8. Em **“Searchable columns”**, marque pelo menos uma coluna; inclua apenas
   campos que devam participar na pesquisa.
9. Selecione **“Upload and index”** e aguarde o estado **“INDEXED”**.
10. Pesquise alguns números, nomes e códigos em **“Objects”** > **“Search”** para
    validar o resultado.

## Resultado esperado

O documento aparece na coleção com o mapeamento **“Configured”**, contagem de
linhas e estado **“INDEXED”**. Os objetos podem ser encontrados e associados a
propostas e projetos.

## Atenção

> Um ficheiro com o mesmo nome e conteúdo diferente substitui a versão
> anterior. Um ficheiro idêntico é deduplicado sem criar outra cópia.

> O mapeamento determina a identificação e a pesquisa futuras. Valide amostras
> antes de considerar a importação concluída.

## Se algo não funcionar

| Situação | O que verificar ou fazer |
| --- | --- |
| **“Upload and index”** está indisponível | Escolha número de inventário, título e pelo menos uma coluna pesquisável |
| O documento fica **“ERROR”** | Leia a mensagem, corrija o ficheiro ou mapeamento e use a reindexação |
| **“Upload .xlsx”** não aparece | Confirme as permissões sobre a coleção e o papel ativo |
| A pesquisa não encontra uma coluna | Confirme se ela foi marcada em **“Searchable columns”** |

## Tarefas relacionadas

- [Corrigir e reindexar uma fonte de coleção](reindexar-fonte-colecao.md)
- [Pesquisar e associar objetos](../equipa-museu/pesquisar-associar-objetos.md)
- [Manual do Utilizador — fontes de coleção](../../user-manual.md#26-fontes-de-dados-de-coleção-padmincollection-data-sources)
- [Índice dos guias práticos](../README.md)
