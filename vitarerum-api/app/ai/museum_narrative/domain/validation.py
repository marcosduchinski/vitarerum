"""Deterministic validation of generated narratives against canonical facts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum

from app.ai.museum_narrative.domain.facts import (
    ApprovalFact,
    CanonicalVisitFacts,
    ExecutionFact,
)


class NarrativeFindingCode(StrEnum):
    INVENTED_DATE = "invented_date"
    PLANNED_DATE_AS_EXECUTED = "planned_date_as_executed"
    INVENTED_PERSON = "invented_person"
    INVENTED_OBJECT = "invented_object"
    INVENTED_PLACE = "invented_place"


@dataclass(frozen=True, slots=True)
class NarrativeFinding:
    code: NarrativeFindingCode
    message: str
    evidence: str


@dataclass(frozen=True, slots=True)
class NarrativeValidationResult:
    conforms: bool
    findings: list[NarrativeFinding] = field(default_factory=list)


_ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_EU_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
_PERSON_MENTION = re.compile(
    r"\b(?:Dr\.?|Dra\.?|Prof\.?|Professor|Curator|Researcher)\s+"
    r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç'-]+"
    r"(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç'-]+){0,3})"
)
_OBJECT_MENTION = re.compile(r"\b(?:INV|RO|OBJ|XL)-[A-Za-z0-9._/-]+\b")
_PLACE_MENTION = re.compile(
    r"\b(?:Gallery|Galeria|Room|Sala|Lab|Laboratory|Laboratório|Reserve|Reserva)\s+"
    r"[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç'-]*"
)
_EXECUTION_WORDS = (
    "executed",
    "execution",
    "occurred",
    "took place",
    "carried out",
    "realizada",
    "realizado",
    "realizou",
    "ocorreu",
    "aconteceu",
    "efetuada",
    "efetuado",
)


def _date_value(value: date | datetime | None) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value


def _date_range(start: date | None, end: date | None) -> set[date]:
    if start is None:
        return set()
    if end is None or end < start:
        return {start}
    days = (end - start).days
    return {start + timedelta(days=offset) for offset in range(days + 1)}


def _allowed_dates(facts: CanonicalVisitFacts) -> set[date]:
    allowed = _date_range(facts.planned_begin_date, facts.planned_end_date)
    values: list[date | None] = []
    if isinstance(facts.execution, ExecutionFact):
        values.append(_date_value(facts.execution.occurred_at))
    values.extend(_date_value(log.added_at) for log in facts.access_logs)
    values.extend(_date_value(log.conclusion_at) for log in facts.access_logs)
    values.extend(_date_value(occ.occurrence_date) for occ in facts.occurrences)
    values.extend(_date_value(occ.conclusion_at) for occ in facts.occurrences)
    values.extend(_date_value(pub.added_at) for pub in facts.publications)
    allowed.update(value for value in values if value is not None)
    return allowed


def _allowed_people(facts: CanonicalVisitFacts) -> set[str]:
    values: list[str | None] = [facts.requester.name]
    if isinstance(facts.approval, ApprovalFact):
        values.append(facts.approval.approved_by)
    if isinstance(facts.execution, ExecutionFact):
        values.append(facts.execution.recorded_by)
    values.extend(log.added_by for log in facts.access_logs)
    values.extend(log.curator for log in facts.access_logs)
    values.extend(occ.reported_by for occ in facts.occurrences)
    values.extend(occ.curator for occ in facts.occurrences)
    values.extend(pub.added_by for pub in facts.publications)
    return {value.lower() for value in values if value}


def _allowed_objects(facts: CanonicalVisitFacts) -> set[str]:
    values: list[str | None] = []
    for obj in facts.objects:
        values.extend([obj.source_id, obj.label])
    values.extend(log.related_object_source_id for log in facts.access_logs)
    values.extend(occ.related_object_source_id for occ in facts.occurrences)
    values.extend(pub.related_object_source_id for pub in facts.publications)
    return {value.lower() for value in values if value}


def _allowed_places(facts: CanonicalVisitFacts) -> set[str]:
    return {
        occurrence.location.lower()
        for occurrence in facts.occurrences
        if occurrence.location
    }


def _candidate_text(text: str, pattern: re.Pattern[str]) -> list[str]:
    values: list[str] = []
    for match in pattern.finditer(text):
        if match.groups():
            values.append(match.group(1).strip())
        else:
            values.append(match.group(0).strip())
    return values


def _mentioned_dates(text: str) -> list[tuple[date, str]]:
    dates: list[tuple[date, str]] = []
    for match in _ISO_DATE.finditer(text):
        try:
            dates.append((date.fromisoformat(match.group(1)), match.group(0)))
        except ValueError:
            continue
    for match in _EU_DATE.finditer(text):
        try:
            dates.append(
                (
                    date(int(match.group(3)), int(match.group(2)), int(match.group(1))),
                    match.group(0),
                )
            )
        except ValueError:
            continue
    return dates


def _mentions_execution_near(text: str, raw_date: str) -> bool:
    lowered = text.lower()
    date_index = lowered.find(raw_date.lower())
    if date_index < 0:
        return False
    window = lowered[max(0, date_index - 80) : date_index + len(raw_date) + 80]
    return any(word in window for word in _EXECUTION_WORDS)


def validate_generated_narrative(
    text: str, facts: CanonicalVisitFacts
) -> NarrativeValidationResult:
    findings: list[NarrativeFinding] = []
    allowed_dates = _allowed_dates(facts)
    mentioned_dates = _mentioned_dates(text)
    for mentioned, raw in mentioned_dates:
        if mentioned not in allowed_dates:
            findings.append(
                NarrativeFinding(
                    code=NarrativeFindingCode.INVENTED_DATE,
                    message="Narrative mentions a date absent from canonical facts.",
                    evidence=raw,
                )
            )

    execution_date = (
        _date_value(facts.execution.occurred_at)
        if isinstance(facts.execution, ExecutionFact)
        else None
    )
    planned_dates = {
        value
        for value in (facts.planned_begin_date, facts.planned_end_date)
        if value is not None
    }
    for mentioned, raw in mentioned_dates:
        if mentioned in planned_dates and mentioned != execution_date:
            if execution_date is None or _mentions_execution_near(text, raw):
                findings.append(
                    NarrativeFinding(
                        code=NarrativeFindingCode.PLANNED_DATE_AS_EXECUTED,
                        message=(
                            "Narrative treats a planned project date as factual "
                            "execution evidence."
                        ),
                        evidence=raw,
                    )
                )

    allowed_people = _allowed_people(facts)
    for raw in _candidate_text(text, _PERSON_MENTION):
        if raw.lower() not in allowed_people:
            findings.append(
                NarrativeFinding(
                    code=NarrativeFindingCode.INVENTED_PERSON,
                    message="Narrative mentions a person absent from canonical facts.",
                    evidence=raw,
                )
            )

    allowed_objects = _allowed_objects(facts)
    for raw in _candidate_text(text, _OBJECT_MENTION):
        if raw.lower() not in allowed_objects:
            findings.append(
                NarrativeFinding(
                    code=NarrativeFindingCode.INVENTED_OBJECT,
                    message=(
                        "Narrative mentions an object or inventory identifier absent "
                        "from canonical facts."
                    ),
                    evidence=raw,
                )
            )

    allowed_places = _allowed_places(facts)
    for raw in _candidate_text(text, _PLACE_MENTION):
        if raw.lower() not in allowed_places:
            findings.append(
                NarrativeFinding(
                    code=NarrativeFindingCode.INVENTED_PLACE,
                    message="Narrative mentions a place absent from canonical facts.",
                    evidence=raw,
                )
            )
    return NarrativeValidationResult(conforms=not findings, findings=findings)
