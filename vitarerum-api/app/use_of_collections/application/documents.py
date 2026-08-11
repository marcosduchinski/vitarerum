"""Read models for the documents generated from journal data.

These carry the values a filled-in museum form needs, in the vocabulary of the
form rather than of the aggregates: the object access log renders onto MUHNAC's
RAIS register (``formColecoesAcessoInSituRegisto``). Values stay typed here —
date formatting and blank-line padding belong to the renderer, which knows the
form's layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ObjectAccessLogDocumentObject:
    """One line of the register's object table."""

    inventory_number: str
    designation: str
    object_type: str
    number_of_objects: int
    accessed_at: datetime
    observations: str


@dataclass(frozen=True, slots=True)
class ObjectAccessLogDocument:
    """The object access log as the RAIS register presents it."""

    reference_number: str
    issued_on: date
    requester: str
    researcher_name: str
    researcher_email: str
    collection: str
    curator: str
    conclusion_date: date | None
    objects: tuple[ObjectAccessLogDocumentObject, ...]
