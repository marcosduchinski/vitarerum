# SPEC-023 — Fronteiras de contexto, camadas e envelope de erro

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-023 |
| Estado | Implementado |
| Alcance | Transversal — todos os contextos |
| Escrita a partir de | `pyproject.toml` (contratos import-linter), `app/main.py`, `AGENTS.md`, `docs/architecture/module-boundaries.md` |
| Specs relacionadas | Todas |

## 1. Problema

Um sistema com muitos contextos degrada-se por dependencias que ninguem decidiu:
um `import` conveniente entre modulos transforma dois contextos independentes num
so, e a partir dai qualquer alteracao num propaga-se ao outro.

Igualmente, um cliente que consome dezenas de endpoints precisa de uma forma de
erro previsivel; sem ela, cada ecra trata falhas a sua maneira.

## 2. Objetivo

Fazer das fronteiras arquiteturais uma regra **verificada por ferramenta**, e do
envelope de erro um contrato unico da aplicacao.

## 3. Linguagem ubiqua

- **Contexto delimitado**: modulo de topo com dominio, aplicacao, infraestrutura e apresentacao proprios.
- **Linguagem publicada (`*.public`)**: unico ponto de entrada de um contexto para os restantes.
- **Contrato de camadas**: regra que impoe `presentation > infrastructure > application > domain`.
- **Contrato proibido**: regra que impede um conjunto de modulos de importar outro.
- **Envelope de erro**: forma unica da resposta de falha.

---

## 4. Requisitos funcionais

### RF-001 — Camadas por contexto

Cada contexto obedece a ordem `presentation > infrastructure > application >
domain`. Uma camada nunca importa outra acima de si.

Intencao de cada camada:

| Camada | Contem |
| --- | --- |
| `domain` | Modelo puro, entidades, objetos de valor, enumeracoes, invariantes |
| `application` | Casos de uso, comandos, portas, politicas de autorizacao |
| `infrastructure` | Registos SQLAlchemy, repositorios, armazenamento, adaptadores externos |
| `presentation` | Rotas, dependencias, esquemas de pedido e resposta, mapeamento HTTP |

### RF-002 — Pureza do dominio e da aplicacao

O dominio nao importa FastAPI, SQLAlchemy, Pydantic, infraestrutura nem
apresentacao. A aplicacao nao importa FastAPI nem SQLAlchemy.

Regras praticas que daqui decorrem: nenhuma logica de negocio em rotas ou em
modelos ORM; invariantes vivem no dominio ou em servicos de aplicacao; esquemas
Pydantic apenas na fronteira de apresentacao.

### RF-003 — Acesso entre contextos apenas por linguagem publicada

Um contexto acede a outro exclusivamente pelo modulo `*.public` desse outro. Nao
existe importacao direta para o interior de outro contexto.

Contratos em vigor incluem, entre outros: identidade acedida so por
`identity.public`; numeros de referencia so por `reference_numbers.public`;
prompts so por `prompts.public`; CIDOC-CRM so por `cidoc_crm.public`; retorno
cientifico acede aos fluxos de uso de colecoes so por linguagem publicada;
relatorios e publicacoes externas compoem outros contextos so por linguagem
publicada.

### RF-004 — Contextos deliberadamente isolados

Modelos de documento, indice de objetos de colecao e perguntas ao museu **nao
dependem de outros contextos**, com a unica excecao de identidade pela sua
linguagem publicada.

Isolar reflete o desenho: sao capacidades que servem a instituicao sem participar
no ciclo de vida de propostas e projetos.

### RF-005 — Identidade nao depende de fluxos de negocio

O contexto de identidade nao importa uso de colecoes. A dependencia e sempre no
sentido oposto.

### RF-006 — Nucleo partilhado minimo

`app.shared.kernel` mantem-se dependente apenas da biblioteca padrao, para poder
ser partilhado por qualquer contexto sem arrastar dependencias.

### RF-007 — Registo obrigatorio de contratos

Um contexto novo nao esta completo enquanto nao registar em `pyproject.toml`:

1. o seu contrato de camadas;
2. a sua cobertura nos contratos de pureza do dominio e da aplicacao.

Alterar contratos entre contextos obriga a atualizar o mapa de contextos
(`docs/architecture/vitarerum-context-map.puml`) na mesma alteracao.

### RF-008 — Verificacao automatica

As fronteiras sao verificadas por `uv run lint-imports`, a par de `pytest`,
`ruff` e `mypy`. Nenhuma dessas configuracoes e enfraquecida para fazer passar
uma alteracao.

### RF-009 — Envelope de erro de validacao

Falhas de validacao de pedido respondem `422` com:

```json
{ "message": "Validation failed", "errors": [ { "field": "...", "message": "..." } ] }
```

### RF-010 — Envelope de erro de autorizacao

`AccessDenied` responde `403 ACCESS_DENIED`; `InsufficientGroup` responde `403
INSUFFICIENT_GROUP`. Ambos com `{ "error", "message" }`.

### RF-011 — Normalizacao das excecoes HTTP

As excecoes HTTP sao normalizadas para `{ "message", "errors?" }`, preservando o
codigo legivel por maquina como superconjunto. O cliente le `message`, `errors` e
`fieldErrors` e ignora o resto.

### RF-012 — Falha de decifragem nao expoe detalhe

Ficheiro ou campo que nao decifram respondem `500` com codigo tipado
(`FILE_UNREADABLE`, `FIELD_UNREADABLE`) e mensagem generica. O detalhe vai para o
registo do servidor, nunca para a resposta
([SPEC-022](../022-cifragem-e-armazenamento/spec.md), RF-003).

### RF-013 — Semantica de codigos preservada

`401` e exclusivo de autenticacao; `403` e autorizacao
([SPEC-007](../007-identidade-e-acesso/spec.md), RF-004). Alterar formas de
resposta publicas exige atualizar a documentacao e os testes de contrato.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Nenhum contexto importa o interior de outro |
| INV-002 | O dominio nao conhece frameworks |
| INV-003 | A aplicacao nao conhece FastAPI nem SQLAlchemy |
| INV-004 | `app.shared.kernel` depende apenas da biblioteca padrao |
| INV-005 | Toda a fronteira declarada esta registada como contrato verificavel |
| INV-006 | Toda a falha sai no envelope de erro da aplicacao |
| INV-007 | Nenhuma resposta de erro revela detalhe interno de armazenamento |

## 6. Criterios de aceitacao

### CA-001 — Fronteiras verificadas por ferramenta
Dado o repositorio no seu estado atual
Quando se executa `uv run lint-imports`
Entao todos os contratos declarados passam
→ ferramenta: `import-linter` sobre os contratos de `pyproject.toml`

### CA-002 — Envelope de validacao e de acesso negado
→ `test/use_of_collections/test_golden_contracts.py::test_golden_error_bodies`, `::test_golden_access_denied_body`

### CA-003 — Fronteira `401` / `403`
→ `test/identity/test_auth.py::test_caller_valid_token_missing_permission_header_is_403`, `::test_caller_malformed_token_is_401` (ver [SPEC-007](../007-identidade-e-acesso/spec.md), CA-003)

### CA-004 — Formas de resposta estaveis por contrato dourado
→ `test/use_of_collections/test_golden_contracts.py::test_golden_submit_proposal_response_shape`, `::test_golden_proposal_detail_response_shape`, `::test_golden_paginated_proposals_envelope_shape`, `::test_golden_project_detail_and_list_shapes`, `::test_golden_project_events_envelope_shape`

## 7. Requisitos nao funcionais

- **Verificacao continua**: `pytest`, `ruff`, `mypy` estrito e `lint-imports` correm sobre o repositorio; nenhuma configuracao e relaxada para acomodar uma alteracao.
- **Documentacao viva**: o mapa de contextos acompanha qualquer mudanca de fronteira.
- **Nomenclatura**: classes ORM com sufixo `...Record`, ou `...Orm` quando o dominio ja usa `...Record`.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Contratos de camadas e de proibicao (RF-001..RF-007) | `pyproject.toml`, seccao `tool.importlinter` |
| Envelope de erro (RF-009..RF-012) | `app/main.py` |
| Contrato transversal publicado (RF-009..RF-013) | `docs/api_contracts/README.md` |
| Linguagens publicadas (RF-003) | `app/*/public.py` |
| Nucleo partilhado (RF-006) | `app/shared/kernel.py` |
| Mapa de contextos | `docs/architecture/vitarerum-context-map.puml`, `vitarerum-context-map.svg` |
| Fronteiras documentadas | `docs/architecture/module-boundaries.md`, `AGENTS.md` |

## 9. Questoes em aberto

1. Alguns contextos comunicam hoje por chamada sincrona atraves da linguagem publicada; em que ponto se justifica linguagem publicada **por eventos** (ver `docs/architecture/adr/0002-published-language-over-event-bus.md`)?
2. Deve existir um teste que falhe quando um contexto novo nao registar os seus contratos, em vez de depender de revisao humana?
