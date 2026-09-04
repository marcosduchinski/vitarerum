---
status: current
---

# Como criar, testar e publicar uma versão de prompt

## Objetivo

Preparar uma nova versão das instruções usadas pela IA, testá-la quando o banco
de testes estiver disponível e publicá-la com histórico auditável.

**Disponível para:** COLLECTIONS_MANAGEMENT, CURATORIAL e DIRECTION

**Onde começar:** **“AI”** > **“Prompts”**

**Tempo aproximado:** 15 minutos, além do tempo de teste

## Antes de começar

- Identifique a finalidade do prompt: narrativa de visita ou retorno científico.
- Para testar narrativas, tenha um projeto de visita in situ concluído.
- Prepare critérios objetivos para avaliar o resultado antes de publicar.

## Criar um rascunho

1. Abra o prompt e entre em **“Edit prompt”**.
2. Para partir da versão ativa, selecione **“Duplicate active”**; para começar
   do zero, escreva diretamente em **“Content”**.
3. Preencha **“Version label”** com uma identificação útil.
4. Defina **“Temperature”** entre 0 e 1. Valores baixos são mais consistentes;
   valores altos permitem mais variação.
5. Selecione **“Create draft”**.

## Testar uma narrativa

1. No **“Test bench”**, escolha **“Completed in-situ project”**.
2. Confirme o projeto ou registo apresentado e indique **“Language”**.
3. Selecione **“Test”**. Para testar um rascunho já guardado no histórico, use
   **“Preview”** junto dessa versão.
4. Reveja o resultado, o modelo, a temperatura e a validação apresentada.
5. Ajuste o conteúdo e crie outro rascunho se o resultado não cumprir os
   critérios definidos.

O banco de testes está disponível para prompts de narrativa in situ; não deve
ser presumido para todas as finalidades.

## Publicar ou arquivar

1. Em **“Version history”**, confirme o rótulo e abra **“Content”** para rever a
   versão correta.
2. Selecione **“Publish”** no rascunho aprovado.
3. Confirme que a versão aparece como **“Published”** e que a anterior passou a
   **“Archived”**.
4. Para retirar um rascunho que não será usado, selecione **“Archive”**.

## Resultado esperado

A versão publicada torna-se a instrução ativa para as gerações seguintes dessa
finalidade. As versões anteriores permanecem em **“Version history”** com autor
e datas.

## Atenção

> Publicar afeta as gerações seguintes em todo o sistema e arquiva
> automaticamente a versão anteriormente ativa. Teste e faça revisão por pares
> antes de publicar.

> Não introduza dados pessoais, segredos, credenciais ou instruções fora da
> finalidade institucional no conteúdo do prompt.

## Se algo não funcionar

| Situação | O que verificar ou fazer |
| --- | --- |
| **“Create draft”** está indisponível | Preencha o conteúdo e o rótulo e use temperatura entre 0 e 1 |
| **“Test”** está indisponível | Confirme que é um prompt de narrativa e selecione um projeto concluído |
| O teste falha ou demora | Não publique com base num resultado incompleto; aguarde ou tente mais tarde |
| A versão anterior ficou arquivada | É o comportamento esperado quando uma nova versão é publicada |

## Tarefas relacionadas

- [Criar, rever e exportar um relatório de visita in situ](relatorio-visita-in-situ.md)
- [Manual do Utilizador — prompts de IA](../../user-manual.md#17-prompts-de-ia-paiprompts)
- [Índice dos guias práticos](../README.md)
