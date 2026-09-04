# SPEC-014 — Catalogo de colecoes e indice pesquisavel de objetos

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-014 |
| Estado | Implementado |
| Contexto delimitado | `app/collection_object_index` |
| Escrita a partir de | `app/collection_object_index/`, `test/collection_object_index/`, contrato 15 |
| Specs relacionadas | [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-007](../007-identidade-e-acesso/spec.md) |

## 1. Problema

Os dados das colecoes cientificas do museu vivem em folhas de calculo mantidas
por quem curadoria cada colecao. Um investigador que queira identificar objetos
precisa de os pesquisar; a instituicao precisa de saber que ficheiro, que folha
e que linha originaram cada resultado.

## 2. Objetivo

Ingerir folhas de calculo `.xlsx` por colecao, indexar uma linha por linha da
folha, e oferecer ao staff uma pesquisa que devolve, alem do resultado, **a sua
proveniencia** e um instantaneo pronto a anexar a uma proposta.

## 3. Linguagem ubiqua

- **Area de colecao**: classificacao administrativa/cientifica que agrupa colecoes (ex.: "Historia Natural").
- **Colecao**: unidade de curadoria e de permissao (ex.: Zoologia).
- **Curador**: permissao `CURATORIAL` atribuida a uma colecao concreta.
- **Documento de origem**: ficheiro `.xlsx` carregado. Estados `UPLOADED`, `INDEXED`, `ERROR`.
- **Mapeamento de objeto**: que colunas do ficheiro significam numero de inventario, titulo, nome do objeto, descricao e conteudo pesquisavel.
- **Linha indexada**: uma linha da folha, com as suas celulas e coordenadas.
- **Razao de correspondencia**: explicacao compacta de por que uma linha entrou nos resultados.

## 4. Escopos de autorizacao

Impostos **no servidor**; o menu do frontend nao e fronteira de seguranca.

| Escopo | Pode |
| --- | --- |
| `SYS_ADMIN` | Unico administrador do catalogo: criar, renomear e remover colecoes e areas, mover colecoes entre areas, atribuir e remover curadores |
| `SYS_ADMIN` e `COLLECTIONS_MANAGEMENT` | Gerir documentos de origem de **qualquer** colecao |
| `CURATORIAL` | Gerir documentos de origem **apenas** das colecoes que curadoria |
| Outro staff (ex.: `DIRECTION`) | Listar o catalogo em leitura, sem nada gerivel |
| Nao-staff | `403` |

Uma area **nao** concede autorizacao: o ambito de um curador resulta apenas das
colecoes que lhe estao atribuidas.

---

## 5. Requisitos funcionais

### RF-001 — Areas de colecao

CRUD de areas restrito a `SYS_ADMIN`. A listagem inclui a contagem de colecoes.
Nome duplicado responde `409`. Remover uma area em uso responde `409`.

### RF-002 — Colecoes

CRUD de colecoes restrito a `SYS_ADMIN`, incluindo mover uma colecao para outra
area por `POST /admin/collection-data-sources/collections/{collectionId}/move-area`
com `areaId` no corpo. Nome duplicado — inclusive apos aparar espacos — responde
`409`. Colecao desconhecida e area desconhecida respondem ambas `404`, com
`COLLECTION_NOT_FOUND` e `COLLECTION_AREA_NOT_FOUND` respetivamente; a resposta
devolve a colecao ja na area nova.

Remover uma colecao apaga tudo o que lhe pertence e **recupera os ficheiros**.

### RF-003 — Campo `manageable` decidido pelo servidor

Cada colecao devolvida traz `manageable`, calculado a partir do escopo do
chamador. Um curador cuja permissao ja nao resolve em identidade continua
listado pelo seu `permissionId`, com nome e email nulos.

### RF-004 — Curadores

Atribuir e remover curadores e exclusivo de `SYS_ADMIN`; a atribuicao regista
quem a fez. Candidatos a curador sao apenas permissoes do grupo `CURATORIAL`, e
a listagem de candidatos e vedada a quem nao seja `SYS_ADMIN`.

### RF-005 — Pre-visualizacao de colunas

`POST .../documents/columns-preview` analisa a folha e devolve a uniao ordenada
dos nomes de coluna **sem guardar o ficheiro e sem indexar**. E o passo que
permite ao utilizador escolher o mapeamento antes de submeter.

### RF-006 — Carregamento com mapeamento obrigatorio

`POST .../collections/{id}/documents` carrega e indexa sincronamente. Exige
ficheiro `.xlsx` real (validado por assinatura) e o mapeamento semantico:
coluna do numero de inventario, colunas de titulo, coluna de nome do objeto
(vazia significa recorrer ao titulo), colunas de descricao e colunas
pesquisaveis.

O mapeamento e validado contra a folha analisada **antes** da indexacao. Colunas
desconhecidas respondem `422 SOURCE_DOCUMENT_MAPPING_INVALID`; conjunto de
colunas pesquisaveis vazio responde `422
SOURCE_DOCUMENT_SEARCHABLE_COLUMNS_EMPTY`.

### RF-007 — Idempotencia por conteudo

| Situacao | Comportamento |
| --- | --- |
| Ficheiro identico ja vivo na colecao | Deduplica; devolve o documento existente |
| Mesmo nome, conteudo diferente | Nova versao: o anterior e apagado de forma logica e as suas linhas removidas antes de indexar o novo |
| Falha de analise ou limite de linhas excedido | Persiste como `ERROR`, mantendo o ficheiro e a mensagem |

Guardar o ficheiro de uma falha e deliberado: o administrador ve o problema no
ecra em vez de perder o carregamento.

### RF-008 — Analise da folha

O cabecalho de cada folha define as chaves das celulas; cada linha guarda as
suas coordenadas. Linhas totalmente vazias sao ignoradas. Valores sao
normalizados. Cabecalhos duplicados ou vazios recebem chaves estaveis. Varias
folhas tem, cada uma, o seu cabecalho. Conteudo que nao seja uma folha valida
levanta erro tipado.

### RF-009 — Conteudo indexado segue as colunas pesquisaveis

Apenas as colunas declaradas pesquisaveis sao concatenadas no conteudo indexado.
Alterar essas colunas **reconstroi** as linhas indexadas do documento.

`contentMatchesSearchableColumns = false` assinala um documento legado cujo
conteudo persistido ainda nao foi reconstruido sob a regra de colunas nomeadas.

### RF-010 — Alteracao de mapeamento resiliente

`PUT .../documents/{id}/object-mapping` valida as colunas e reindexa. Se a
reindexacao falhar, o mapeamento anterior e o indicador de legado sao
preservados: uma falha nao deixa o documento num estado que ninguem declarou.

### RF-011 — Reindexacao

`POST .../documents/{id}/reindex` reconstroi as linhas a partir do ficheiro
guardado. Sucesso marca o documento como coerente com as colunas pesquisaveis;
falha preserva o indicador de legado. Um ficheiro guardado que ja nao seja folha
valida coloca o documento em `ERROR`.

### RF-012 — Remocao de documento

Remove as linhas indexadas, apaga o documento de forma logica e recupera o
ficheiro **apos** a transacao ficar duravel.

### RF-013 — Pesquisa de objetos

`GET /objects/search` devolve resultados paginados com colecao, documento de
origem, nome do ficheiro, folha, numero da linha, celulas, excerto realcado, o
instantaneo do objeto e as razoes de correspondencia. Consulta vazia e recusada.
A pesquisa e acessivel a staff e vedada a nao-staff.

### RF-014 — Razoes de correspondencia por prioridade

Cada resultado traz no maximo uma razao, escolhida por prioridade:
`exact > substring > text > approximate`. `columns` pode vir vazio quando o
metodo e conhecido mas a coluna de origem nao e atribuivel com fiabilidade.

`semantic` **nao** e devolvido enquanto a pesquisa semantica nao existir: nomear
um metodo que nao esta implementado seria descrever uma capacidade inexistente.

### RF-015 — Instantaneo pronto a propor

Cada resultado traz numero de inventario, titulo, nome do objeto, descricao
resumida e categoria, prontos a serem anexados a uma proposta
([SPEC-008](../008-proposta-uso-de-colecoes/spec.md), RF-002).

### RF-016 — Facetas de pesquisa

`GET /objects/search/collections` lista as colecoes pesquisaveis com um resumo
das colunas pesquisaveis e a contagem total distinta. Para documentos legados
com conjunto vazio, as chaves das celulas da linha indexada sao tratadas como o
conjunto efetivo.

### RF-017 — Documentos apagados saem da pesquisa

Linhas de um documento de origem apagado nao aparecem nos resultados.

### RF-018 — Candidatos a curador

`GET /admin/collection-data-sources/curator-candidates` devolve as permissoes
elegiveis para curadoria de uma colecao: **apenas** as do grupo `CURATORIAL`,
com `permissionId`, nome e email. Restrito a `SYS_ADMIN`, como o resto da
administracao do catalogo; qualquer outro chamador recebe `403`.

A lista e derivada da Identidade atraves do leitor de permissoes publicado, nao
de estado proprio deste contexto. Pertencer ao grupo torna alguem **elegivel**;
nao lhe concede ambito nenhum enquanto nao for atribuido a uma colecao concreta.

---

## 6. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | O escopo de gestao e decidido no servidor, colecao a colecao |
| INV-002 | Uma area nunca concede autorizacao por si |
| INV-003 | Nenhum documento e indexado sem mapeamento validado |
| INV-004 | Uma falha de analise nunca perde o ficheiro carregado |
| INV-005 | Uma reindexacao falhada nunca corrompe o mapeamento em vigor |
| INV-006 | O conteudo indexado corresponde as colunas pesquisaveis declaradas, ou o documento e marcado como legado |
| INV-007 | Cada resultado de pesquisa identifica ficheiro, folha e linha de origem |
| INV-008 | Ficheiros so sao recuperados depois de a transacao ficar duravel |

## 7. Criterios de aceitacao

### CA-001 — Analise da folha
→ `test_parser.py::test_header_becomes_cell_keys_and_rows_keep_coordinates`, `::test_fully_empty_rows_are_skipped`, `::test_multiple_sheets_each_have_their_own_header`, `::test_values_are_normalized`, `::test_duplicate_and_blank_headers_get_stable_keys`, `::test_invalid_bytes_raise_invalid_spreadsheet`

### CA-002 — Carregamento, pre-visualizacao e validacao do mapeamento
→ `test_api.py::test_upload_indexes_and_returns_document`, `::test_preview_upload_columns_without_indexing`, `::test_configure_source_document_object_mapping`, `::test_configure_source_document_object_mapping_rejects_unknown_column`, `::test_upload_rejects_empty_searchable_columns_with_specific_error`, `::test_upload_rejects_non_xlsx_content`, `::test_upload_to_unknown_collection_is_404`

### CA-003 — Idempotencia por conteudo e versoes
→ `test_use_cases.py::test_identical_reupload_dedupes`, `::test_deduped_reupload_reindexes_and_marks_legacy_flag_true`, `::test_new_version_replaces_previous_source_and_rows`

### CA-004 — Conteudo indexado segue colunas pesquisaveis
→ `test_use_cases.py::test_upload_indexes_rows_and_marks_indexed`, `::test_upload_indexes_only_searchable_columns_in_content`, `::test_update_object_mapping_reindexes_searchable_content`, `::test_list_columns_and_update_object_mapping`, `::test_update_object_mapping_rejects_unknown_columns`, `::test_searchable_columns_empty_is_rejected_for_user_commands`

### CA-005 — Falhas preservam estado coerente
→ `test_use_cases.py::test_failed_update_object_mapping_preserves_mapping_and_legacy_flag`, `::test_failed_reindex_preserves_legacy_flag`, `::test_error_status_when_stored_file_is_not_a_spreadsheet`

### CA-006 — Reindexacao e remocao
→ `test_use_cases.py::test_reindex_rebuilds_rows_from_stored_file`, `::test_reindex_success_marks_legacy_flag_true`, `::test_delete_removes_index_rows_and_soft_deletes`, `test_api.py::test_reindex_returns_updated_document`, `::test_delete_document_removes_and_reclaims_after_commit`

### CA-007 — Escopos de gestao
→ `test_use_cases.py::test_curator_cannot_manage_unassigned_collection`, `::test_assigned_curator_manages_their_collection`, `::test_collections_management_manages_any_collection`, `::test_curator_cannot_assign_curators`, `::test_assign_records_assigned_by_and_remove_revokes`, `::test_list_manageable_collections_flags_scope`, `test_api.py::test_curator_upload_out_of_scope_is_403`, `::test_assign_then_curator_manages_and_delete_reclaims_file`, `::test_assign_curator_rejects_non_curatorial_permission`, `::test_external_caller_is_forbidden`

### CA-008 — Administracao do catalogo restrita a `SYS_ADMIN`
→ `test_api.py::test_create_get_and_update_collection`, `::test_create_collection_duplicate_name_is_409`, `::test_create_collection_duplicate_name_after_trim_is_409`, `::test_create_collection_unknown_area_is_404`, `::test_create_collection_blocked_for_curator`, `::test_remove_collection_deletes_everything_and_reclaims_files`, `::test_remove_collection_blocked_for_curator`, `::test_curator_candidates_blocked_for_non_sys_admin`, `::test_curator_candidates_lists_curatorial_group_only`

### CA-009 — Areas e movimentacao de colecoes
→ `test_api.py::test_list_collection_areas_shows_counts`, `::test_create_rename_and_remove_collection_area`, `::test_create_collection_area_duplicate_name_is_409`, `::test_remove_collection_area_in_use_is_409`, `::test_move_collection_to_area`, `::test_move_collection_to_unknown_area_is_404`, `::test_move_collection_to_area_blocked_for_curator`, `::test_list_collection_areas_blocked_for_curator`

### CA-010 — Pesquisa: correspondencia, filtros, paginacao e autorizacao
→ `test_search_api.py::test_search_returns_matching_hits`, `::test_search_filters_by_collection`, `::test_search_paginates`, `::test_search_requires_non_empty_query`, `::test_search_rejects_non_staff`, `::test_searchable_collections_lists_full_catalogue`, `::test_searchable_collections_rejects_non_staff`

### CA-011 — Razoes de correspondencia e proveniencia
→ `test_search_postgres.py::test_search_matches_full_text`, `::test_search_match_reason_prioritises_exact_for_legacy_columns`, `::test_search_match_reason_uses_substring_before_text`, `::test_search_matches_hyphenated_code_partially`, `::test_match_reason_columns_respect_searchable_columns`, `::test_searchable_collection_scope_summarises_columns`

### CA-012 — Documento apagado sai da pesquisa
→ `test_search_postgres.py::test_search_excludes_rows_of_deleted_source_document`, `::test_search_paginates_without_overlap`, `::test_search_finds_no_match_returns_empty`

### CA-013 — Mover colecao de area
Dado uma colecao e uma area existentes
Quando `SYS_ADMIN` move a colecao para essa area
Entao a resposta devolve a colecao na area nova; uma area desconhecida, uma colecao desconhecida e um chamador que nao seja `SYS_ADMIN` respondem `404`, `404` e `403`
→ `test_api.py::test_move_collection_to_area`, `::test_move_collection_to_unknown_area_is_404`, `::test_move_unknown_collection_to_area_is_404`, `::test_move_collection_to_area_blocked_for_curator`, `test_use_cases.py::test_move_collection_to_area`, `::test_move_collection_to_area_raises_not_found_for_unknown_area`, `::test_move_unknown_collection_to_area_raises_not_found`

### CA-014 — Candidatos a curador limitados ao grupo curatorial
Dado permissoes distribuidas por varios grupos
Quando `SYS_ADMIN` pede os candidatos a curador
Entao devolve so as do grupo `CURATORIAL`; qualquer outro chamador recebe `403`
→ `test_api.py::test_curator_candidates_lists_curatorial_group_only`, `::test_curator_candidates_blocked_for_non_sys_admin`, `test_use_cases.py::test_list_curator_candidates_returns_curatorial_group_only`, `::test_list_curator_candidates_blocked_for_non_sys_admin`

## 8. Requisitos nao funcionais

- **Pesquisa em PostgreSQL**: a correspondencia usa as capacidades de texto do motor; os testes de pesquisa exercitam a base real.
- **Limite de linhas**: folhas acima do limite configurado falham de forma visivel, nao silenciosa.
- **Ficheiros**: guardados sob `DATA_DIR`, fora de qualquer raiz web.

## 9. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Modelo do catalogo e do indice | `app/collection_object_index/domain/` |
| Analise de folhas (RF-008) | `app/collection_object_index/infrastructure/` (parser) |
| Casos de uso de ingestao e escopos (RF-005..RF-012) | `app/collection_object_index/application/` |
| Pesquisa e razoes (RF-013, RF-014, RF-016) | `app/collection_object_index/infrastructure/` (pesquisa PostgreSQL) |
| Endpoints | `app/collection_object_index/presentation/` |
| Mover colecao e candidatos a curador (RF-002, RF-018) | `app/collection_object_index/application/use_cases.py` (`MoveCollectionToArea`, `ListCuratorCandidates`) |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 10. Questoes em aberto

1. Um curador devia poder gerir todas as colecoes de uma area? Hoje a area nao concede escopo; a decisao esta em aberto no contrato.
2. Que politica de retencao para documentos apagados de forma logica e para os seus ficheiros?
3. A pesquisa semantica, se vier a existir, entra como quinto metodo de correspondencia ou como caminho separado?
