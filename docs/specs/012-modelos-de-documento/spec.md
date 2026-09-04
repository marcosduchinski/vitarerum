# SPEC-012 — Modelos de documento por tipo de uso

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-012 |
| Estado | Implementado |
| Contexto delimitado | `app/document_templates` |
| Escrita a partir de | `app/document_templates/`, `test/document_templates/test_api.py`, contrato 12 |
| Specs relacionadas | [SPEC-010](../010-submissao-publica/spec.md), [SPEC-008](../008-proposta-uso-de-colecoes/spec.md) |

## 1. Problema

O cidadao que submete um pedido tem de anexar formularios institucionais
preenchidos, mas nao sabe quais sao nem onde os obter. Distribui-los por email ou
por uma pagina estatica leva a versoes desatualizadas em circulacao.

## 2. Objetivo

Manter um catalogo curado de modelos `.docx` por tipo de uso, oferecido sem
autenticacao no ecra publico de submissao, e gerido pelo staff.

## 3. Atores

| Ator | Papel |
| --- | --- |
| Cidadao (sem autenticacao) | Lista e descarrega modelos **ativos** do tipo de uso escolhido |
| `CURATORIAL`, `COLLECTIONS_MANAGEMENT`, `DIRECTION`, `SYS_ADMIN` | Gerem o catalogo |

---

## 4. Requisitos funcionais

### RF-001 — Listagem publica por tipo de uso

`GET /api/v1/public/document-templates?useType={UseType}` devolve os modelos
**ativos** do tipo indicado, ordenados por `displayOrder` e depois por titulo.
`useType` e obrigatorio; sem modelos configurados, devolve lista vazia.

O item publico expoe apenas `id`, `title`, `description` e `mandatory` — nunca os
campos de curadoria.

### RF-002 — Descarga publica so de modelos ativos

`GET /public/document-templates/{id}/file` transmite o `.docx`. Um modelo
desativado responde `404` **mesmo a quem conhece o identificador**: desativar
retira do alcance publico, nao apenas da listagem.

Identificador desconhecido, modelo inativo e ficheiro em falta produzem o mesmo
`404 DOCUMENT_TEMPLATE_NOT_FOUND`.

### RF-003 — Cabecalho de descarga seguro

`Content-Type` e o MIME de DOCX e `Content-Disposition: attachment` carrega um
nome de ficheiro sanitizado: apenas o nome base, sem separadores de caminho e
imune a injecao de cabecalho.

### RF-004 — Listagem do staff inclui inativos

`GET /document-templates?useType=` devolve **todos** os modelos, ativos e
inativos. Sem `useType`, lista todos os tipos, agrupados por tipo e
`displayOrder`. O item de staff acrescenta `useType`, `active`, `displayOrder`,
`fileName` e `uploadedAt`.

### RF-005 — Descarga pelo staff em qualquer estado

`GET /document-templates/{id}/file` serve modelos em qualquer estado, para o
staff poder rever um modelo desativado antes de o reativar ou substituir. Aplica
o mesmo tratamento seguro de cabecalho.

### RF-006 — Criacao

`POST /document-templates` (`multipart/form-data`) exige `file`, `useType` e
`title`. `description` assume `""`, `mandatory` assume `false`, `active` assume
`true` e `displayOrder` assume `0`.

O ficheiro e validado por **assinatura de conteudo**, nao apenas pela extensao;
um ficheiro que nao seja DOCX real responde `415 INVALID_FILE_FORMAT`. Ficheiro
demasiado grande responde `413`.

### RF-007 — Nome de ficheiro sanitizado no armazenamento

O nome guardado e reduzido ao nome base. Uma tentativa de travessia de caminho
no nome enviado nao alcanca o sistema de ficheiros.

### RF-008 — Edicao de metadados por substituicao total

`PATCH /document-templates/{id}` substitui os metadados editaveis: titulo,
descricao, obrigatoriedade, atividade e ordem. O formulario de gestao envia todos
os campos.

### RF-009 — Substituicao do ficheiro

`PUT /document-templates/{id}/file` substitui o `.docx` guardado e devolve o item
atualizado com o novo nome. Mesma validacao de formato da criacao.

### RF-010 — Remocao

`DELETE /document-templates/{id}` remove o modelo **e** o ficheiro guardado,
respondendo `204`.

### RF-011 — Limpeza quando a transacao falha

Se a persistencia falhar depois de o ficheiro ser escrito, o ficheiro e
removido.

### RF-012 — Obrigatoriedade meramente informativa

`mandatory` e hoje informacao mostrada ao cidadao. **Nao** e imposta na
submissao: um pedido sem o modelo obrigatorio anexado nao e recusado por esta
razao.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | O publico nunca alcanca um modelo inativo, nem por identificador direto |
| INV-002 | A resposta publica nunca expoe campos de curadoria |
| INV-003 | Apenas ficheiros DOCX reais entram no catalogo |
| INV-004 | Nomes de ficheiro sao sempre reduzidos ao nome base |
| INV-005 | Apagar um modelo apaga o seu ficheiro |
| INV-006 | Um ficheiro escrito sem transacao concluida nao permanece |
| INV-007 | Os endpoints de gestao sao vedados a nao-staff |

## 6. Criterios de aceitacao

### CA-001 — Listagem publica so com ativos do tipo pedido
→ `test_api.py::test_public_list_returns_only_active_for_use_type`

### CA-002 — Descarga publica e ocultacao de inativos
→ `test_api.py::test_public_download_streams_docx`, `::test_public_download_missing_returns_404`, `::test_public_download_hides_inactive_template`

### CA-003 — Cabecalho de descarga seguro
→ `test_api.py::test_public_download_uses_safe_content_disposition`

### CA-004 — Staff descarrega e lista inativos
→ `test_api.py::test_staff_download_serves_inactive_template`, `::test_staff_list_includes_inactive`

### CA-005 — Criacao valida formato e sanitiza nome
→ `test_api.py::test_staff_create_persists_template_and_file`, `::test_staff_create_rejects_non_docx`, `::test_staff_create_sanitizes_traversal_filename`

### CA-006 — Limpeza quando o commit falha
→ `test_api.py::test_staff_create_cleans_up_file_when_commit_fails`

### CA-007 — Edicao, substituicao e remocao
→ `test_api.py::test_staff_patch_updates_metadata`, `::test_staff_patch_missing_returns_404`, `::test_staff_replace_file_swaps_stored_bytes`, `::test_staff_delete_removes_template_and_file`

### CA-008 — Autorizacao dos endpoints de gestao
→ `test_api.py::test_staff_endpoints_forbidden_for_external`, `::test_staff_download_forbidden_for_external`

## 7. Requisitos nao funcionais

- **Modelo de confianca publico**: os endpoints publicos seguem o mesmo modelo da submissao publica — sem cookies, sem credenciais, CORS restrito.
- **Armazenamento**: ficheiros sob `DATA_DIR`, fora de qualquer raiz web.

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Modelo e casos de uso | `app/document_templates/domain/`, `application/` |
| Validacao de formato e armazenamento (RF-006, RF-007, RF-011) | `app/document_templates/infrastructure/` |
| Endpoints publicos e de staff | `app/document_templates/presentation/` |
| Contrato publico | Esquema OpenAPI em `/openapi.json`; regras transversais em `docs/api_contracts/README.md` |

## 9. Questoes em aberto

1. Quando (e se) `mandatory` passar a ser imposto na submissao, o que acontece a pedidos ja pendentes sem o anexo?
2. Deve existir versionamento dos modelos, para saber que versao um requerente descarregou?
