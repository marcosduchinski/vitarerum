"""Shared upload/download helpers reused across presentation adapters.

Framework-coupled (FastAPI) helpers for reading capped uploads, validating that
an upload is a real DOCX (OOXML), and guessing a download Content-Type. Kept in
``shared`` so multiple bounded contexts can reuse them without importing each
other's presentation layer.
"""

from __future__ import annotations

import io
import mimetypes
import os
import re
import zipfile
from urllib.parse import quote

from fastapi import HTTPException, UploadFile, status

from app.config import settings

_UPLOAD_CHUNK = 1024 * 1024
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def safe_basename(name: str, *, default: str = "file") -> str:
    """Reduce an untrusted upload name to a safe file *basename*.

    Strips any directory components (``/`` or ``\\``), control characters and
    leading/trailing dots/spaces so the result can never traverse directories or
    resolve to ``.``/``..``. Falls back to ``default`` when nothing usable is
    left."""
    base = os.path.basename(name.replace("\\", "/"))
    base = _CONTROL_CHARS.sub("", base).strip().strip(".").strip()
    if not base or base in {".", ".."} or "/" in base:
        return default
    return base


def content_disposition_attachment(filename: str, *, default: str = "file") -> str:
    """Build a safe ``Content-Disposition`` attachment header value.

    Sanitizes to a basename first, then emits both an ASCII ``filename`` (with
    quotes stripped so the header can't be broken out of) and an RFC 5987
    ``filename*`` for full-fidelity Unicode names."""
    safe = safe_basename(filename, default=default)
    ascii_fallback = safe.encode("ascii", "replace").decode("ascii").replace('"', "")
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(safe)}"


async def read_upload_capped(file: UploadFile) -> bytes:
    """Read an upload in chunks, rejecting anything over ``max_upload_bytes``
    (413) before the whole body is buffered."""
    limit = settings.max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "error": "FILE_TOO_LARGE",
                    "message": f"File exceeds the {limit}-byte limit",
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


def ensure_docx(content: bytes) -> None:
    """Reject anything that is not a real DOCX — a ZIP carrying the OOXML
    ``[Content_Types].xml`` part — rather than trusting the file extension."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        names = set()
    if "[Content_Types].xml" not in names:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "error": "INVALID_FILE_FORMAT",
                "message": "Only valid .docx files are accepted",
            },
        )


def guess_content_type(file_name: str) -> str:
    """Best-effort MIME type for a download, from the file name's extension.

    Falls back to a generic binary type when the extension is unknown."""
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or "application/octet-stream"
