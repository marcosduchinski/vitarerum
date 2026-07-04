"""Enumerations for the Collection Object Index context."""

from __future__ import annotations

from enum import StrEnum


class SourceKind(StrEnum):
    """Where a source document came from. UPLOAD is the only MVP kind; remote
    sources (SharePoint, Google Drive) plug in as new kinds behind the same
    ports without touching parser/index/use cases."""

    UPLOAD = "UPLOAD"


class SourceDocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    INDEXED = "INDEXED"
    ERROR = "ERROR"
