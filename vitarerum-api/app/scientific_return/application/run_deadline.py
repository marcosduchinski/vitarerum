"""How long one worker process may keep working.

The platform kills the job on its own clock — Cloud Run gives it thirty
minutes — and a killed process is precisely what turns a slow investigation
into an unaccounted retry. So the worker stops earlier, on a clock it owns,
and hands the work back intact.

The budget belongs to the *process*, not to an investigation: one pass drains
several investigations after running the deterministic sweep, so a per
investigation budget would multiply by the queue length and protect nothing.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class RunDeadline:
    def __init__(
        self,
        total_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if total_seconds <= 0:
            raise ValueError("A run deadline must be positive")
        self._monotonic = monotonic
        self._total = total_seconds
        self._expires_at = monotonic() + total_seconds

    @property
    def total_seconds(self) -> float:
        return self._total

    def remaining(self) -> float:
        return self._expires_at - self._monotonic()

    def allows(self, seconds: float) -> bool:
        """Whether an operation of this worst-case duration still fits."""
        return self.remaining() >= seconds
