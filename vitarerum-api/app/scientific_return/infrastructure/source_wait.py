"""Bounded waiting for external bibliographic sources.

Three sources implement the same retry shape, and each of them used to accept
whatever ``Retry-After`` the server stated. A single hostile or misconfigured
header could therefore park a worker for hours inside one attempt, outliving
the investigation lease and the platform's own job window without ever raising
anything the loop could react to.

The rule here is deliberately not "wait less". Sleeping for less than the
source asked would breach its stated rate limit and risks losing access, so an
excessive delay abandons the attempt instead. The agentic loop already treats a
failed query as an ordinary outcome, records it, and moves on.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from app.scientific_return.application.ports import (
    SourceDeadlineExceeded,
    SourceRetryDelayExceeded,
)


class SourceDeadline:
    """One source call's total budget: waits, retries and HTTP together."""

    def __init__(self, source: str, total_seconds: float) -> None:
        self._source = source
        self._total = max(0.0, total_seconds)
        self._expires_at = time.monotonic() + self._total

    @property
    def source(self) -> str:
        return self._source

    def remaining(self) -> float:
        return self._expires_at - time.monotonic()

    def ensure(self, seconds: float = 0.0) -> None:
        """Fail now rather than start work that cannot finish inside the budget."""
        if self.remaining() < seconds:
            raise SourceDeadlineExceeded(
                f"{self._source} exceeded its {self._total:.0f}s call budget"
            )


@dataclass(frozen=True, slots=True)
class SourceWaitBudget:
    """How long one source may be waited for, per delay and in total."""

    max_retry_after_seconds: float
    total_timeout_seconds: float

    def __post_init__(self) -> None:
        if self.max_retry_after_seconds < 0:
            raise ValueError("max_retry_after_seconds cannot be negative")
        if self.total_timeout_seconds <= 0:
            raise ValueError("total_timeout_seconds must be positive")

    def start(self, source: str) -> SourceDeadline:
        return SourceDeadline(source, self.total_timeout_seconds)

    def retry_delay(
        self,
        *,
        source: str,
        retry_after_header: str,
        attempt: int,
        base_seconds: float,
    ) -> float:
        """The delay to honour before the next attempt, or refuse to wait at all.

        Both header forms are read — delay-seconds and HTTP-date — because the
        three sources differ in which they send, and a value that cannot be
        parsed falls back to exponential backoff rather than to zero.
        """
        delay = _parse_retry_after(retry_after_header)
        if delay is None:
            delay = base_seconds * float(2**attempt)
        delay = max(0.0, delay)
        if delay > self.max_retry_after_seconds:
            raise SourceRetryDelayExceeded(
                f"{source} asked for a {delay:.0f}s wait, above the "
                f"{self.max_retry_after_seconds:.0f}s ceiling"
            )
        return delay


def _parse_retry_after(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at is None:
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(tz=UTC)).total_seconds())
