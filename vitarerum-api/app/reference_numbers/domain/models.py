from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import NewType

ReferencePolicyId = NewType("ReferencePolicyId", str)

MAX_SEQUENCE_WIDTH = 12
_DATE_TOKEN_RUN_PATTERN = re.compile(r"(?:YYYY|YY|MM|DD)+")
_DATE_TOKEN_PATTERN = re.compile(r"YYYY|YY|MM|DD")
_LETTER_RUN_PATTERN = re.compile(r"[A-Za-z]+")
_ALLOWED_LITERAL_PATTERN = re.compile(r"^[A-Za-z0-9/_-]+$")


class ReferenceKind(StrEnum):
    PROPOSAL = "PROPOSAL"
    COLLECTION_USE_PROJECT = "COLLECTION_USE_PROJECT"
    OBJECT_ACCESS_LOG = "OBJECT_ACCESS_LOG"
    OBJECT_OCCURRENCE_LOG = "OBJECT_OCCURRENCE_LOG"
    PUBLICATION_LOG = "PUBLICATION_LOG"


class ReferencePolicyStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    RETIRED = "RETIRED"


class SequenceScope(StrEnum):
    GLOBAL = "GLOBAL"
    YEAR = "YEAR"
    MONTH = "MONTH"
    DAY = "DAY"


class ReferencePolicyEvent(StrEnum):
    CREATED = "CREATED"
    ACTIVATED = "ACTIVATED"
    DEACTIVATED = "DEACTIVATED"
    RETIRED = "RETIRED"


class SequenceOverflow(ValueError):
    pass


class InvalidReferencePolicyTransition(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReferenceMask:
    value: str

    def __post_init__(self) -> None:
        mask = self.value.strip()
        if not mask:
            raise ValueError("Reference mask is required.")
        if not _ALLOWED_LITERAL_PATTERN.fullmatch(mask):
            raise ValueError(
                "Reference mask may contain only letters, digits, /, _ and -."
            )
        runs = list(re.finditer(r"X+", mask))
        if len(runs) != 1:
            raise ValueError(
                "Reference mask must contain exactly one sequence token run."
            )
        run = runs[0]
        if run.end() != len(mask):
            raise ValueError("Reference mask sequence token must be the final token.")
        if run.end() - run.start() > MAX_SEQUENCE_WIDTH:
            raise ValueError(
                f"Reference mask sequence width must be at most {MAX_SEQUENCE_WIDTH}."
            )
        object.__setattr__(self, "value", mask)

    @property
    def sequence_width(self) -> int:
        match = re.search(r"X+$", self.value)
        if match is None:  # pragma: no cover - guaranteed by __post_init__
            raise AssertionError("valid mask has a sequence run")
        return match.end() - match.start()

    def _prefix_segments(self) -> tuple[tuple[str, str], ...]:
        """Split the mask's non-sequence prefix into ('literal', text) /
        ('token', name) segments.

        A maximal run of letters becomes date tokens only if the *entire* run
        decomposes exactly into YYYY/YY/MM/DD with nothing left over —
        otherwise the whole run stays one literal segment. Without this, a
        naive substring search would misread the "MM" inside a literal prefix
        like "COMM" as a month token and corrupt rendering/validation.
        """
        prefix = self.value[: len(self.value) - self.sequence_width]
        segments: list[tuple[str, str]] = []
        pos = 0
        for match in _LETTER_RUN_PATTERN.finditer(prefix):
            if match.start() > pos:
                segments.append(("literal", prefix[pos : match.start()]))
            run = match.group(0)
            if _DATE_TOKEN_RUN_PATTERN.fullmatch(run):
                segments.extend(
                    ("token", token.group(0))
                    for token in _DATE_TOKEN_PATTERN.finditer(run)
                )
            else:
                segments.append(("literal", run))
            pos = match.end()
        if pos < len(prefix):
            segments.append(("literal", prefix[pos:]))
        return tuple(segments)

    @property
    def tokens(self) -> tuple[str, ...]:
        date_tokens = tuple(
            name for kind, name in self._prefix_segments() if kind == "token"
        )
        return (*date_tokens, "X" * self.sequence_width)

    @property
    def sequence_scope(self) -> SequenceScope:
        date_tokens = {
            name for kind, name in self._prefix_segments() if kind == "token"
        }
        if "DD" in date_tokens:
            return SequenceScope.DAY
        if "MM" in date_tokens:
            return SequenceScope.MONTH
        if "YYYY" in date_tokens or "YY" in date_tokens:
            return SequenceScope.YEAR
        return SequenceScope.GLOBAL

    @property
    def max_rendered_length(self) -> int:
        return len(self.render(on_date=date(9999, 12, 31), sequence=1))

    def scope_key(self, on_date: date) -> str:
        match self.sequence_scope:
            case SequenceScope.GLOBAL:
                return "GLOBAL"
            case SequenceScope.YEAR:
                return f"{on_date:%Y}"
            case SequenceScope.MONTH:
                return f"{on_date:%Y-%m}"
            case SequenceScope.DAY:
                return f"{on_date:%Y-%m-%d}"

    def render(self, *, on_date: date, sequence: int) -> str:
        if sequence < 1:
            raise ValueError("Reference sequence must be positive.")
        max_value = 10**self.sequence_width - 1
        if sequence > max_value:
            raise SequenceOverflow(
                f"Reference sequence {sequence} exceeds width {self.sequence_width}."
            )
        date_values = {
            "YYYY": f"{on_date:%Y}",
            "YY": f"{on_date:%y}",
            "MM": f"{on_date:%m}",
            "DD": f"{on_date:%d}",
        }
        parts = [
            date_values[name] if kind == "token" else name
            for kind, name in self._prefix_segments()
        ]
        parts.append(f"{sequence:0{self.sequence_width}d}")
        return "".join(parts)

    def to_regex(self) -> re.Pattern[str]:
        date_patterns = {
            "YYYY": r"\d{4}",
            "YY": r"\d{2}",
            "MM": r"\d{2}",
            "DD": r"\d{2}",
        }
        parts = [
            date_patterns[name] if kind == "token" else re.escape(name)
            for kind, name in self._prefix_segments()
        ]
        parts.append(rf"\d{{{self.sequence_width}}}")
        return re.compile("^" + "".join(parts) + "$")


@dataclass(frozen=True, slots=True)
class ReferencePolicy:
    id: ReferencePolicyId
    kind: ReferenceKind
    mask: ReferenceMask
    status: ReferencePolicyStatus
    active_from: datetime | None
    active_until: datetime | None
    created_by: str
    created_at: datetime
    updated_by: str | None = None
    updated_at: datetime | None = None
    activated_by: str | None = None
    activated_at: datetime | None = None

    @classmethod
    def create_draft(
        cls,
        *,
        kind: ReferenceKind,
        mask: ReferenceMask,
        created_by: str,
        now: datetime | None = None,
    ) -> ReferencePolicy:
        timestamp = now or datetime.now(UTC)
        return cls(
            id=ReferencePolicyId(str(uuid.uuid4())),
            kind=kind,
            mask=mask,
            status=ReferencePolicyStatus.DRAFT,
            active_from=None,
            active_until=None,
            created_by=created_by,
            created_at=timestamp,
        )

    @property
    def sequence_scope(self) -> SequenceScope:
        return self.mask.sequence_scope

    def activate(
        self, *, actor_id: str, now: datetime | None = None
    ) -> ReferencePolicy:
        if self.status not in (
            ReferencePolicyStatus.DRAFT,
            ReferencePolicyStatus.INACTIVE,
        ):
            raise InvalidReferencePolicyTransition(
                f"Cannot activate a policy with status {self.status.value}."
            )
        timestamp = now or datetime.now(UTC)
        return ReferencePolicy(
            id=self.id,
            kind=self.kind,
            mask=self.mask,
            status=ReferencePolicyStatus.ACTIVE,
            active_from=timestamp,
            active_until=None,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_by=actor_id,
            updated_at=timestamp,
            activated_by=actor_id,
            activated_at=timestamp,
        )

    def deactivate(
        self, *, actor_id: str, now: datetime | None = None
    ) -> ReferencePolicy:
        if self.status is not ReferencePolicyStatus.ACTIVE:
            raise InvalidReferencePolicyTransition(
                f"Cannot deactivate a policy with status {self.status.value}."
            )
        timestamp = now or datetime.now(UTC)
        return ReferencePolicy(
            id=self.id,
            kind=self.kind,
            mask=self.mask,
            status=ReferencePolicyStatus.INACTIVE,
            active_from=self.active_from,
            active_until=timestamp,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_by=actor_id,
            updated_at=timestamp,
            activated_by=self.activated_by,
            activated_at=self.activated_at,
        )

    def matches(self, value: str) -> bool:
        return self.mask.to_regex().fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class LegacyReferenceFormat:
    kind: ReferenceKind
    name: str
    pattern: str

    def matches(self, value: str) -> bool:
        return re.fullmatch(self.pattern, value) is not None
