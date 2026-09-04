---
status: current
---

# Como publicar e revogar um acesso externo

## Objetivo

Emitir um link tokenizado para um recurso aprovado, limitar os dados expostos e
revogar o acesso quando necessário.

**Disponível para:** SYS_ADMIN

**Onde começar:** **“Administration”** > **“External Resource Access”**

**Tempo aproximado:** 5 minutos

## Antes de começar

Confirme que o recurso está aprovado para divulgação, qual o perfil mínimo de
dados necessário, quem receberá o link e se deve existir uma expiração.

## Publicar um link

1. Selecione **“Publish resource”**.
2. Em **“Type”**, escolha a família do recurso e selecione **“Continue”**.
3. Em **“Resource”**, pesquise por referência, título, código de visita ou ID,
   selecione o resultado correto e avance.
4. Em **“Access”**, escolha o perfil que expõe apenas o necessário.
5. Se aplicável, preencha **“Expiration”**. O perfil **“JSON_LD”** só está
   disponível para relatórios de visita in situ.
6. Selecione **“Review”** e confirme tipo, recurso, perfil e expiração.
7. Selecione **“Publish externally”**.
8. Copie o URL tokenizado apresentado e transmita-o por um canal adequado.

## Consultar e revogar

1. Em **“Published links”**, pesquise pelo ID da publicação ou do recurso e use
   os filtros de tipo, estado e perfil.
2. Use **“Copy external URL”** para voltar a copiar um link ativo.
3. Para o invalidar, selecione **“Revoke publication”** e confirme a revogação.

## Resultado esperado

O link aparece no registo com o perfil, estado e expiração escolhidos. Depois
da revogação, o mesmo URL deixa de permitir acesso.

## Atenção

> O URL contém um token de acesso. Trate-o como informação sensível: não o
> publique em documentação, código, capturas ou canais abertos.

> Revogar é irreversível. Para voltar a partilhar o recurso, terá de publicar
> um novo link, com outro token.

## Se algo não funcionar

| Situação | O que verificar ou fazer |
| --- | --- |
| O recurso não aparece | Confirme que pertence ao tipo escolhido e está elegível para publicação |
| **“JSON_LD”** está indisponível | Selecione um relatório de visita in situ ou escolha outro perfil |
| **“Publish externally”** está indisponível | Complete recurso, perfil e revisão; corrija uma expiração inválida |
| Um link revogado não pode ser reativado | Publique um novo acesso externo e distribua o novo URL |

## Tarefas relacionadas

- [Criar, rever e exportar um relatório de visita in situ](../equipa-museu/relatorio-visita-in-situ.md)
- [Manual do Utilizador — acesso a recursos externos](../../user-manual.md#28-acesso-a-recursos-externos-padminexternal-publications)
- [Índice dos guias práticos](../README.md)
