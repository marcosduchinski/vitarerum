# SPEC-008 — Proposta de uso de colecoes

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-008 |
| Estado | Implementado |
| Contexto delimitado | `app/use_of_collections` (fase de proposta) |
| Escrita a partir de | `domain/models.py`, `application/use_cases/{proposal,project}.py`, `test/use_of_collections/`, contratos 02 e 03 |
| Specs relacionadas | [SPEC-009](../009-projeto-uso-de-colecoes/spec.md), [SPEC-010](../010-submissao-publica/spec.md), [SPEC-007](../007-identidade-e-acesso/spec.md), [SPEC-019](../019-numeros-de-referencia/spec.md) |

## 1. Problema

Um pedido de acesso a colecoes comeca como uma conversa — um investigador
descreve por palavras o que pretende — e tem de terminar como uma decisao
institucional fundamentada, com documentacao verificada e rasto de quem decidiu
o que e quando.

## 2. Objetivo

Conduzir um pedido desde a primeira mensagem ate a decisao (aprovacao,
rejeicao ou cancelamento), acumulando objetos pretendidos, documentos exigidos,
correcoes e conversa, com evento registado em cada passo.

## 3. Atores

| Ator | Papel |
| --- | --- |
| Investigador (`EXTERNAL`) | Submete, acrescenta objetos, envia documentos, conversa, cancela |
| `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `SYS_ADMIN` | Atribuem, pedem documentos e correcoes, encaminham, rejeitam |
| `CURATORIAL` | **Unico** grupo que aprova |
| `DIRECTION` | Le as propostas que lhe foram encaminhadas e devolve-as ao staff com a sua resposta. Nao executa mais nenhuma alteracao (RF-023) |

## 4. Linguagem ubiqua

- **Proposta**: pedido formal. Estados `SUBMITTED`, `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED`.
- **Canal de submissao**: `AUTHENTICATED` ou `PUBLIC`.
- **Objeto pretendido**: instantaneo de um objeto de colecao que o investigador identificou no catalogo.
- **Documento requerido**: tipo de documento que o staff exige, nomeado em texto livre.
- **Item de correcao**: pedido de substituicao de um documento entregue, ou de entrega de um documento em falta. Estados `REQUESTED`, `RESOLVED`.
- **Evento de proposta**: registo imutavel de cada ato relevante.
- **Conversa**: fio de mensagens associado a proposta.
- **Via da Direcao**: desvio temporario de uma proposta `PENDING` para a Direcao, para decisao que o staff operacional nao toma sozinho. Entra por `REFERRED_TO_DIRECTION` e sai por `DIRECTION_CLARIFIED`.

---

## 5. Requisitos funcionais

### RF-001 — Submissao autenticada

`POST /api/v1/proposals` (`multipart/form-data`) cria atomicamente a proposta em
`SUBMITTED` e a conversa semeada com a mensagem inicial, e regista o evento
`SUBMITTED`. O `PermissionId` do chamador fica como `requestedBy`.

Regras de conteudo:

- `title`, `intendedUse`, `purpose`, `beginDate` e `endDate` sao opcionais;
- `intendedUse`, quando presente, e `EXHIBITION`, `IN_SITU_VISIT` ou `OTHER`;
- `endDate` posterior a `beginDate` so e exigido quando ambas existem;
- ate 5 documentos, dos tipos PDF, JPG, PNG e DOCX, com maximo de 10 MB cada.

### RF-002 — A proposta nasce sem objetos

A submissao **nao** aceita objetos estruturados. O investigador descreve em prosa
o que pretende; os objetos sao acrescentados depois, ja identificados no
catalogo, por `POST /proposals/{id}/requested-objects`. Uma proposta pode chegar
a aprovacao sem objetos, e o projeto nasce entao vazio.

A justificacao e de processo: quem submete raramente conhece o numero de
inventario; exigi-lo a entrada transformaria o primeiro contacto num formulario
que o investigador nao consegue preencher.

### RF-003 — Nenhum projeto e criado na submissao

O projeto so existe quando um curador aprova. Uma proposta rejeitada ou
cancelada nunca materializa projeto.

### RF-004 — Numero de referencia

A proposta recebe `VRP-YYYYMMDD-XXXX`, sequencial por data de submissao. O
projeto recebe `CUP-XXXXXXXX` no momento da aprovacao
([SPEC-019](../019-numeros-de-referencia/spec.md)).

### RF-005 — Visibilidade das listagens

Um investigador so ve as propostas cujo `requestedBy` e a sua permissao ativa.
O staff ve todas e dispoe de filtros por estado (repetivel), tipo de uso, datas
e pesquisa. Um filtro `requestedBy` enviado por um nao-staff e ignorado e
forcado ao proprio identificador.

### RF-006 — Rollback da submissao

Se a persistencia da submissao falhar depois de ficheiros escritos, os ficheiros
guardados sao removidos. Nao ficam ficheiros orfaos.

### RF-007 — Atribuicao e encaminhamento

- `POST /proposals/{id}/assign` regista `ASSIGNED` e define `assignedTo`.
- `POST /proposals/{id}/forward` regista `FORWARDED`, atualiza `assignedTo` e exige estado `PENDING`.

Em ambos, o alvo tem de existir (`404` caso contrario) e pertencer a um grupo de
staff (`422` caso contrario). Atribuir ou encaminhar a si proprio nao gera
notificacao nem email. Tomar uma atribuicao de outra pessoa notifica quem a
detinha.

### RF-008 — Pedido de documentos

`POST /proposals/{id}/request-documents` regista `DOCUMENTS_REQUESTED` e
acrescenta os tipos exigidos. Exige `PENDING` e nao altera o estado.

O `type` e **texto livre**, nao um catalogo fixo: o staff nomeia o documento nas
suas palavras. O servidor apara espacos e exige valor nao vazio com ate 128
caracteres.

### RF-009 — Entrega de documentos

`POST /proposals/{id}/documents` associa um documento a proposta, exige estado
`PENDING` e notifica o staff atribuido. O tipo de documento segue a mesma regra
de texto livre. Conteudo que nao corresponde ao tipo declarado e recusado.

### RF-010 — Pedido de correcoes

`POST /proposals/{id}/request-document-corrections` marca documentos entregues
para substituicao e/ou pede documentos em falta, regista
`DOCUMENT_CORRECTIONS_REQUESTED` e envia ao requerente uma ligacao de emenda
delimitada e de uso unico.

- Exige `PENDING`; o ato e **instrutorio** e nao altera o estado.
- Exige pelo menos um item (`NO_CORRECTION_ITEMS`, `422`).
- `documentType` e texto livre, nao vazio, ate 128 caracteres.
- Com `documentId`, o documento tem de pertencer a proposta; sem ele, pede-se um documento em falta e o tipo e o unico ambito.
- Sem contacto de requerente, responde `MISSING_REQUESTER_CONTACT` (`409`).

### RF-011 — Emenda delimitada pelo ambito

Na entrega por ligacao de emenda:

- so sao aceites documentos dentro do ambito das correcoes pedidas;
- um tipo em texto livre e aparado e tem de corresponder exatamente ao ambito;
- tipo em branco e recusado;
- carregar um substituto substitui o documento assinalado;
- remover um documento de emenda liberta o ficheiro correspondente.

### RF-012 — Conclusao das correcoes

A submissao das correcoes so e aceite quando **todos** os itens estao
satisfeitos: cada item em falta tem documento novo, e cada substituicao tem um
documento posterior ao pedido. Caso contrario, e recusada nomeando os tipos em
falta.

### RF-013 — Edicao pelo staff

`PATCH /proposals/{id}` altera titulo, tipo de uso e datas. Campos omitidos
permanecem inalterados; `null` limpa o campo. Estados terminais respondem `409`;
intervalo de datas invalido responde `422`.

### RF-014 — Rejeicao

`POST /proposals/{id}/reject` exige `PENDING`, transita para `REJECTED`, regista
o evento e cria uma mensagem para o requerente na conversa.

### RF-015 — Cancelamento pelo requerente

`POST /proposals/{id}/cancel` so pode ser feito por quem submeteu. Uma proposta
`REJECTED` nao pode ser cancelada; uma ja `CANCELLED` tambem nao. O cancelamento
propaga-se ao projeto associado, **qualquer que seja** o estado deste — incluindo
`COMPLETED`, unico caso em que um projeto concluido muda de estado.

### RF-016 — Aprovacao

`POST /proposals/{id}/approve`, restrito a `CURATORIAL`:

1. exige `PENDING`;
2. transita a proposta para `APPROVED`;
3. cria o `CollectionUseProject` em `CREATED`;
4. regista `APPROVED` na proposta e `REQUESTED` no projeto;
5. copia titulo, proposito e datas **do corpo do pedido**, nao da proposta: o curador confirma ou ajusta os parametros no momento da decisao;
6. copia os objetos pretendidos como instantaneos do projeto, incluindo colecao de origem quando conhecida.

### RF-017 — Aprovisionamento no momento da aprovacao

Para uma proposta publica (`requestedBy` nulo, `requesterContact` presente), a
aprovacao e o momento em que a identidade aprovisiona — ou reutiliza — o
utilizador do email de contacto.

- Email novo: cria utilizador com password temporaria e, **depois de a transacao ficar duravel**, envia email de acesso.
- Email existente: reutiliza utilizador e permissao, nao repoe a password e nao envia credenciais; envia apenas o email de aprovacao.

Uma proposta rejeitada ou cancelada antes da aprovacao nunca chega a este passo:
nao cria utilizador, permissao nem email de credenciais.

### RF-018 — Conversa

`GET /proposals/{id}/conversation` e
`POST /proposals/{id}/conversation/messages` mantêm o fio associado a proposta.
Toda a proposta abre com uma mensagem.

### RF-019 — Historico de eventos

`GET /proposals/{id}/events` devolve a sequencia completa de eventos tipados,
cada um com instante, tipo, autor e nota.

### RF-020 — Isolamento entre requerentes

Um utilizador `EXTERNAL` nao acede a eventos, documentos ou projetos de outra
proposta que nao a sua.

### RF-021 — Encaminhar para a Direcao

`POST /proposals/{proposalId}/refer-to-direction`, com `targetPermissionId` e
`reason`, passa a proposta para a via da Direcao.

Condicoes, todas verificadas:

| Condicao | Falha |
| --- | --- |
| Chamador em `CURATORIAL` ou `COLLECTIONS_MANAGEMENT` | `403` |
| Chamador e o **responsavel atual** da proposta | `409` `INVALID_TRANSITION` |
| Proposta em `PENDING` | `409` `INVALID_TRANSITION` |
| `targetPermissionId` existe e pertence a `DIRECTION` | `422` |
| Utilizador de destino nao esta desativado | `422` |
| `reason` nao vazio | `422` |

O efeito e uma **reatribuicao, nao uma transicao de estado**: a proposta
permanece `PENDING`, `assignedTo` passa a ser a permissao da Direcao, e fica
registado o evento `REFERRED_TO_DIRECTION` com o autor, o instante, a razao e a
permissao de destino. O destinatario e notificado.

Exigir que o chamador seja o responsavel atual e o que impede que a via da
Direcao seja usada para tirar uma proposta a quem a esta a tratar.

### RF-022 — Devolver ao staff

`POST /proposals/{proposalId}/return-to-staff`, com `targetPermissionId` e
`reason`, e o caminho de saida — e o **unico** que a Direcao tem.

As condicoes espelham RF-021: chamador em `DIRECTION` e responsavel atual,
proposta `PENDING`, destino ativo em `CURATORIAL` ou `COLLECTIONS_MANAGEMENT`, e
`reason` nao vazio. Regista `DIRECTION_CLARIFIED` com a resposta da Direcao, que
fica assim no historico da proposta e nao apenas numa conversa paralela.

### RF-023 — A Direcao e so de leitura fora da sua via

Um chamador do grupo `DIRECTION` que tente qualquer outra alteracao sobre uma
proposta — atribuir, encaminhar, pedir documentos ou correcoes, aprovar,
rejeitar — recebe `403` com `DIRECTION_READ_ONLY`.

A Direcao acede apenas as propostas atribuidas a sua permissao ativa.

A restricao e deliberada: a Direcao decide, nao administra o processo. Sem ela,
os comandos genericos de atribuicao permitiriam entrar e sair da via da Direcao
sem deixar os eventos que a tornam auditavel.

---

## 6. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Toda a proposta tem `requestedBy` ou `requesterContact`, conforme o canal |
| INV-002 | Toda a proposta abre com uma mensagem na conversa |
| INV-003 | Cada ato relevante deixa um evento tipado |
| INV-004 | Nenhum projeto existe sem aprovacao curatorial |
| INV-005 | Nenhuma correcao e dada por satisfeita sem documento que a satisfaca |
| INV-006 | Uma emenda nunca aceita documento fora do ambito pedido |
| INV-007 | Uma proposta rejeitada nunca cria utilizador nem envia credenciais |
| INV-008 | Um requerente so ve a sua propria proposta |
| INV-009 | Uma proposta rejeitada nao pode ser cancelada |
| INV-010 | A via da Direcao nunca muda o estado da proposta: entra e sai em `PENDING` |
| INV-011 | So o responsavel atual encaminha para a Direcao ou devolve ao staff |
| INV-012 | Entrada e saida da via da Direcao deixam sempre evento com razao |

## 7. Criterios de aceitacao

### CA-001 — Submissao e seus limites de ficheiro
→ `test_api.py::test_submit_proposal_returns_201`, `::test_submit_proposal_accepts_supporting_document_types`, `::test_submit_proposal_rejects_unsupported_document_type`, `::test_submit_proposal_rejects_more_than_five_documents`, `::test_submit_proposal_rejects_oversized_document`, `::test_submit_proposal_invalid_date_range_returns_422`

### CA-002 — Rollback de ficheiros quando a submissao falha
→ `test_api.py::test_submit_proposal_rolls_back_saved_documents_when_upload_fails`

### CA-003 — Objetos acrescentados depois da submissao
→ `test_api.py::test_relate_searched_objects_surfaces_them_on_detail`, `::test_remove_requested_object_updates_proposal_detail`

### CA-004 — Visibilidade e filtros das listagens
→ `test_api.py::test_list_proposals_paginates_results`, `::test_list_proposals_filters_by_multiple_statuses`, `::test_staff_can_scope_list_with_requested_by`, `::test_non_staff_requested_by_is_ignored_and_forced_to_own_id`

### CA-005 — Atribuicao e encaminhamento com alvo valido
→ `test_api.py::test_staff_can_assign_proposal_to_staff_target`, `::test_assign_proposal_rejects_unknown_target_permission`, `::test_assign_proposal_rejects_external_target_permission`, `::test_forward_proposal_rejects_external_target_permission`, `::test_forward_proposal_rejects_non_pending_proposal`, `::test_assign_proposal_to_self_sends_no_notification_or_email`, `::test_take_over_assignment_notifies_previous_assignee`

### CA-006 — Autorizacao por grupo na fase de proposta
→ `test_api.py::test_external_owner_cannot_assign_proposal`, `::test_external_owner_cannot_request_documents`, `::test_external_owner_cannot_patch_proposal`

### CA-007 — Edicao pelo staff e estados terminais
→ `test_api.py::test_staff_can_patch_proposal_title`, `::test_patch_proposal_null_title_clears_it`, `::test_patch_proposal_omitted_fields_left_unchanged`, `::test_patch_proposal_terminal_status_returns_409`, `::test_patch_proposal_invalid_date_range_returns_422`

### CA-008 — Correcoes: ambito, satisfacao e substituicao
→ `test_domain_models.py::test_request_document_corrections_records_items_and_event`, `::test_request_document_corrections_requires_pending`, `::test_request_document_corrections_unknown_document_id_raises`, `::test_submit_document_corrections_resolves_satisfied_missing_item`, `::test_submit_document_corrections_rejects_unsatisfied_item`, `::test_submit_document_corrections_replacement_needs_fresh_document`, `::test_remove_document_out_of_scope_raises`

### CA-009 — Emenda publica delimitada
→ `test_correction_flow.py::test_amendment_add_then_submit_resolves`, `::test_amendment_submit_without_document_is_rejected`, `::test_amendment_upload_out_of_scope_is_rejected`, `::test_amendment_upload_free_text_type_trims_and_matches_scope`, `::test_amendment_upload_blank_type_rejected`, `::test_amendment_upload_replaces_flagged_document`, `::test_amendment_remove_reclaims_file`

### CA-010 — Rejeicao cria mensagem ao requerente
→ `test_api.py::test_reject_proposal_creates_message_to_requester`

### CA-011 — Cancelamento pelo requerente e sua propagacao
→ `test_api.py::test_cancel_proposal_by_requester_without_project_returns_cancelled`, `::test_cancel_proposal_cascades_to_existing_project_any_status`, `::test_cancel_proposal_rejects_non_requester`, `::test_cancel_proposal_rejects_rejected_status`, `test_domain_models.py::test_proposal_driven_project_cancellation_allows_completed_project`

### CA-012 — Aprovacao e aprovisionamento
→ `test_api.py::test_approve_proposal_without_objects_creates_empty_project`, `::test_approve_proposal_invalid_date_range_returns_422`, `::test_approve_public_proposal_sends_access_email_after_commit`, `::test_approve_public_proposal_new_account_skips_approval_email`, `::test_approve_public_proposal_existing_account_sends_approval_email`

### CA-013 — Isolamento entre requerentes
→ `test_api.py::test_external_user_cannot_read_other_proposal_events`, `::test_external_user_cannot_read_other_proposal_documents`, `::test_external_user_cannot_read_other_project_events`

### CA-014 — Tipo de documento em texto livre com limites
→ `test_domain_models.py::test_document_type_accepts_free_text_and_trims`, `::test_document_type_rejects_blank`, `::test_document_type_rejects_over_128_characters`, `::test_document_type_accepts_exactly_128_characters`

### CA-015 — Encaminhamento reatribui e regista a razao
Dado uma proposta `PENDING` atribuida a um curador
Quando este a encaminha para uma permissao da Direcao com uma razao
Entao a proposta continua `PENDING`, passa a estar atribuida a Direcao, e o evento `REFERRED_TO_DIRECTION` guarda a razao, o autor e a permissao de destino
→ `test_domain_models.py::test_refer_to_direction_changes_assignee_and_records_reason_and_target`, `test_api.py::test_curator_can_refer_assigned_proposal_to_direction`

### CA-016 — Devolucao exige razao e responsavel atual
Dado uma proposta na via da Direcao
Quando a Direcao a devolve ao staff
Entao a razao e obrigatoria, so o responsavel atual pode devolver, e fica registado `DIRECTION_CLARIFIED`
→ `test_domain_models.py::test_return_to_staff_requires_reason_and_current_direction_assignee`, `::test_return_to_staff_records_direction_clarification`, `test_api.py::test_direction_can_return_proposal_to_staff_with_required_reason`

### CA-017 — A Direcao nao ve o que nao lhe foi encaminhado
Dado uma proposta atribuida a outro membro da Direcao
Quando um membro da Direcao a tenta ler
Entao o acesso e recusado
→ `test_api.py::test_direction_cannot_read_a_proposal_assigned_to_another_member`

## 8. Requisitos nao funcionais

- **Atomicidade**: proposta, conversa e evento inicial nascem na mesma transacao.
- **Efeitos externos depois do commit**: emails de acesso so partem apos a transacao ficar duravel.
- **Contratos dourados**: as formas de resposta cobertas por testes de contrato nao mudam sem atualizar a documentacao.
- **Dados sensiveis**: emails de requerentes e documentos carregados sao dados sensiveis da aplicacao.

## 9. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Agregado `Proposal` e transicoes (RF-008..RF-016) | `app/use_of_collections/domain/models.py` |
| Casos de uso da proposta | `app/use_of_collections/application/use_cases/proposal.py` |
| Aprovacao e aprovisionamento (RF-016, RF-017) | `app/use_of_collections/application/use_cases/project.py`, `infrastructure/external_requester.py` |
| Emenda delimitada (RF-011) | `app/use_of_collections/infrastructure/amendment_invitation.py` |
| Endpoints | `app/use_of_collections/presentation/proposal_routes.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 10. Questoes em aberto

1. A password temporaria aprovisionada na aprovacao nao expira nem forca alteracao no primeiro login — risco assumido e por fechar agora que existe reposicao self-service ([SPEC-007](../007-identidade-e-acesso/spec.md), RF-009).
2. Deve o tipo de documento em texto livre convergir para um catalogo sugerido, mantendo a liberdade de escrita?
