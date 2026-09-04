---
status: current
---

# Como gerir modelos de documentos

## Objetivo

Publicar e manter os modelos DOCX apresentados aos proponentes conforme o tipo
de utilização das coleções.

**Disponível para:** SYS_ADMIN; o servidor também autoriza
COLLECTIONS_MANAGEMENT, CURATORIAL e DIRECTION pelo URL direto

**Onde começar:** **“Administration”** > **“Document templates”**

**Tempo aproximado:** 5 minutos por modelo

## Antes de começar

Prepare um ficheiro `.docx` válido, sem dados reais de requerentes, e confirme o
tipo de utilização e a ordem de apresentação.

## Adicionar um modelo

1. Em **“Add a template”**, escolha **“Use type”**.
2. Preencha **“Title”** e, opcionalmente, **“Description”**.
3. Indique **“Display order”** e escolha **“File (.docx)”**.
4. Marque **“Mandatory”** se quiser sinalizá-lo como obrigatório e **“Active”**
   se deve ficar imediatamente disponível.
5. Selecione **“Add template”**.

A indicação **“Mandatory”** é atualmente informativa: a submissão ainda não
impede o envio quando esse ficheiro falta.

## Atualizar ou retirar

- Use **“Edit”** para alterar título, descrição, ordem, obrigatoriedade ou estado
  e selecione **“Save”**.
- Use **“Replace file”** para trocar apenas o DOCX, mantendo a configuração.
- Desmarque **“Active”** para retirar imediatamente o modelo dos formulários sem
  apagar o histórico.
- Use **“Delete”** apenas para eliminar definitivamente o modelo e o ficheiro.

## Resultado esperado

Modelos ativos aparecem no formulário público e autenticado do tipo de uso
correspondente, pela ordem configurada. Modelos inativos deixam de estar
disponíveis para descarga.

## Atenção

> **“Delete”** é definitivo. Prefira desativar quando o modelo pode voltar a ser
> necessário ou quando o histórico deve ser preservado.

> A extensão não é a única validação: o conteúdo deve ser um DOCX válido.

## Se algo não funcionar

| Situação | O que verificar ou fazer |
| --- | --- |
| **“Add template”** está indisponível | Preencha título, tipo, ordem e selecione um DOCX válido |
| O modelo não aparece no formulário | Confirme **“Active”**, o **“Use type”** e a ordem |
| A substituição é recusada | Abra e volte a guardar o ficheiro como DOCX antes de repetir |
| Um papel de equipa não encontra o menu | Aceda diretamente a `/p/admin/document-templates`; o menu completo é de SYS_ADMIN |

## Tarefas relacionadas

- [Manual do Utilizador — modelos de documentos](../../user-manual.md#25-modelos-de-documentos-padmindocument-templates)
- [Índice dos guias práticos](../README.md)
