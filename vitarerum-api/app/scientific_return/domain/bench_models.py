"""Pure domain model for the local-corpus scientific-return test bench."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class TestSourceKind(StrEnum):
    TEXT_DOCUMENT = "TEXT_DOCUMENT"
    BIBLIOGRAPHIC_REFERENCE = "BIBLIOGRAPHIC_REFERENCE"


class TestSourceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class TestBatchStatus(StrEnum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def terminal(self) -> bool:
        return self in {
            self.COMPLETED,
            self.COMPLETED_WITH_ERRORS,
            self.FAILED,
            self.CANCELLED,
        }


class TestItemStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class TestAttemptStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class TestInventoryEvidenceStatus(StrEnum):
    VERIFIED = "VERIFIED"
    NOT_OBSERVED = "NOT_OBSERVED"
    UNAVAILABLE = "UNAVAILABLE"


class BenchRuleViolation(ValueError):
    pass


def required_text(value: str, field: str, maximum: int) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise BenchRuleViolation(f"{field} is required")
    if len(normalized) > maximum:
        raise BenchRuleViolation(f"{field} exceeds {maximum} characters")
    return normalized


@dataclass(frozen=True, slots=True)
class TestSubject:
    author: str
    object_name: str
    inventory_number: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "author", required_text(self.author, "author", 500))
        object.__setattr__(
            self, "object_name", required_text(self.object_name, "objectName", 500)
        )
        object.__setattr__(
            self,
            "inventory_number",
            required_text(self.inventory_number, "inventoryNumber", 255),
        )


@dataclass(frozen=True, slots=True)
class NormalizedScore:
    value: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.value <= Decimal("1"):
            raise BenchRuleViolation("score must be between zero and one")


def derive_batch_status(
    item_statuses: list[TestItemStatus], *, cancellation_requested: bool = False
) -> TestBatchStatus:
    if cancellation_requested:
        return (
            TestBatchStatus.CANCELLING
            if TestItemStatus.RUNNING in item_statuses
            else TestBatchStatus.CANCELLED
        )
    if not item_statuses:
        return TestBatchStatus.FAILED
    if TestItemStatus.RUNNING in item_statuses:
        return TestBatchStatus.RUNNING
    if TestItemStatus.PENDING in item_statuses:
        return TestBatchStatus.QUEUED
    completed = item_statuses.count(TestItemStatus.COMPLETED)
    errors = item_statuses.count(TestItemStatus.ERROR)
    if completed == len(item_statuses):
        return TestBatchStatus.COMPLETED
    if errors == len(item_statuses):
        return TestBatchStatus.FAILED
    if completed and errors:
        return TestBatchStatus.COMPLETED_WITH_ERRORS
    return TestBatchStatus.CANCELLED
