# File Storage References

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
