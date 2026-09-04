---
status: current
---

# Como criar um utilizador e atribuir-lhe um grupo

## Objetivo

Criar uma conta, atribuir os papéis necessários e gerir o acesso sem eliminar o
histórico do utilizador.

**Disponível para:** SYS_ADMIN

**Onde começar:** **“Administration”** > **“Users”**

**Tempo aproximado:** 5 minutos

## Antes de começar

Confirme o nome, o email institucional ou validado e o grupo autorizado. Uma
conta sem grupo não consegue iniciar sessão.

## Criar e ativar o acesso

1. Em **“Users”**, selecione a ação de criar utilizador.
2. Preencha **“Name”**, **“Email”** e **“Password”** inicial.
3. Selecione **“Create user”**.
4. No detalhe criado, vá a **“Assign to group”**.
5. Em **“Select group...”**, escolha o papel e selecione **“Assign”**.
6. Repita apenas para outros papéis efetivamente autorizados.

Comunique a password inicial por um canal apropriado e peça ao utilizador para
a alterar no primeiro acesso.

## Manter a conta

- Use **“Edit name”** para corrigir o nome.
- Use **“Send password reset”** para enviar um link de reposição; a password
  atual não é revelada nem reenviada.
- Use **“Disable user”** para bloquear o login sem apagar o histórico e
  **“Enable user”** para reativar.
- Em **“Group memberships”**, use **“Revoke”** e confirme **“Remove”** para
  retirar imediatamente um papel.

## Resultado esperado

O utilizador aparece na lista e, depois de receber pelo menos um grupo, pode
iniciar sessão com as permissões correspondentes. Desativação e revogação
produzem efeito imediato sem eliminar os registos históricos.

## Atenção

> Atribua apenas os papéis necessários. **“Revoke”** retira imediatamente esse
> acesso; **“Disable user”** bloqueia todos os acessos da conta.

> Nunca envie passwords por documentação, tickets públicos ou mensagens sem
> proteção adequada.

## Se algo não funcionar

| Situação | O que verificar ou fazer |
| --- | --- |
| **“Create user”** está indisponível | Preencha nome, email válido e password dentro das regras apresentadas |
| O utilizador não consegue entrar | Confirme que a conta está ativa e possui pelo menos um grupo |
| Um grupo não aparece na atribuição | Pode já estar atribuído ao utilizador |
| O email de reposição não chega | Confirme o endereço e tente **“Send password reset”**; não crie outra conta para o mesmo utilizador |

## Tarefas relacionadas

- [Recuperar, redefinir ou alterar a password](../tarefas-comuns/gerir-password.md)
- [Manual do Utilizador — gestão de utilizadores](../../user-manual.md#22-gestão-de-utilizadores-padminusers)
- [Índice dos guias práticos](../README.md)
