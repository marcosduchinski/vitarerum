---
status: current
---

# Como recuperar, redefinir ou alterar a password

## Objetivo

Recuperar o acesso quando não se lembra da password ou alterá-la em segurança
durante uma sessão iniciada.

**Disponível para:** qualquer utilizador com conta

**Onde começar:** `/login` para recuperação, ou menu do utilizador para alteração

**Tempo aproximado:** 5 minutos, sem contar a entrega do email

## Recuperar uma password esquecida

1. No login, selecione **“Forgot password?”**.
2. Preencha **“Email address”** e selecione **“Send reset link”**.
3. A página confirma o pedido sem revelar se existe uma conta para esse email.
4. Abra apenas o email esperado e selecione o link de reposição.
5. Preencha **“New password”** e **“Confirm new password”** com o mesmo valor.
6. Selecione **“Reset password”** e depois **“Back to sign in”**.

Se o link estiver ausente, inválido, expirado ou já tiver sido usado, selecione
**“Request a new reset link”**.

## Alterar durante uma sessão

1. Abra o menu do utilizador na barra superior.
2. Selecione **“Change password”**.
3. Preencha **“Current password”**, **“New password”** e **“Confirm new
   password”**.
4. Selecione **“Change password”**.
5. Inicie novamente a sessão com a nova password.

A password deve ter entre 5 e 128 carateres.

## Resultado esperado

A nova password substitui a anterior. Na alteração autenticada, a sessão é
terminada e a aplicação pede novo login.

## Atenção

> Não partilhe links de reposição nem passwords. Confirme o endereço e o domínio
> da aplicação antes de introduzir uma nova credencial.

> O sistema nunca mostra nem reenvia a password existente. Um administrador
> pode apenas iniciar o envio de um email de reposição.

## Se algo não funcionar

| Situação | O que verificar ou fazer |
| --- | --- |
| O email não chega | Confirme a caixa de spam e o endereço; aguarde antes de pedir outro link |
| O link é inválido ou expirou | Use **“Request a new reset link”** e abra apenas o email mais recente |
| **“Reset password”** está indisponível | Confirme o tamanho e se os dois campos coincidem |
| A password atual é recusada | Use o fluxo **“Forgot password?”** em vez de repetir tentativas |

## Tarefas relacionadas

- [Manual do Utilizador — acesso ao sistema](../../user-manual.md#3-acesso-ao-sistema)
- [Índice dos guias práticos](../README.md)
