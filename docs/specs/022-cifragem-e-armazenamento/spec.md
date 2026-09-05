# SPEC-022 — Encryption at Rest and File Storage

| Field | Value |
| --- | --- |
| Identifier | SPEC-022 |
| Status | Implemented (with declared migration, key-rotation, coverage, metadata-leakage, and recovery gaps) |
| Scope | Cross-cutting technical adapters in `app/shared`, consumed by multiple bounded contexts |
| Derived from | Shared encryption/storage code, context adapters, configuration, migrations, architecture contracts, deployment files, and automated tests inspected on 2026-09-04 |
| Related specs | [SPEC-002](../002-vigilancia-retorno-cientifico/spec.md), [SPEC-008](../008-proposta-uso-de-colecoes/spec.md), [SPEC-009](../009-projeto-uso-de-colecoes/spec.md), [SPEC-010](../010-submissao-publica/spec.md), [SPEC-011](../011-perguntas-ao-museu/spec.md), [SPEC-012](../012-modelos-de-documento/spec.md), [SPEC-014](../014-catalogo-e-indice-de-objetos/spec.md), [SPEC-023](../023-fronteiras-e-envelope-de-erro/spec.md) |

## 1. Problem

The application persists personal information, citizen correspondence,
research interests, model inputs and outputs, and uploaded documents. Database
or filesystem access must not automatically reveal every protected value in
plaintext, and tampering with protected data must be detected before it is
returned as valid application data.

Encryption at rest is only one layer. It does not replace authorisation,
transport security, secure backups, log redaction, retention, host/volume
protection, or a tested incident-recovery process.

## 2. Goal and scope

Provide reusable application-level adapters that:

- encrypt selected database text/JSON fields with authenticated encryption;
- derive keyed digests for selected equality lookups;
- encrypt complete file contents behind existing storage ports;
- confine local file references beneath a configured data directory; and
- translate detected corruption into generic HTTP failures.

This specification describes implemented protection, not a claim that every
sensitive database column is encrypted. Password hashing, JWT/token hashing,
TLS, infrastructure disk/database encryption, database credentials, secret-
manager integration, backup policy, and the unrelated unique-conflict retry
helper are outside its cryptographic boundary.

## 3. Strategic design and trust boundaries

Encryption and local storage are generic infrastructure services, not a domain
bounded context or aggregate. Domain/application models continue to use
plaintext values in memory. Concrete repositories encrypt while mapping to ORM
records and decrypt while mapping back; composition roots inject the configured
adapters.

| Component | Responsibility |
| --- | --- |
| `FieldEncryptor` | AES-GCM text/JSON sealing, opening, and keyed lookup digests. |
| `EncryptedFileStorage` | Decorate any compatible storage adapter with whole-file AES-GCM encryption. |
| `LocalDiskFileStorage` | Confine, atomically replace, read, and idempotently delete local files. |
| Context repositories | Select protected fields and stable associated-data labels. |
| Context composition roots | Construct encryptors/storage from runtime settings. |
| Global exception handlers | Hide corruption details from HTTP clients while logging the internal identifier. |

The database stores ciphertext, lookup digests, and unencrypted operational
metadata. The local filesystem stores encrypted blobs when file encryption is
enabled. The running API process and any code after repository decryption can
see plaintext; application-level encryption does not defend against a fully
compromised process or key store.

## 4. Ubiquitous language and wire formats

### 4.1 Field ciphertext

An encrypted database field is encoded as:

```text
v1:<base64(12-byte nonce || AES-GCM ciphertext || 16-byte tag)>
```

The textual `v1:` prefix identifies the field format. The application derives
independent 256-bit AES and HMAC subkeys from the 32-byte field master key using
HKDF-SHA-256 with fixed purpose-specific `info` and no salt.

### 4.2 File blob

An encrypted file is encoded as binary:

```text
0x01 || 12-byte nonce || AES-GCM ciphertext || 16-byte tag
```

The first byte identifies the algorithm format, not the encryption key. File
encryption uses its separate 32-byte file key directly.

### 4.3 Associated data

Associated data (AAD) is authenticated but not encrypted. Changing it makes an
otherwise intact ciphertext fail authentication.

For files, AAD is the exact UTF-8 `file_reference`. For database fields, AAD is
the exact literal supplied by each repository. Most phase-one fields use a
`<table>.<logical-column>` form, for example
`museum_questions.requester_email`. Some scientific-return adapters instead
use stable conceptual namespaces such as
`scientific_return.full_agentic.tool.result`; the implementation does not
enforce one naming grammar or derive AAD from ORM metadata.

AAD labels are therefore versioned cryptographic identifiers, even when they
do not match physical table and column names.

### 4.4 Lookup digest

A lookup digest is an HMAC-SHA-256 hexadecimal string over:

```text
aad || 0x00 || utf8(trim(value).lower())
```

It supports exact normalized lookup and equality correlation within one AAD
namespace. It is not encryption, cannot support arbitrary contains/range
search, and deliberately reveals that equal normalized inputs in the same
namespace are equal.

## 5. Functional requirements

### FR-001 — Encrypt fields non-deterministically

`encrypt_text` accepts `str | None`. `None` remains `None`; a present string is
UTF-8 encoded and encrypted with AES-256-GCM using a fresh cryptographically
random 96-bit nonce. Re-encrypting the same value with the same key and AAD
normally produces a different ciphertext.

`encrypt_required_text` is a convenience wrapper used for non-null columns. It
does not validate domain non-emptiness; domain/schema validation owns that
rule.

### FR-002 — Decrypt only authenticated field values

`decrypt_text` requires the `v1:` prefix, strict Base64, more than 12 decoded
bytes, the correct derived key, and the exact AAD. Invalid format,
authentication failure, or invalid UTF-8 raises `CorruptedEncryptedField`.
Plaintext legacy values have no compatibility read path and are rejected.

The minimum-length check does not separately require the 16-byte GCM tag;
shorter malformed payloads still fail inside AES-GCM and become the same typed
corruption error.

### FR-003 — Encrypt JSON through the field format

`encrypt_json` serialises JSON-compatible values with sorted keys and compact
separators, then delegates to text encryption. `decrypt_json` authenticates and
decrypts first, then parses JSON. Authenticated plaintext that is not valid JSON
raises `CorruptedEncryptedField`.

Runtime JSON serialisation errors for unsupported Python objects remain normal
`TypeError` failures and are not classified as storage corruption.

### FR-004 — Derive equality lookup digests

`lookup_hash` preserves `None` and normalises every other value by trimming and
lowercasing before applying the derived HMAC key and AAD namespace.

Implemented uses include museum-question requester-email filtering and
scientific-return knowledge matching for registered inventory numbers and
observed forms. Changing normalisation, the field master key, or the AAD label
requires recomputing every affected digest.

### FR-005 — Validate configured keys

Both runtime keys are Base64 strings that must decode to exactly 32 bytes when
non-empty. Invalid Base64 or length causes Pydantic settings validation to fail.
Direct `FieldEncryptor` and `EncryptedFileStorage` construction also rejects raw
keys whose length is not exactly 32 bytes.

`APP_ENV` values `local`, `test`, and `development` may start with empty keys.
All other environment names require both keys at settings construction. An
empty database-field key still fails later when an encrypted repository/public
reader dependency constructs `FieldEncryptor`; there is no plaintext field
fallback. An empty local file key intentionally selects plaintext file storage.

### FR-006 — Encrypt complete file contents

`EncryptedFileStorage.save` encrypts the entire in-memory byte string with a
fresh nonce and the exact reference as AAD, then delegates the binary blob to
the inner storage. Reads validate the version/header and authenticate before
returning plaintext. Empty files are supported; delete delegates unchanged.

Wrong keys, another reference, modified data, plaintext/legacy blobs, unknown
versions, and truncated blobs raise `CorruptedEncryptedFile`. There is no
dual-key, dual-format, or automatic migration reader.

### FR-007 — Compose file storage from settings

`build_file_storage(data_dir, encryption_key)` always creates
`LocalDiskFileStorage`. With a non-empty file key it wraps that adapter in
`EncryptedFileStorage`; with an empty key it returns local plaintext storage.

Use of Collections, Public Submission, Museum Questions, Document Templates,
and Collection Object Index construct file storage through this builder. A
configuration change applies to all future reads/writes through those
dependencies; it does not rewrite existing blobs.

### FR-008 — Keep file references provider-neutral but non-secret

A `file_reference` is the relative logical address passed through application
ports and persisted in the database. It does not contain `DATA_DIR`, a bucket
name, cloud URI, or provider configuration. A future remote adapter must treat
the same value as its relative object name.

The reference is plaintext metadata and must not be treated as confidential.
Several producers include a sanitised original filename in it, including
proposal/public-submission attachments, journal attachments, document
templates, and collection source documents. Encrypting a separate `file_name`
column therefore does not hide that filename from database/filesystem metadata.

### FR-009 — Confine local paths

`LocalDiskFileStorage` resolves the configured base directory at construction.
For every operation it joins and resolves the supplied reference, then rejects
a destination outside the base with `FileNotFoundError`. Absolute paths outside
the base and `..` traversal are therefore rejected.

This check follows the filesystem state during resolution but does not use an
open-directory file descriptor or otherwise eliminate symlink time-of-check/
time-of-use races against a local actor able to mutate the storage tree.

### FR-010 — Write local files atomically

Save runs in an AnyIO worker thread, creates parent directories, writes a
temporary sibling with `mkstemp`, and replaces the destination using
`os.replace`. A write/replace failure removes the temporary file. Read and
delete also run in a worker thread; missing/directory reads become
`FileNotFoundError`, and delete is idempotent.

Atomic replacement prevents readers from observing a partially written
destination on the same filesystem. The adapter does not call `fsync` on the
file or directory, so it does not claim crash-durable persistence after a
reported success.

### FR-011 — Expose generic corruption responses

Global FastAPI exception handlers map:

| Exception | HTTP response |
| --- | --- |
| `CorruptedEncryptedField` | `500 {"error":"FIELD_UNREADABLE","message":"Stored field could not be read."}` |
| `CorruptedEncryptedFile` | `500 {"error":"FILE_UNREADABLE","message":"Stored file could not be read."}` |

The client receives no key, cipher, AAD, or authentication detail. Server logs
include the exception string: a field AAD label or file reference. References
that embed filenames can consequently place those names in error logs.

## 6. Implemented database-field coverage

Encryption is selected by repository mapping, not automatically applied to all
`Text` or personally identifiable columns.

| Context | Encrypted values |
| --- | --- |
| Museum Questions | Requester name/email, subject, message, answer body, out-of-scope reason, and attachment display filenames. |
| Public Submission | Citizen name/email, subject, body, pending-document display filenames, and amendment-token requester email. |
| Scientific Return | Project snapshot payload, query text, supervised-agent inputs/results, decision context, iteration observation/plan/reflection, tool queries, knowledge content/numbers/forms, full-agentic trajectory payloads, and tool invocation/results. |

Examples of sensitive or correlating values that remain plaintext include:

- Identity user names/emails and permission/institution relationships;
- proposal requester contact snapshots, conversation subject/body, notes, TODO
  text, and attachment display filenames after materialisation in Use of
  Collections;
- pending public-submission confirmation token and all plaintext file
  references;
- museum-question assignee/actor IDs, timestamps, status, content type, size,
  and file references;
- scientific-return candidate title, authors, abstract, URL/DOI, objectives,
  failure/error strings, and extensive workflow/provenance metadata; and
- document-template/catalogue metadata and source-document filenames.

Some plaintext is required for routing, indexing, workflow, or interoperability;
other coverage has simply not been selected. The repository contains no formal
data-classification inventory that justifies each decision.

## 7. Migration and compatibility behaviour

Migration `0054_db_field_encryption_p1` widens selected columns to `Text`, drops
the public-submission email index, and adds a required museum-question email
digest. It contains no data transformation or backfill.

On an installation with rows created before encryption:

- adding the non-null digest column can fail immediately;
- existing plaintext selected fields cannot be read by the encrypted
  repositories because they lack `v1:`; and
- no existing requester-email hashes are calculated.

The consolidated baseline describes fresh-start environments, which reduces
the expected upgrade path, but the migration itself is not safe for a populated
database. Downgrade similarly changes types/indexes without decrypting values,
so ciphertext remains in columns that older application code expects as
plaintext.

File compatibility is equally strict. Enabling file encryption over a directory
of plaintext blobs makes old files return `FILE_UNREADABLE`; changing the key
makes all encrypted blobs unreadable; disabling encryption causes ciphertext
bytes to be returned as if they were file content.

## 8. Invariants

| ID | Invariant |
| --- | --- |
| INV-001 | A successfully opened field/file was authenticated with the configured key and exact AAD. |
| INV-002 | Every encryption operation uses a fresh 96-bit random nonce. |
| INV-003 | Field encryption and lookup HMAC use independently derived keys. |
| INV-004 | `None` field/JSON/digest input remains `None`. |
| INV-005 | Invalid key length is rejected before cryptographic use. |
| INV-006 | An encrypted file cannot be opened through a different reference. |
| INV-007 | A resolved local reference must remain beneath `DATA_DIR`. |
| INV-008 | Local delete is idempotent and replacement is atomic on one filesystem. |
| INV-009 | Database-field repositories do not silently accept plaintext legacy values. |

“All sensitive data is encrypted at rest”, “keys can be rotated without
downtime”, and “migration 0054 upgrades a populated database safely” are not
current invariants.

## 9. Acceptance and test traceability

| Behaviour | Representative automated evidence |
| --- | --- |
| Field text round trip, confidentiality, and nonce uniqueness | `test_field_encryption.py::test_text_round_trip_returns_original_value`, `test_field_encryption.py::test_ciphertext_does_not_contain_plaintext`, `test_field_encryption.py::test_same_value_encrypts_with_distinct_nonce` |
| Field corruption and AAD mismatch | `test_field_encryption.py::test_aad_mismatch_raises_corrupted_field`, `test_field_encryption.py::test_missing_prefix_raises_corrupted_field`, `test_field_encryption.py::test_unknown_version_raises_corrupted_field`, `test_field_encryption.py::test_invalid_base64_raises_corrupted_field`, `test_field_encryption.py::test_tampered_ciphertext_raises_corrupted_field` |
| Null preservation, keyed normalization, and JSON | `test_field_encryption.py::test_none_remains_none`, `test_field_encryption.py::test_email_hash_is_normalized_and_stable`, `test_field_encryption.py::test_hash_changes_with_aad`, `test_field_encryption.py::test_json_round_trip_returns_original_value`, `test_field_encryption.py::test_json_decode_failure_raises_corrupted_field` |
| File round trip, confidentiality, nonce, empty content, and deletion | `test_file_encryption.py::test_round_trip_returns_original_content`, `test_file_encryption.py::test_saved_blob_does_not_contain_plaintext`, `test_file_encryption.py::test_same_content_saves_with_distinct_nonce`, `test_file_encryption.py::test_empty_file_round_trips`, `test_file_encryption.py::test_delete_delegates_to_inner_storage` |
| File tamper/key/reference/header failures | `test_file_encryption.py::test_ciphertext_tampering_raises_corrupted_file`, `test_file_encryption.py::test_wrong_key_raises_corrupted_file`, `test_file_encryption.py::test_aad_binds_blob_to_file_reference`, `test_file_encryption.py::test_blob_without_version_header_raises_corrupted_file`, `test_file_encryption.py::test_truncated_versioned_blob_raises_corrupted_file` |
| Local confinement and atomic replacement | `test_file_storage.py::test_round_trip_into_subfolder`, `test_file_storage.py::test_read_rejects_path_traversal`, `test_file_storage.py::test_save_is_atomic_and_leaves_no_temp_files`, `test_file_storage.py::test_delete_removes_file_and_is_idempotent` |
| Builder and context file-storage wiring | `test_file_storage.py::test_build_file_storage_returns_plain_storage_without_key`, `test_file_storage.py::test_build_file_storage_wraps_storage_when_key_is_configured`, `test_file_storage.py::test_file_storage_dependencies_use_configured_encryption_key` |
| Runtime key validation | `test_config.py::test_non_local_settings_require_file_encryption_key`, `test_config.py::test_non_local_settings_require_db_field_encryption_key`, `test_config.py::test_file_encryption_key_must_be_valid_base64_in_local`, `test_config.py::test_db_field_encryption_key_must_decode_to_32_bytes_in_local` |
| Phase-one repository field wiring | `test_database_field_encryption_phase1.py::test_context_encryptor_uses_configured_db_field_key`, `test_database_field_encryption_phase1.py::test_museum_questions_wiring_encrypts_through_context_dependencies`, `test_database_field_encryption_phase1.py::test_public_submission_repository_stores_selected_fields_encrypted`, `test_database_field_encryption_phase1.py::test_museum_question_repository_filters_by_hash_and_encrypts`, `test_database_field_encryption_phase1.py::test_amendment_token_repository_stores_requester_email_encrypted` |
| Route-level encrypted file round trip and generic error | `test_api.py::test_log_entry_attachment_uses_configured_encrypted_storage` |

Tests do not cover populated-database migration/downgrade, plaintext-to-
ciphertext file conversion, key rotation, mixed key versions, backup restore,
AAD inventory drift, filename leakage through references/logs, symlink races,
crash durability, large-file memory/latency, or systematic field-classification
coverage.

## 10. Non-functional requirements

- **Confidentiality and integrity:** AES-GCM provides authenticated encryption;
  nonce uniqueness depends on the operating-system random source.
- **Key separation:** database AES/HMAC keys are derived separately, and file
  encryption uses a distinct configured master key.
- **Availability:** losing either key permanently loses access to its protected
  data; there is no recovery key or escrow workflow in the application.
- **Memory:** field and file encryption are one-shot operations. Complete file
  bytes and ciphertext coexist in memory; there is no streaming encryption.
- **Event-loop safety:** local filesystem I/O runs in worker threads, but AES-GCM
  and field/JSON processing run synchronously in the request/worker task.
- **Metadata:** encryption preserves lengths approximately and leaves table,
  row, timestamps, relations, statuses, file references, and selected search
  digests visible.
- **Observability:** corruption is logged and returned generically, but there is
  no metric, alert, quarantine state, repair queue, or integrity sweep.
- **Portability:** application file references are storage-provider neutral;
  only a local-disk adapter currently exists.

## 11. Known gaps and recommended changes

| Priority | Finding | Recommended change |
| --- | --- | --- |
| Critical | There is no key identifier, key ring, rotation reader, or rewrite workflow; replacing a key makes every existing value unreadable. | Define envelope/key-version metadata, load current plus previous keys from a secret manager, rotate by authenticated read/re-encrypt, verify counts, and retire old keys only after tested backup/rollback. |
| Critical | Migration `0054` neither backfills the required digest nor encrypts existing plaintext, and its downgrade does not decrypt ciphertext. | Replace the upgrade assumption with an explicit expand/backfill/verify/contract migration or formally prohibit in-place upgrades and enforce an empty-database precondition. |
| High | File encryption has no migration path between plaintext, encrypted, or rotated-key blobs. | Add format/key metadata and an idempotent, resumable file rewrite tool with inventory, integrity verification, checkpoints, and rollback/backup instructions. |
| High | Filename-bearing plaintext `file_reference` values defeat the confidentiality gained by encrypting display filename columns. | Generate opaque references from IDs/extensions only; migrate existing blobs by decrypting/re-encrypting because the reference is AAD, and keep display names solely in protected metadata where required. |
| High | Sensitive-field coverage is selective and undocumented as a data-classification decision; substantial requester, conversation, research, and AI metadata remains plaintext. | Create an owned data inventory with classification, purpose, retention, search needs, protection decision, AAD/key domain, and compensating controls for every sensitive column. |
| High | AAD naming is inconsistent and the architecture document claims one physical-name grammar that code does not enforce. | Introduce a reviewed registry of stable versioned AAD constants, test uniqueness/coverage against encrypted mappings, and update `encryption-contracts.md` without deriving labels implicitly from mutable ORM names. |
| High | Keys are runtime strings with no secret-manager lifecycle, provenance, startup key identity check, or recovery test in this codebase. | Load versioned keys from the deployment secret manager, restrict access, audit retrieval, record non-secret fingerprints, and exercise restore/rotation in staging. |
| Medium | Enabling/disabling file encryption in local/development can silently change interpretation of an existing data directory. | Persist storage-format metadata or require a new/verified-empty `DATA_DIR`; refuse startup when configuration and on-disk inventory disagree. |
| Medium | Corruption logs include AAD/file references, and references may contain original filenames. | Log opaque record/reference hashes plus controlled diagnostic context; redact filename-bearing paths and add security metrics/alerts. |
| Medium | Local path confinement is vulnerable to filesystem races by an actor able to alter symlinks beneath `DATA_DIR`. | Use descriptor-relative, no-follow operations or a storage root not writable by untrusted local actors; add adversarial path tests. |
| Medium | Atomic replacement is not crash durability, and no backup/restore integrity procedure is specified. | Add file/directory `fsync` where durability is required and document/test encrypted backup restoration with key availability. |
| Medium | Whole-file encryption and JSON sealing duplicate complete plaintext/ciphertext buffers. | Enforce size limits consistently, measure peak memory/event-loop latency, and adopt an authenticated streaming/container format if larger objects are required. |
| Medium | HMAC normalization is hard-coded to `strip().lower()` for every lookup domain. | Define per-field canonicalization (for example email/domain or inventory rules), version it with the digest namespace, and test Unicode/case semantics. |
| Low | Error responses use `500` but offer no stable incident correlation identifier. | Attach a request/incident ID to logs and safe responses without exposing AAD or key details. |
| Low | `run_with_unique_retry` was previously included as an encryption requirement although it is an unrelated persistence helper. | Keep it documented with the workflows that use it (for example SPEC-010/SPEC-019) rather than expanding this cryptographic boundary. |

## 12. Traceability

| Element | Location |
| --- | --- |
| Field encryption, JSON, digest, and key derivation | `vitarerum-api/app/shared/field_encryption.py` |
| File encryption decorator | `vitarerum-api/app/shared/file_encryption.py` |
| Local storage and composition | `vitarerum-api/app/shared/file_storage.py` |
| Runtime key validation | `vitarerum-api/app/config.py` |
| Global corruption error mapping | `vitarerum-api/app/main.py` |
| Phase-one encrypted repositories | `vitarerum-api/app/museum_questions/infrastructure/repositories.py`, `app/public_submission/infrastructure/repositories.py` |
| Scientific-return encrypted repositories | `vitarerum-api/app/scientific_return/infrastructure/repositories.py`, `full_agentic_repository.py` |
| File-storage composition roots | `vitarerum-api/app/{use_of_collections,public_submission,museum_questions,document_templates,collection_object_index}/presentation/dependencies.py` |
| Database schema preparation | `vitarerum-api/alembic/versions/00000054_0054_db_field_encryption_p1.py` |
| Written cryptographic contract | `docs/architecture/encryption-contracts.md` |
| Automated tests | `vitarerum-api/test/shared/`, `vitarerum-api/test/test_database_field_encryption_phase1.py`, `vitarerum-api/test/test_config.py` |

## 13. Open product and operational decisions

1. Is in-place upgrade of a populated pre-encryption database supported, or are
   deployments contractually fresh-start only?
2. Which system owns key generation, access, versioning, escrow, rotation,
   revocation, and destruction?
3. Which database fields and metadata are classified as confidential, and what
   justifies each plaintext exception?
4. Are original filenames confidential, and may they appear in file references
   or operational logs?
5. What restoration objective applies when authentication fails or a key is
   unavailable?
6. What maximum file size and encryption latency/memory budget must future
   storage adapters support?
