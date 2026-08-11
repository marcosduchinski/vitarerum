"""Read models for the documents generated from journal data.

These carry the values a filled-in museum form needs, in the vocabulary of the
form rather than of the aggregates:

- the object access log renders onto MUHNAC's RAIS register
  (``formColecoesAcessoInSituRegisto``), one register per project;
- an object occurrence entry renders onto the ROC report
  (``formOcorrenciaColecoes``), one report per occurrence — the form has a
  single date, place and description, so it cannot hold a whole log.

Values stay typed here — date formatting, blank-line padding and the joining of
list fields belong to the renderers, which know the forms' layouts.
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


@dataclass(frozen=True, slots=True)
class ObjectOccurrenceDocumentImage:
    """One file attached to the occurrence, named on the report's Imagens row."""

    file_name: str
    description: str


@dataclass(frozen=True, slots=True)
class ObjectOccurrenceDocumentEntry:
    """One incident block of the report, naming the object it concerns."""

    collection: str
    designation: str
    inventory_number: str
    number_of_objects: int
    occurred_at: datetime
    location: str
    detailed_description: str
    testimonial: str
    images: tuple[ObjectOccurrenceDocumentImage, ...]
    reported_by: str


@dataclass(frozen=True, slots=True)
class ObjectOccurrenceDocument:
    """A project's whole occurrence log as the ROC report presents it.

    Each block identifies its own collection and object, which is what lets one
    document carry every occurrence. Ordered oldest first, as a log reads.
    """

    reference_number: str
    issued_on: date
    institution: str
    occurrences: tuple[ObjectOccurrenceDocumentEntry, ...]
