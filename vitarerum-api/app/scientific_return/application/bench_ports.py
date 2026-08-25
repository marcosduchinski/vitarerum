"""Ports and application read models for the scientific-return test bench."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class BenchItemDispatcher(Protocol):
    async def dispatch(self, item_ids: Sequence[str]) -> None: ...
