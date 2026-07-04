"""Shared Kernel — exactly the PUML "Shared Kernel" package plus the
cross-context identifier types those value objects and contexts share.

This module may import only the standard library (enforced by import-linter).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

PermissionId = NewType("PermissionId", str)
DocumentId = NewType("DocumentId", str)

REFERENCE_NUMBER_PATTERN = re.compile(
    r"^(?:CUP-[A-Z0-9]{8}|VRP-\d{8}-\d{4}|OAL-[A-Z0-9]{8}"
    r"|OOL-[A-Z0-9]{8}|PUB-[A-Z0-9]{8})$"
)
EMAIL_ADDRESS_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# The document type is free-form text (no fixed catalogue). The bound mirrors the
# String(128) column it is persisted into, so an over-long value is rejected at
# the edge with a 422 rather than surfacing as a database error.
MAX_DOCUMENT_TYPE_LENGTH = 128


@dataclass(frozen=True, slots=True)
class ReferenceNumber:
    value: str

    def __post_init__(self) -> None:
        if REFERENCE_NUMBER_PATTERN.fullmatch(self.value) is None:
            raise ValueError(
                "Reference number must match CUP-XXXXXXXX, VRP-YYYYMMDD-XXXX, "
                "OAL-XXXXXXXX, OOL-XXXXXXXX or PUB-XXXXXXXX."
            )


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str

    def __post_init__(self) -> None:
        if EMAIL_ADDRESS_PATTERN.fullmatch(self.value) is None:
            raise ValueError("Invalid email address.")


@dataclass(frozen=True, slots=True)
class DocumentType:
    """Free-form document type. Normalised to a trimmed, non-empty string of at
    most MAX_DOCUMENT_TYPE_LENGTH characters. Kept as a value object (not an enum)
    so staff and citizens can name documents in their own words."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized:
            raise ValueError("Document type is required.")
        if len(normalized) > MAX_DOCUMENT_TYPE_LENGTH:
            raise ValueError(
                f"Document type must be at most {MAX_DOCUMENT_TYPE_LENGTH} characters."
            )
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class MessageAttachment:
    document_id: DocumentId
    file_name: str


class UseType(StrEnum):
    """The collection-use taxonomy shared by Proposal and CollectionUseProject.
    Promoted to the Shared Kernel so any context can speak it without crossing a
    bounded-context boundary."""

    EXHIBITION = "EXHIBITION"
    IN_SITU_VISIT = "IN_SITU_VISIT"
    OTHER = "OTHER"
