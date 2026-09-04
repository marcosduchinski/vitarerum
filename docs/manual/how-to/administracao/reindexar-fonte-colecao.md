---
status: current
---

# Como corrigir e reindexar uma fonte de coleção

## Objetivo

Corrigir o mapeamento de um ficheiro de coleção ou reconstruir o índice depois
de um erro ou de uma alteração de colunas.

**Disponível para:** SYS_ADMIN e COLLECTIONS_MANAGEMENT em qualquer coleção;
CURATORIAL apenas nas coleções em que é curador

**Onde começar:** **“Administration”** > **“Collection Data Sources”**

**Tempo aproximado:** 5 a 15 minutos

## Antes de começar

Leia o estado e a mensagem de erro do documento. Guarde uma cópia do ficheiro
de origem e identifique o mapeamento correto antes de alterar o índice.

## Corrigir o mapeamento

1. Abra a coleção e localize o documento.
2. Selecione **“Configure columns”**.
3. Corrija **“Inventory number”**, **“Display title”**, **“Object name”**,
   **“Description columns”** e **“Searchable columns”**.
4. Selecione **“Save mapping”**.
5. Selecione **“Reindex”** para reconstruir as linhas pesquisáveis.
6. Aguarde **“INDEXED”** e teste a pesquisa de uma amostra conhecida.

Se o problema estiver no conteúdo do XLSX, corrija o ficheiro original e
carregue a versão corrigida com o mesmo nome; depois confirme o mapeamento.

## Remover um documento

Selecione **“Delete”** apenas quando o documento já não deve alimentar a
pesquisa. A remoção retira também as linhas correspondentes do índice.

## Resultado esperado

O documento apresenta estado **“INDEXED”**, datas atualizadas e mapeamento
**“Configured”**. As pesquisas devolvem os campos esperados.

## Atenção

> Reindexar substitui as linhas pesquisáveis derivadas desse ficheiro. Teste
> números de inventário e nomes representativos depois da operação.

> **“Delete”** remove o documento da pesquisa. Confirme a coleção e o ficheiro
> antes de executar a ação.

## Se algo não funcionar

| Situação | O que verificar ou fazer |
| --- | --- |
| **“Save mapping”** está indisponível | Preencha os campos obrigatórios e selecione pelo menos uma coluna pesquisável |
| A reindexação volta a **“ERROR”** | Reveja a mensagem, o limite de linhas, os cabeçalhos e os valores do XLSX |
| As pesquisas antigas continuam erradas | Confirme que reindexou depois de guardar o novo mapeamento |
| Não pode gerir o documento | Confirme se tem permissão sobre a coleção com o papel ativo |

## Tarefas relacionadas

- [Importar e mapear uma fonte de coleção](importar-fonte-colecao.md)
- [Pesquisar e associar objetos](../equipa-museu/pesquisar-associar-objetos.md)
- [Manual do Utilizador — reindexação](../../user-manual.md#26-fontes-de-dados-de-coleção-padmincollection-data-sources)
- [Índice dos guias práticos](../README.md)
