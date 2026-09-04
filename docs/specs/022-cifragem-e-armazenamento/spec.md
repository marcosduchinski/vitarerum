# SPEC-022 — Cifragem em repouso e armazenamento de ficheiros

| Campo | Valor |
| --- | --- |
| Identificador | SPEC-022 |
| Estado | Implementado |
| Alcance | Transversal — `app/shared` (nucleo partilhado), consumido por todos os contextos |
| Escrita a partir de | `app/shared/{field_encryption,file_encryption,file_storage,persistence}.py`, `test/shared/`, `docs/architecture/encryption-contracts.md` |
| Specs relacionadas | [SPEC-011](../011-perguntas-ao-museu/spec.md), [SPEC-002](../002-vigilancia-retorno-cientifico/spec.md), [SPEC-009](../009-projeto-uso-de-colecoes/spec.md) |

## 1. Problema

O sistema guarda dados que identificam pessoas e revelam interesses de
investigacao: emails de requerentes, mensagens de cidadaos, documentos
carregados, e a associacao entre um investigador, um projeto e os objetos que
consultou. Guardar isto em claro coloca a confidencialidade inteiramente nas maos
do acesso a base de dados e ao sistema de ficheiros.

## 2. Objetivo

Cifrar campos e ficheiros sensiveis em repouso, mantendo-os pesquisaveis onde e
necessario, e fixar como **contrato criptografico** os identificadores usados
como dados associados.

## 3. Linguagem ubiqua

- **Campo cifrado**: valor de coluna guardado cifrado com AES-GCM.
- **Dados associados (AAD)**: cadeia autenticada junto com o texto cifrado, que o liga ao seu lugar.
- **Hash de pesquisa**: derivacao estavel de um valor cifrado que permite procura por igualdade.
- **Referencia de ficheiro (`file_reference`)**: endereco relativo e duravel de um ficheiro guardado.
- **Campo corrompido**: qualquer texto cifrado que nao autentica.

---

## 4. Requisitos funcionais

### RF-001 — Cifragem de campo com nonce distinto

Um valor cifrado e decifrado devolve o original. O texto cifrado nunca contem o
texto em claro. O **mesmo** valor cifrado duas vezes produz textos cifrados
diferentes, porque cada operacao usa um nonce proprio.

### RF-002 — Dados associados dos campos

Um campo cifrado autentica o seu nome logico como dados associados, na forma
exata:

```text
<nome_da_tabela>.<nome_da_coluna>
```

Consequencia: renomear uma tabela ou coluna cifrada **nao e** uma refatoracao de
esquema. Os valores escritos sob os dados associados antigos nao decifram sob os
novos.

Qualquer migracao que renomeie tem de decifrar e recifrar sob a nova cadeia
exata, ou manter um caminho de leitura versionado que aceite a anterior ate a
reescrita estar concluida.

Os dados associados **nao** sao normalizados, alcunhados nem derivados
dinamicamente: os nomes literais do mapeamento ORM sao o contrato.

### RF-003 — Falhas de integridade sao explicitas

Levantam erro tipado de campo corrompido: dados associados que nao correspondem,
prefixo em falta, versao desconhecida, base64 invalido e texto cifrado adulterado.

Um valor que nao autentica nunca e devolvido como se fosse valido.

### RF-004 — Ausencia preservada

Um valor nulo permanece nulo. A cifragem nao converte ausencia em presenca.

### RF-005 — Hash de pesquisa estavel e normalizado

Emails cifrados possuem hash de pesquisa normalizado e estavel, que permite
filtrar por igualdade sem decifrar
([SPEC-011](../011-perguntas-ao-museu/spec.md), RF-008). O hash muda com os dados
associados: o mesmo email em contextos diferentes nao produz o mesmo hash.

### RF-006 — Estruturas cifradas

Estruturas serializadas em JSON seguem o mesmo percurso: ida e volta preserva o
valor, e uma descodificacao que falhe levanta campo corrompido.

### RF-007 — Chave validada

Uma chave com comprimento invalido e recusada na construcao, nao no primeiro uso.

### RF-008 — Cifragem de ficheiros

Ficheiros guardados sao cifrados: o blob nunca contem o conteudo em claro, o
mesmo conteudo produz blobs distintos, e conteudo adulterado, chave errada,
cabecalho de versao ausente ou blob truncado levantam erro de ficheiro
corrompido. Um ficheiro vazio faz ida e volta corretamente.

### RF-009 — Referencia de ficheiro como dados associados

O blob cifrado autentica a `file_reference` como dados associados. Um blob
escrito para uma referencia **nao decifra** noutra: mover ou renomear objetos
guardados exige decifrar e recifrar sob as referencias exatas registadas na base
de dados.

A `file_reference` e um caminho relativo estavel — nunca um caminho absoluto, URL,
URI de objeto ou identificador especifico de fornecedor. O nome de balde, volume
ou diretorio base pertence a configuracao de execucao e nao entra na referencia.

Adaptadores futuros de armazenamento devem preservar esta propriedade.

### RF-010 — Cifragem opcional por configuracao

Sem chave configurada, o armazenamento e simples; com chave, o armazenamento
simples e envolvido pela camada de cifragem. A decisao e da composicao, e os
contextos consumidores nao mudam.

### RF-011 — Armazenamento seguro e atomico

O armazenamento de ficheiros:

- escreve de forma atomica e nao deixa ficheiros temporarios;
- recusa travessia de caminho na leitura;
- levanta erro na leitura de ficheiro inexistente;
- apaga de forma idempotente;
- suporta subpastas.

### RF-012 — Repeticao em operacoes de persistencia

Existe utilitario de repeticao para operacoes de persistencia sujeitas a conflito
transitorio: repete ate ter sucesso e volta a levantar o erro depois de esgotar
as tentativas ([SPEC-010](../010-submissao-publica/spec.md), RF-009).

### RF-013 — Politica de autorizacao partilhada

O nucleo partilhado reconhece os grupos de staff e oferece as verificacoes usadas
transversalmente: exigir grupo, exigir staff, e acesso a proposta e a projeto —
com o proprietario e o staff autorizados, e um `EXTERNAL` que nao seja o
proprietario recusado. Um projeto sem proposta associada continua acessivel ao
seu proprietario.

### RF-014 — Nucleo partilhado sem dependencias

`app.shared.kernel` mantem-se dependente apenas da biblioteca padrao.

---

## 5. Invariantes

| Id | Invariante |
| --- | --- |
| INV-001 | Nenhum texto cifrado contem o texto em claro |
| INV-002 | Duas cifragens do mesmo valor nunca produzem o mesmo texto cifrado |
| INV-003 | Um valor que nao autentica nunca e devolvido |
| INV-004 | O nome logico do campo faz parte do contrato criptografico |
| INV-005 | A `file_reference` faz parte do contrato criptografico do blob |
| INV-006 | A `file_reference` nunca contem configuracao de infraestrutura |
| INV-007 | Chaves invalidas sao recusadas na construcao |
| INV-008 | `app.shared.kernel` nao depende de terceiros |

## 6. Criterios de aceitacao

### CA-001 — Ida e volta, ausencia de texto em claro e nonce distinto
→ `test_field_encryption.py::test_text_round_trip_returns_original_value`, `::test_ciphertext_does_not_contain_plaintext`, `::test_same_value_encrypts_with_distinct_nonce`, `::test_none_remains_none`

### CA-002 — Falhas de integridade tipadas
→ `test_field_encryption.py::test_aad_mismatch_raises_corrupted_field`, `::test_missing_prefix_raises_corrupted_field`, `::test_unknown_version_raises_corrupted_field`, `::test_invalid_base64_raises_corrupted_field`, `::test_tampered_ciphertext_raises_corrupted_field`, `::test_invalid_key_length_is_rejected`

### CA-003 — Hash de pesquisa normalizado e ligado aos dados associados
→ `test_field_encryption.py::test_email_hash_is_normalized_and_stable`, `::test_hash_changes_with_aad`

### CA-004 — Estruturas JSON cifradas
→ `test_field_encryption.py::test_json_round_trip_returns_original_value`, `::test_json_decode_failure_raises_corrupted_field`

### CA-005 — Cifragem de ficheiros e sua integridade
→ `test_file_encryption.py::test_round_trip_returns_original_content`, `::test_saved_blob_does_not_contain_plaintext`, `::test_same_content_saves_with_distinct_nonce`, `::test_ciphertext_tampering_raises_corrupted_file`, `::test_wrong_key_raises_corrupted_file`, `::test_blob_without_version_header_raises_corrupted_file`, `::test_truncated_versioned_blob_raises_corrupted_file`, `::test_invalid_key_length_is_rejected`, `::test_empty_file_round_trips`

### CA-006 — Blob ligado a sua referencia
→ `test_file_encryption.py::test_aad_binds_blob_to_file_reference`, `::test_delete_delegates_to_inner_storage`

### CA-007 — Armazenamento atomico e seguro
→ `test_file_storage.py::test_round_trip_into_subfolder`, `::test_read_missing_raises`, `::test_read_rejects_path_traversal`, `::test_save_is_atomic_and_leaves_no_temp_files`, `::test_delete_removes_file_and_is_idempotent`

### CA-008 — Cifragem opcional por configuracao
→ `test_file_storage.py::test_build_file_storage_returns_plain_storage_without_key`, `::test_build_file_storage_wraps_storage_when_key_is_configured`, `::test_file_storage_dependencies_use_configured_encryption_key`

### CA-009 — Repeticao de persistencia
→ `test_persistence.py::test_retries_until_success`, `::test_reraises_after_exhausting_attempts`

### CA-010 — Politica de autorizacao partilhada
→ `test_authorization.py::test_staff_groups_are_recognized`, `::test_require_group_rejects_wrong_group`, `::test_require_staff_rejects_external`, `::test_proposal_access_allows_owner_and_staff`, `::test_proposal_access_rejects_non_owner_external`, `::test_project_access_allows_owner_and_staff`, `::test_project_access_rejects_missing_or_foreign_proposal_for_external`, `::test_project_access_allows_owner_without_a_proposal`

## 7. Requisitos nao funcionais

- **Gestao de chaves**: as chaves vivem na configuracao de execucao, nunca no repositorio.
- **Migracoes**: renomear tabela ou coluna cifrada exige plano de reescrita (RF-002).
- **Portabilidade de armazenamento**: mudar de adaptador nao pode alterar a `file_reference` (RF-009).

## 8. Rastreabilidade

| Elemento | Localizacao |
| --- | --- |
| Cifragem de campo (RF-001..RF-007) | `app/shared/field_encryption.py` |
| Cifragem de ficheiro (RF-008, RF-009) | `app/shared/file_encryption.py` |
| Armazenamento (RF-010, RF-011) | `app/shared/file_storage.py`, `uploads.py` |
| Repeticao (RF-012) | `app/shared/persistence.py` |
| Autorizacao partilhada (RF-013) | `app/shared/authorization.py` |
| Nucleo partilhado (RF-014) | `app/shared/kernel.py` |
| Contrato documentado | `docs/architecture/encryption-contracts.md` |

## 9. Questoes em aberto

1. Existe procedimento definido de rotacao de chave, com caminho de leitura versionado durante a transicao?
2. O que acontece operacionalmente quando um campo corrompido e detetado em producao — falha visivel, quarentena, ou registo e continuacao?
