---
status: current
---

# Como criar, testar e ativar uma máscara de referência

## Objetivo

Definir o formato das novas referências, testar uma amostra e ativar a política
correta sem perder o histórico.

**Disponível para:** SYS_ADMIN

**Onde começar:** **“Administration”** > **“Reference number masks”**

**Tempo aproximado:** 5 minutos

## Antes de começar

Escolha o tipo de referência e defina se a sequência deve reiniciar por dia,
mês, ano ou nunca. A máscara termina obrigatoriamente numa sequência de `X`,
com até 12 posições.

## Passo a passo

1. Escolha **“Reference type”**.
2. Escreva **“Mask”** usando texto fixo, tokens opcionais `YYYY`, `YY`, `MM` e
   `DD`, e uma sequência final de `X`.
3. Indique **“Preview date”**.
4. Selecione **“Preview”** e confira o exemplo e o âmbito da sequência.
5. Selecione **“Create draft”**.
6. Localize o rascunho no grupo correto e selecione **“Activate”**.
7. Confirme que só a máscara pretendida aparece **“Active”**.

Use **“Deactivate”** apenas quando pretende deixar esse tipo sem a política
ativa correspondente.

## Resultado esperado

As novas entidades desse tipo recebem referências segundo a máscara ativa. As
referências existentes e as políticas anteriores permanecem inalteradas no
histórico.

## Atenção

> Ativar uma máscara muda a numeração das entidades criadas depois desse
> momento. Valide a amostra, o reinício da sequência e o tipo selecionado.

> Só são permitidos letras, dígitos, barras, underscores e hífens, além dos
> tokens reconhecidos; a sequência de `X` deve ser o último token.

## Se algo não funcionar

| Situação | O que verificar ou fazer |
| --- | --- |
| **“Preview”** está indisponível | Selecione o tipo, preencha uma máscara válida e indique a data |
| A amostra reinicia no período errado | Reveja os tokens de data presentes na máscara |
| **“Activate”** falha | Atualize a lista e confirme se outra alteração ocorreu entretanto |
| Uma referência antiga não mudou | É o comportamento esperado; máscaras não renumeram registos existentes |

## Tarefas relacionadas

- [Manual do Utilizador — máscaras de referência](../../user-manual.md#27-máscaras-de-número-de-referência-padminreference-number-policies)
- [Índice dos guias práticos](../README.md)
