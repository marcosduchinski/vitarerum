---
status: current
---

# Padrões das imagens dos guias práticos

Este diretório guarda as imagens usadas pelos guias em `docs/manual/how-to/`.
As imagens devem ajudar a executar uma tarefa; não devem servir apenas como
decoração nem substituir instruções escritas.

## Escolher o tipo de imagem

Use uma **captura de ecrã** para mostrar onde se encontra um controlo, quais
campos devem ser preenchidos ou qual confirmação aparece depois de uma ação.

Use um **infográfico** para explicar uma escolha, uma sequência com vários
ecrãs ou uma mudança de estado que não seja compreensível numa única captura.
O infográfico deve usar linguagem do utilizador final, sem componentes de
software, APIs, bases de dados ou outros elementos técnicos.

Não é necessário incluir uma imagem quando o passo identifica claramente um
único menu ou botão.

## Como as capturas atuais são produzidas

As imagens deste diretório não são feitas à mão: são geradas por
`vitarerum-ui/e2e/capture-manual-screenshots.spec.ts`, que conduz a aplicação
com a API e a autenticação *mock* em memória.

```sh
cd vitarerum-ui
npx playwright test e2e/capture-manual-screenshots.spec.ts
```

Cada `test` dessa spec começa por um comentário com a rota, o papel ativo e o
estado do recurso que a captura exige — é a forma de manter esse registo junto
do código que o reproduz, em vez de depender da descrição de um *commit*. Ao
alterar a interface, volte a correr o comando e reveja as imagens alteradas.

Se acrescentar uma imagem por outro meio, aplique na mesma as regras abaixo.

## Origem e segurança dos dados

- Prefira gerar a captura pela spec acima; se a produzir manualmente, use uma
  execução local da aplicação com serviços *mock* ou dados de demonstração.
- Use apenas nomes, emails, referências, documentos e conteúdos fictícios.
- Nunca mostre passwords, tokens, chaves, cabeçalhos HTTP, URLs assinados ou
  dados pessoais reais.
- Feche menus, separadores e aplicações que não pertençam ao Vitarerum antes de
  capturar o ecrã.
- Verifique metadados e nomes dos ficheiros antes de os adicionar ao
  repositório.

Desfocar informação sensível é uma medida de último recurso. Se uma captura
contiver dados que exigem desfoque, prefira recriá-la com dados fictícios.

## Estado da aplicação

Cada captura deve representar uma situação reproduzível. Para as imagens
geradas pela spec, esse registo vive no comentário de cada `test`; para uma
imagem produzida de outra forma, registe na descrição do *commit* ou da
revisão:

- rota apresentada;
- papel ativo;
- estado do recurso;
- conjunto de dados *mock* ou cenário de teste usado;
- largura aproximada da janela.

Antes de capturar, confirme os rótulos, permissões e efeitos da ação contra o
frontend, as especificações e os testes atuais. A aparência visual de um botão
não prova que a tarefa esteja disponível para aquele papel.

## Formato e dimensões

| Uso | Formato preferido | Requisito |
| --- | --- | --- |
| Captura da interface | PNG | largura entre 1400 e 1800 px |
| Infográfico vetorial | SVG | fontes e símbolos renderizados corretamente |
| Imagem com transparência | PNG ou SVG | contraste verificado sobre fundo claro |
| Fotografia, apenas se indispensável | JPEG | qualidade alta, sem dados identificáveis |

- Capture a interface com escala do navegador a 100%.
- Use o tema claro como referência documental. Acrescente o tema escuro apenas
  quando a diferença fizer parte da tarefa.
- Preserve a proporção original; nunca estique uma imagem para preencher a
  página.
- A imagem deve continuar legível quando dimensionada para uma página A4 com
  margens.
- Para um procedimento móvel, use uma captura adicional com 375 px de largura.
  Não substitua a captura principal de desktop por uma imagem móvel.

## Recorte e composição

- Mostre contexto suficiente para a pessoa reconhecer a página: título,
  separador ativo ou secção relevante.
- Remova áreas vazias e elementos sem relação com a tarefa.
- Não corte mensagens de validação, cabeçalhos de campos ou o resultado da
  ação.
- Evite capturas de uma página inteira quando apenas uma região é relevante.
- Não combine estados diferentes da aplicação sem separar e identificar cada
  painel.

## Chamadas visuais

Quando uma imagem exigir orientação adicional, use círculos numerados simples
e faça os mesmos números corresponderem aos passos do texto.

- Use no máximo cinco chamadas por imagem.
- Não cubra rótulos, valores, mensagens ou controlos.
- Use uma cor de realce com contraste WCAG AA e que não dependa apenas de
  vermelho/verde para transmitir significado.
- Não adicione setas, sombras ou ornamentos sem função informativa.
- Mantenha o estilo das chamadas consistente em todos os guias.

Uma sequência longa deve ser dividida em duas ou mais imagens, colocadas perto
dos passos correspondentes.

## Nomenclatura e organização

Use nomes em minúsculas, sem acentos, separados por hífen:

```text
<perfil>-<tarefa>-<passo>.<extensão>
```

Exemplos:

```text
publico-submeter-pedido-formulario.png
investigador-proposta-conversacao.png
equipa-proposta-acoes.png
direcao-revisao-devolver.png
admin-fonte-colecao-mapeamento.png
```

Não use nomes como `screenshot-1.png`, datas ou identificadores de recursos
reais. Se uma imagem for substituída mantendo a mesma finalidade, preserve o
nome para não quebrar as referências.

## Inserção no guia

Use texto alternativo que descreva a informação necessária para executar a
tarefa, não a aparência genérica da imagem:

```text
Texto alternativo: Separador Actions com o botão Assign to me assinalado como passo 1.
Ficheiro: assets/equipa-proposta-assumir.png
Legenda: Figura 1 — Localização da ação para assumir uma proposta nova.
```

O procedimento deve continuar compreensível quando a imagem não carregar. Não
use frases como “clique aqui”, “veja acima” ou instruções dependentes apenas de
cor ou posição.

Para guias dentro de subdiretórios, ajuste o caminho relativo até este
diretório sem duplicar a imagem noutro local.

## Verificação obrigatória

Antes de publicar uma imagem:

1. confirme que corresponde à versão atual da aplicação;
2. inspecione-a na resolução original;
3. confirme que não contém dados pessoais ou segredos;
4. verifique legibilidade, contraste e texto alternativo;
5. renderize o guia em Markdown e no PDF consolidado;
6. confirme que não há cortes, deformação ou legenda separada da imagem;
7. execute a verificação de links da documentação.

Se uma alteração da aplicação modificar a disposição, os rótulos ou o estado
representado, atualize a captura e reveja os passos do guia no mesmo trabalho.
