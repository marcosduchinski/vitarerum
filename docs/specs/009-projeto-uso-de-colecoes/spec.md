# SPEC-009 — Projeto de uso de colecoes e seus diarios

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-009 |
| Estado | Implementado |
| Contexto delimitado | `app/use_of_collections` (fase de projeto) |
| Escrita a partir de | `domain/models.py`, `application/use_cases/{project,journal,publication,project_todos}.py`, `test/use_of_collections/`, contratos 04 e 05 |
| Specs relacionadas | [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-004](../004-decisao-candidato-publicacao/spec.md), [SPEC-013](../013-mapeamento-cidoc-crm/spec.md), [SPEC-019](../019-numeros-de-referencia/spec.md) |

## 1. Problema

Depois de aprovado o acesso, o museu precisa de saber **o que aconteceu ao
acervo**: que objetos foram efetivamente manuseados, por quem, quando, em que
condicoes, que ocorrencias houve, e o que a consulta produziu em conhecimento.
Sem esse registo, o acesso deixa o acervo sem memoria.

## 2. Objetivo

Conduzir o projeto de `CREATED` a `COMPLETED` ou `CANCELLED`, mantendo tres
diarios distintos — acesso a objetos, ocorrencias e publicacoes — com autoria,
anexos e regras de escrita adequadas a fase e ao papel.

## 3. Linguagem ubiqua

- **Projeto de uso**: execucao aprovada de um acesso. Estados `CREATED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`; resultado `COMPLETED` ou `CANCELLED`.
- **Objeto do projeto**: instantaneo, propriedade do projeto, do objeto de colecao a manusear.
- **Diario de acesso a objetos (`OAL`)**: registo do manuseamento efetivo.
- **Diario de ocorrencias (`ROC`)**: registo de eventos anomalos ou dignos de nota sobre objetos.
- **Diario de publicacoes**: registo do retorno cientifico declarado do projeto.
- **Evento de uso (`UseEvent`)**: `REQUESTED`, `STARTED`, `COMPLETED`, `CANCELLED`.
- **Post-it de projeto**: lista de tarefas pessoal de um membro do staff sobre um projeto.

---

## 4. Requisitos funcionais

### RF-001 — Criacao apenas por aprovacao

O projeto nasce em `CREATED` no ato de aprovacao da proposta, com evento
`REQUESTED` e numero `CUP-XXXXXXXX`
([SPEC-008](../008-proposta-uso-de-colecoes/spec.md), RF-016).

### RF-002 — Inicio do projeto

`POST /collection-use-projects/{id}/start` exige `CREATED` e transita para
`IN_PROGRESS`, registando `STARTED`.

**Efeito lateral deliberado:** o diario de acesso (`OAL-XXXXXXXX`) e semeado com
uma entrada por cada objeto do projeto, ligada ao objeto de origem, com
`numberOfObjects = 1` e o chamador como autor.

A semeadura so ocorre quando o projeto tem objetos **e** ainda nao existe
diario: um projeto sem objetos deixa o diario por criar, e um diario ja iniciado
pelo staff antes do arranque nao e tocado.

### RF-003 — Conclusao

`POST /collection-use-projects/{id}/complete` exige `IN_PROGRESS` e pelo menos
um objeto do projeto. Transita para `COMPLETED`, fixa `result = COMPLETED` e
regista `COMPLETED`.

Concluir sem objetos e recusado: um projeto sem objetos nao documenta uso
nenhum e nao pode alimentar retorno cientifico nem relatorio.

### RF-004 — Cancelamento

`POST /collection-use-projects/{id}/cancel` exige razao e e permitido a partir de
qualquer estado nao terminal. Transita para `CANCELLED` com
`result = CANCELLED`.

A unica excecao a terminalidade e o cancelamento propagado pela proposta
([SPEC-008](../008-proposta-uso-de-colecoes/spec.md), RF-015), que alcanca mesmo
um projeto `COMPLETED`.

### RF-005 — Edicao de detalhes

`PATCH /collection-use-projects/{id}` altera titulo, proposito e datas efetivas,
restrito ao staff. Estados terminais respondem `409`; `endDate` anterior a
`beginDate` responde `422`. A edicao **nao** gera evento de ciclo de vida.

### RF-006 — Gestao de objetos do projeto

`POST /collection-use-projects/{id}/objects` acrescenta objetos, restrito ao
staff, recusado em estados terminais.

Sincronizacao com o diario de acesso:

- objetos novos sao acrescentados ao diario existente;
- se nao existir diario, e criado;
- se o diario ja estiver **concluido**, o acrescento e bloqueado.

### RF-007 — Remocao de objetos e dependencias

`DELETE /collection-use-projects/{projectId}/objects/{objectId}` e
deliberadamente conservador. Remove o objeto quando nada depende dele, ou quando
a unica dependencia e a entrada automatica de diario criada ao adiciona-lo —
nesse caso a entrada e apagada com o objeto. Responde `204`.

Havendo ocorrencias, entradas de publicacao, anexos ou entradas de diario
editadas, a remocao e bloqueada com `409` `PROJECT_OBJECT_HAS_DEPENDENCIES`, e a
resposta traz `dependencies` com a contagem por tipo — o cliente precisa dela
para apresentar uma confirmacao que diga o que se perde.

A remocao em cascata existe em
`POST /collection-use-projects/{projectId}/objects/{objectId}/remove`, mas
**exige confirmacao explicita**: apagar trabalho registado nunca acontece por
omissao.

### RF-008 — Notificacao do requerente externo

Iniciar, concluir e cancelar um projeto notificam o requerente externo.

### RF-009 — Diario de acesso a objetos

- `POST /collection-use-projects/{id}/log-entries` cria entrada (e o diario, se ainda nao existir);
- `PATCH .../log-entries/{entryId}` edita parcialmente e permite limpar observacoes;
- `GET .../log-entries` e `GET .../object-access-log` leem;
- entrada exige `numberOfObjects >= 1`;
- uma entrada pode ligar-se ao objeto do projeto que documenta.

Ler o diario de um projeto sem entradas responde `404`: o diario e criado
preguicosamente e a sua ausencia e informacao, nao um erro de servidor.

### RF-010 — Diario de ocorrencias

Estrutura simetrica a do diario de acesso
(`/occurrence-entries`, `/object-occurrence-log`), com exigencias proprias:
`numberOfObjects >= 1`, local e descricao detalhada obrigatorios. A edicao e
parcial e permite limpar o testemunho.

### RF-011 — Anexos dos diarios

Entradas de ambos os diarios aceitam anexos. Todo o anexo exige **descricao**.
Tipos de media invalidos sao recusados (`422`). O download exige a referencia do
ficheiro; referencia desconhecida responde `404`. A remocao apaga o ficheiro.

Os ficheiros sao guardados sob o `DATA_DIR` configurado, com cifragem quando
configurada.

### RF-012 — Diario de publicacoes com regra de fase e papel

Cada projeto tem no maximo um diario de publicacoes, criado no primeiro
registo. A escrita e limitada por fase **e** papel:

| Estado do projeto | Quem pode escrever |
| --- | --- |
| `IN_PROGRESS` | apenas o requerente externo |
| `COMPLETED` | apenas `CURATORIAL`, `COLLECTIONS_MANAGEMENT` ou `DIRECTION` |
| qualquer outro | ninguem |

A regra reproduz a realidade institucional: durante o trabalho, quem publica e o
investigador; concluido o projeto, quem mantem o registo e o museu. E por aqui
que entram as confirmacoes de retorno cientifico
([SPEC-004](../004-decisao-candidato-publicacao/spec.md), RF-003).

Uma entrada exige nota nao vazia, aceita anexos com descricao e pode referir um
objeto do projeto — recusando um objeto que pertenca a outro projeto.

### RF-013 — Projetos de seguimento

`POST /collection-use-projects/{projectId}/follow-ups`, restrito ao staff, cria um projeto novo a
partir de um projeto de origem `COMPLETED`, com um subconjunto nao vazio dos
seus objetos e um intervalo de datas valido.

Os diarios **nao** sao copiados: o projeto de seguimento documenta o seu proprio
trabalho. O proprietario do projeto de origem acede ao projeto criado.

### RF-014 — Post-its de projeto por perfil

Cada membro do staff mantem a sua propria lista de tarefas por projeto sob
`/collection-use-projects/{projectId}/todo-items`: criar, renomear, marcar
concluida, reabrir (`/todo-items/{itemId}/reopen`), reordenar e apagar. O painel
pessoal agrega-as em `GET /collection-use-projects/my-todo-items`. O texto e aparado e
limitado a 160 caracteres; a posicao e nao negativa.

As listas sao **isoladas por permissao**: um membro do staff nunca ve nem altera
os itens de outro. O painel pessoal mostra apenas os itens do perfil ativo.
Utilizadores `EXTERNAL` nao tem acesso a esta funcionalidade.

### RF-015 — Documentos oficiais gerados

O diario de acesso e o de ocorrencias podem ser descarregados como documentos
preenchidos a partir dos modelos institucionais (RAIS e ROC). O contacto do
requerente e obtido do projeto e, na sua falta, do contacto da proposta. Sem
diario, a descarga responde `404`. Um investigador nao descarrega o documento de
outro.

### RF-016 — Historico de eventos

`GET /collection-use-projects/{id}/events` devolve a sequencia de eventos de uso
com autor, instante e nota.

### RF-017 — Exportacao para o modelo CIDOC-CRM

`POST /collection-use-projects/{id}/export-in-situ-visit-record` entrega o
projeto ao contexto de mapeamento CIDOC-CRM
([SPEC-013](../013-mapeamento-cidoc-crm/spec.md)). So um projeto `COMPLETED`
com evento de conclusao constitui evidencia de visita executada.

### RF-018 — Superficie HTTP do diario de publicacoes

Todos sob `/collection-use-projects/{projectId}`, sujeitos a regra de fase e
papel de RF-012 e ao mesmo acesso ao projeto que os restantes diarios.

| Endpoint | Comportamento |
| --- | --- |
| `POST /publication-entries` | Cria a entrada e, se ainda nao existir, o proprio diario, com numero de referencia atribuido ([SPEC-019](../019-numeros-de-referencia/spec.md)). `201` |
| `PATCH /publication-entries/{entryId}` | Corrige a nota da entrada |
| `DELETE /publication-entries/{entryId}` | Remove a entrada e os seus anexos. `204` |
| `GET /publication-entries` | Lista paginada (`page`, `size` maximo 100), com filtro `addedBy` |
| `GET /publication-log` | Devolve o diario com o seu numero de referencia; `404` enquanto nao houver diario |
| `GET /publication-log/document` | Documento oficial preenchido (RF-019) |
| `POST /publication-entries/{entryId}/attachments` | Anexo com descricao obrigatoria |
| `GET`/`DELETE /publication-entries/{entryId}/attachments/{fileReference}` | Descarrega e remove o anexo |

Uma entrada que registe um retorno cientifico confirmado
([SPEC-004](../004-decisao-candidato-publicacao/spec.md)) **nao** pode ser
apagada: responde `409` com `PUBLICATION_ENTRY_IN_USE`. O diario e a prova do
retorno; apagar a entrada apagaria a prova de uma decisao curatorial ja tomada.

Uma entrada de outro projeto responde `404`, e nao `403` — a existencia de
entradas alheias nao e revelada.

### RF-019 — Documento oficial do diario de publicacoes (RRP)

`GET /collection-use-projects/{projectId}/publication-log/document` devolve o
modelo institucional RRP preenchido com o diario, as suas entradas e o contacto
do requerente, pela mesma regra de RF-015. Sem diario responde `404`.

Acima de 1000 entradas a composicao e recusada com `422` e
`DOCUMENT_ENTRY_LIMIT_EXCEEDED`, em vez de produzir um documento truncado em
silencio.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Um projeto so existe por aprovacao de proposta |
| INV-002 | Um projeto nao conclui sem pelo menos um objeto |
| INV-003 | Cada transicao de ciclo de vida deixa um `UseEvent` |
| INV-004 | Editar detalhes nunca gera evento de ciclo de vida |
| INV-005 | Nenhuma entrada de diario e apagada em cascata sem confirmacao explicita |
| INV-006 | Um diario concluido nao recebe objetos novos |
| INV-007 | Todo o anexo tem descricao |
| INV-008 | A escrita no diario de publicacoes respeita fase e papel |
| INV-009 | Um projeto de seguimento nunca herda diarios do projeto de origem |
| INV-010 | Post-its sao privados da permissao que os criou |
| INV-011 | Evidencia de visita executada exige projeto `COMPLETED` com evento de conclusao |

## 6. Criterios de aceitacao

### CA-001 — Ciclo de vida e suas guardas
→ `test_api.py::test_complete_project_without_objects_returns_409`, `test_domain_models.py::test_cancel_project_blocks_completed_project`, `::test_cancel_project_blocks_already_cancelled_project`, `::test_submitted_project_records_requested_event`

### CA-002 — Notificacao do requerente nas transicoes
→ `test_api.py::test_start_project_notifies_external_requester`, `::test_complete_project_notifies_external_requester`, `::test_cancel_project_notifies_external_requester`

### CA-003 — Edicao de detalhes sem evento e com guardas
→ `test_api.py::test_staff_can_patch_project_details`, `::test_patch_project_requires_staff`, `::test_patch_project_invalid_date_range_returns_422`, `::test_patch_project_terminal_status_returns_409`, `test_domain_models.py::test_edit_project_updates_metadata_without_lifecycle_event`, `::test_edit_project_blocks_terminal_status`, `::test_edit_project_rejects_invalid_effective_date_range`

### CA-004 — Objetos: acrescento, sincronizacao e bloqueios
→ `test_api.py::test_staff_can_add_project_objects`, `::test_add_project_objects_requires_staff`, `::test_add_project_objects_terminal_status_returns_409`, `::test_add_project_objects_syncs_new_objects_to_existing_access_log`, `::test_add_project_objects_creates_access_log_when_missing`, `::test_add_project_objects_blocks_when_access_log_concluded`

### CA-005 — Remocao de objetos, dependencias e cascata confirmada
→ `test_api.py::test_staff_can_remove_unused_project_object`, `::test_remove_project_object_removes_automatic_log_entry`, `::test_remove_project_object_blocks_with_dependencies`, `::test_remove_project_object_cascade_requires_confirmation`, `::test_remove_project_object_cascade_removes_dependencies`

### CA-006 — Diario de acesso: criacao, edicao parcial e ausencia
→ `test_api.py::test_add_log_entry_returns_201_with_access_log_created`, `::test_edit_log_entry_updates_editable_fields`, `::test_edit_log_entry_is_partial_and_clears_observations`, `::test_edit_log_entry_unknown_entry_returns_404`, `::test_log_entry_links_to_requested_object_over_http`, `::test_get_object_access_log_returns_404_without_entries`

### CA-007 — Diario de ocorrencias
→ `test_api.py::test_add_occurrence_entry_returns_201_with_occurrence_log_created`, `::test_edit_occurrence_entry_updates_editable_fields`, `::test_edit_occurrence_entry_is_partial_and_clears_testimonial`, `::test_get_object_occurrence_log_returns_404_without_entries`

### CA-008 — Anexos com descricao, tipo valido e armazenamento cifrado
→ `test_api.py::test_log_entry_attachment_requires_description`, `::test_log_entry_attachment_invalid_media_type_returns_422`, `::test_log_entry_attachment_uses_configured_encrypted_storage`, `::test_download_log_entry_attachment_returns_file`, `::test_download_log_entry_attachment_unknown_reference_returns_404`, `::test_delete_log_entry_attachment_removes_file`, `::test_occurrence_entry_attachment_requires_description`

### CA-009 — Diario de publicacoes: fase e papel
→ `test_api.py::test_add_publication_entry_in_progress_external_creates_log`, `::test_add_publication_entry_staff_while_in_progress_rejected`, `::test_add_publication_entry_staff_once_completed_ok`, `::test_add_publication_entry_external_once_completed_rejected`, `::test_add_publication_entry_in_created_status_rejected`, `::test_add_publication_entry_rejects_foreign_collection_use_object_id`

### CA-010 — Projetos de seguimento
→ `test_api.py::test_staff_can_create_follow_up_project`, `::test_follow_up_project_requires_staff`, `::test_follow_up_project_rejects_non_completed_origin`, `::test_follow_up_project_rejects_empty_object_ids`, `::test_follow_up_project_rejects_invalid_date_range`, `::test_follow_up_project_does_not_copy_journal_logs`, `::test_follow_up_project_owner_can_access_created_follow_up_project`

### CA-011 — Post-its isolados por perfil
→ `test_project_todos.py::test_todo_items_are_isolated_by_staff_permission`, `::test_todo_update_toggle_and_delete_require_item_owner`, `::test_external_callers_cannot_use_project_todos`, `::test_dashboard_postits_list_only_current_staff_profile_items`, `::test_todo_text_is_trimmed_and_limited`

### CA-012 — Documentos oficiais gerados
→ `test_api.py::test_download_object_access_log_document_fills_the_rais_form`, `::test_download_object_access_log_document_is_denied_to_other_researchers`, `::test_download_object_access_log_document_falls_back_to_proposal_contact`, `::test_download_object_access_log_document_returns_404_without_log`, `::test_download_object_occurrence_document_fills_the_roc_form`, `::test_download_object_occurrence_document_returns_404_without_log`

### CA-013 — Evidencia de visita executada
→ `test_domain_models.py::test_visit_execution_evidence_rejects_created_project`, `::test_visit_execution_evidence_rejects_in_progress_project`, `::test_visit_execution_evidence_accepts_completed_project_with_event`

### CA-014 — Formas de resposta estaveis
→ `test_golden_contracts.py::test_golden_project_detail_and_list_shapes`, `::test_golden_project_events_envelope_shape`, `::test_golden_log_entries_shapes`, `::test_golden_occurrence_entries_shapes`, `::test_golden_publication_entries_shapes`, `::test_golden_error_bodies`, `::test_golden_access_denied_body`

### CA-015 — Regra de fase e papel no diario de publicacoes
Dado um projeto em cada estado
Quando cada perfil tenta registar uma publicacao
Entao so o requerente externo escreve em `IN_PROGRESS`, so o staff curatorial escreve em `COMPLETED`, e `CREATED` nao aceita ninguem
→ `test_api.py::test_add_publication_entry_in_progress_external_creates_log`, `::test_add_publication_entry_staff_while_in_progress_rejected`, `::test_add_publication_entry_staff_once_completed_ok`, `::test_add_publication_entry_external_once_completed_rejected`, `::test_add_publication_entry_in_created_status_rejected`

### CA-016 — Entrada, correcao, remocao e anexos
Dado um diario de publicacoes com entradas
Quando uma entrada e corrigida, apagada ou recebe anexos
Entao a nota e atualizada, a remocao leva os anexos consigo, o anexo exige descricao, e uma entrada de outro projeto responde `404`
→ `test_api.py::test_edit_publication_entry_updates_note`, `::test_delete_publication_entry_removes_entry_and_attachments`, `::test_delete_publication_entry_returns_404_for_another_project`, `::test_publication_entry_attachment_upload_and_download`, `::test_publication_entry_attachment_requires_description`, `::test_delete_publication_entry_attachment_removes_file`

### CA-017 — Objeto referido tem de ser do projeto
Dado uma entrada que refere um objeto de uso
Quando o objeto pertence a outro projeto
Entao a entrada e recusada; com um objeto do proprio projeto e aceite e a referencia aparece na entrada
→ `test_api.py::test_add_publication_entry_with_collection_use_object_id`, `::test_add_publication_entry_rejects_foreign_collection_use_object_id`

### CA-018 — Diario e documento oficial so quando existem
Dado um projeto sem qualquer entrada de publicacao
Quando o diario ou o documento RRP sao pedidos
Entao ambos respondem `404`; com diario, o documento sai preenchido
→ `test_api.py::test_get_publication_log_returns_404_without_entries`, `::test_download_publication_log_document_returns_404_without_log`, `::test_download_publication_log_document_fills_the_complete_rrp`

## 7. Requisitos nao funcionais

- **Contratos dourados**: as formas de resposta do projeto e dos diarios estao fixadas por testes; alterar exige atualizar documentacao e testes.
- **Ficheiros**: anexos vivem sob `DATA_DIR`, com cifragem em repouso quando configurada; nunca em caminhos absolutos arbitrarios.
- **Sensibilidade**: registos de colecao, emails de requerentes e documentos carregados sao dados sensiveis.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Agregado do projeto e diarios (RF-002..RF-004, RF-009..RF-012) | `app/use_of_collections/domain/models.py` |
| Ciclo de vida e objetos (RF-002..RF-007, RF-013) | `app/use_of_collections/application/use_cases/project.py` |
| Diarios de acesso e ocorrencias (RF-009..RF-011) | `app/use_of_collections/application/use_cases/journal.py` |
| Diario de publicacoes (RF-012, RF-018) | `app/use_of_collections/application/use_cases/publication.py` |
| Endpoints dos diarios (RF-018, RF-019) | `app/use_of_collections/presentation/journal_routes.py` |
| Post-its (RF-014) | `app/use_of_collections/application/use_cases/project_todos.py` |
| Documentos oficiais (RF-015) | `app/use_of_collections/infrastructure/{object_access_log_docx,object_occurrence_docx,docx_rendering}.py` |
| Linguagem publicada | `app/use_of_collections/public.py` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 9. Questoes em aberto

1. A regra de escrita do diario de publicacoes exclui o investigador depois da conclusao: e o comportamento pretendido a longo prazo, dado que a publicacao costuma sair **depois** do projeto terminar?
2. Deve existir reabertura supervisionada de um diario concluido?
