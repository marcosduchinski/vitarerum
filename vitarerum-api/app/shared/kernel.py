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
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("Document type is required.")


@dataclass(frozen=True, slots=True)
class ObjectReference:
    """Shared Kernel snapshot of a collection object identified by inventory number."""

    inventory_number: str
    display_title: str | None = None
    object_name: str | None = None
    brief_description_snapshot: str | None = None

    def __post_init__(self) -> None:
        if not self.inventory_number:
            raise ValueError("inventoryNumber is required.")


@dataclass(frozen=True, slots=True)
class MessageAttachment:
    document_id: DocumentId
    file_name: str


class UseType(StrEnum):
    """The collection-use taxonomy shared by Proposal, CollectionUseProject and
    the ProposalChat triage suggestion. Promoted to the Shared Kernel so any
    context can speak it without crossing a bounded-context boundary."""

    EXHIBITION = "EXHIBITION"
    IN_SITU_VISIT = "IN_SITU_VISIT"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class IntendedUse:
    """How the collection is intended to be used: a categorised use type plus a
    free-text description. Shared by Proposal and CollectionUseProject."""

    use_type: UseType
    description: str = ""
