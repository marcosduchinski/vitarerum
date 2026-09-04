---
status: current
---

# Encryption Contracts

Encryption in this application authenticates certain identifier strings as
associated data. Those strings stop being free-form implementation details and
become part of the cryptographic contract: change one, and existing values no
longer decrypt.

This document records those strings and the rules that keep them stable.

## File Storage References

`file_reference` is the durable storage address recorded by the application for
uploaded files. It is a stable relative path, not an absolute path, URL, bucket
object URI, or provider-specific identifier.

The bucket, volume, base directory, or remote-storage container name belongs in
runtime configuration. It must not be embedded in `file_reference`.

This contract matters because encrypted file blobs authenticate `file_reference`
as AES-GCM associated data. A blob written for one reference cannot be moved to
another reference and still decrypt. Changing an existing reference format,
renaming stored objects, adding provider prefixes, or normalizing paths
differently requires decrypting and re-encrypting the affected archive under the
new exact references recorded in the database.

Future storage adapters, including `GcsFileStorage`, must preserve the
application-level `file_reference` as the relative object name accepted by the
file-storage port. Provider selection and bucket naming stay outside that value.

## Encrypted Database Field AAD

Encrypted database fields authenticate their logical field name as AES-GCM
associated data:

```text
<table_name>.<column_name>
```

For example:

```text
museum_questions.requester_email
```

This means table and column names become part of the cryptographic contract for
encrypted fields. Renaming an encrypted table or encrypted column is not a pure
schema refactor: values written under the old associated data will not decrypt
under the new associated data.

Any migration that renames an encrypted table or encrypted column must either:

- decrypt and re-encrypt the affected values under the new exact
  `<table_name>.<column_name>` string; or
- keep a versioned read path that accepts the previous associated-data string
  until a controlled rewrite has completed.

Do not normalize, alias, or derive associated-data strings dynamically. The exact
literal table and column names used by the ORM mapping are the contract.
