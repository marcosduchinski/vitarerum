---
status: current
---

# Como [realizar uma tarefa concreta]

> Modelo editorial para os guias práticos do Vitarerum. Ao criar um guia,
> substitua todo o conteúdo entre parênteses retos e remova estas instruções.

## Objetivo

[Explique em uma ou duas frases o resultado que a pessoa obterá. Comece por um
verbo no infinitivo e não descreva a implementação técnica.]

**Disponível para:** [Público sem autenticação | EXTERNAL |
COLLECTIONS_MANAGEMENT | CURATORIAL | DIRECTION | SYS_ADMIN]

**Onde começar:** [Menu > Submenu > Página, ou URL pública]

**Tempo aproximado:** [por exemplo: 5 minutos, sem contar o tempo de resposta
do museu]

## Antes de começar

- [Pré-requisito funcional, documento ou informação necessária.]
- [Estado em que o recurso deve estar, quando aplicável.]
- [Permissão ou papel ativo necessário.]

Se não houver pré-requisitos além do acesso normal à página, indique isso numa
frase e remova a lista.

## Passo a passo

1. Aceda a **[nome do menu]** e escolha **[nome do item]**.
2. [Descreva uma ação observável e mencione o rótulo real do campo ou botão.]
3. [Apresente uma decisão ou preenchimento por passo, sempre que possível.]
4. Selecione **[nome exato do botão de confirmação]**.

Use os nomes exibidos pela aplicação entre aspas ou em negrito. Se a interface
autenticada apresentar um rótulo em inglês, conserve-o e explique-o em
português na primeira ocorrência, por exemplo: **“Assign to me”** (atribuir a
mim).

```text
Imagem: assets/nome-da-imagem.png
Texto alternativo: descrição objetiva do que a imagem permite identificar.
Legenda: Figura 1 — momento da tarefa representado na imagem.
```

Inclua imagens apenas quando ajudarem a localizar uma ação, compreender vários
campos ou evitar um erro. Não use uma captura para repetir um único botão que o
texto já identifica claramente.

## Resultado esperado

[Descreva o que aparece no ecrã, a mudança de estado e, quando aplicável, a
notificação ou email enviado. A pessoa deve conseguir confirmar objetivamente
que terminou a tarefa.]

## Atenção

> [Explique consequências irreversíveis, efeitos noutros recursos, perda de
> acesso ou restrições de estado. Remova esta secção quando não houver um alerta
> relevante.]

## Se algo não funcionar

| Situação | O que verificar ou fazer |
| --- | --- |
| [Mensagem ou sintoma visível] | [Causa provável e ação segura recomendada] |
| [Botão indisponível ou ausente] | [Papel, estado ou pré-requisito necessário] |

Não exponha mensagens internas, detalhes de infraestrutura ou procedimentos
destinados apenas a programadores. Encaminhe falhas não recuperáveis para o
canal institucional indicado no manual.

## Tarefas relacionadas

- [Nome de outro guia — adicionar a ligação apenas quando o ficheiro existir.]
- [Secção relevante do Manual do Utilizador](../user-manual.md)

Só mantenha ligações para ficheiros que já existam. Enquanto um guia relacionado
estiver planeado, escreva o seu nome sem criar um link.

<!--
Notas de manutenção para agentes — remover do guia publicado:

1. Verificar a rota, o menu e os nomes dos controlos no frontend atual.
2. Verificar permissões, estados, efeitos e limites nas especificações, no
   backend e nos testes.
3. Executar `python3 scripts/check_docs.py --links --tests` a partir da raiz do
   repositório.
4. Usar apenas dados fictícios nas capturas de ecrã.
5. Verificar a captura em tamanho de página A4 e num ecrã estreito quando o
   procedimento estiver disponível em dispositivos móveis.
6. Escrever em PT-PT, evitar linguagem técnica e dirigir-se à pessoa de forma
   consistente.
7. Confirmar que o guia explica uma tarefa completa, e não apenas uma página ou
   funcionalidade.
-->
