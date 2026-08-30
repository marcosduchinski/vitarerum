"""The scheduled sweep opens one investigation per consulted object.

Until objects became targets of their own, one investigation covered a whole
project and the floor's guarantee reached only its first object. The fan-out is
where that is decided, and where a shared idempotency key would silently create
one investigation instead of several.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from app.scientific_return.application.full_agentic import (
    FullAgenticAlreadyRunning,
    FullAgenticConfiguration,
    StartFullAgenticInput,
)
from app.scientific_return.domain.enums import AgenticTrajectoryEventKind
from app.scientific_return.domain.full_agentic_models import (
    AgenticBudget,
    AgenticTrajectoryEvent,
    AgenticUsage,
    FullAgenticInvestigation,
    FullAgenticInvestigationId,
)
from app.scientific_return.domain.models import (
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnSnapshotId,
    ScientificReturnWatchId,
)
from app.scientific_return.presentation import commands
from app.shared.kernel import PermissionId

_NOW = datetime(2026, 8, 30, tzinfo=UTC)


class _Session:
    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _Starter:
    """Records what the sweep asked for, and can refuse a chosen object."""

    def __init__(self, refuse: set[str] | None = None) -> None:
        self.requests: list[StartFullAgenticInput] = []
        self._refuse = refuse or set()

    async def execute_scheduled(
        self, data: StartFullAgenticInput
    ) -> FullAgenticInvestigation:
        self.requests.append(data)
        if data.object_id in self._refuse:
            raise FullAgenticAlreadyRunning("already live for this object")
        return FullAgenticInvestigation(
            id=FullAgenticInvestigationId(f"investigation-{data.object_id}"),
            watch_id=data.watch_id,
            objective=data.objective,
            object_id=data.object_id,
            status=commands.FullAgenticInvestigationStatus.QUEUED,
            idempotency_key=data.idempotency_key,
            budget=AgenticBudget(4, 12, 40, 5, 20),
            usage=AgenticUsage(),
            created_by=PermissionId("scheduler"),
            created_at=_NOW,
        )


class _Repository:
    def __init__(self, objects: int) -> None:
        self.snapshot = ScientificReturnProjectSnapshot(
            id=ScientificReturnSnapshotId("snapshot-1"),
            project_id="project-1",
            payload=ProjectSnapshotPayload(
                project_id="project-1",
                project_reference="PRJ-1",
                researcher="Researcher",
                consulted_objects=tuple(
                    ConsultedObjectSnapshot(
                        f"object-{index}", f"MB06-00574{index}", f"Taxon {index}"
                    )
                    for index in range(1, objects + 1)
                ),
            ),
            payload_hash="hash",
            builder_version="v1",
            created_at=_NOW,
        )

    async def get_snapshot_for_watch(self, watch_id: Any) -> Any:
        return self.snapshot


class _AgenticRepository:
    def __init__(self) -> None:
        self.events: list[AgenticTrajectoryEvent] = []

    async def next_event_sequence(self, investigation_id: Any) -> int:
        return len(self.events) + 1

    async def append_event(self, event: AgenticTrajectoryEvent) -> None:
        self.events.append(event)


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    objects: int,
    ceiling: int,
    refuse: set[str] | None = None,
) -> tuple[_Starter, _AgenticRepository]:
    starter, agentic = _Starter(refuse), _AgenticRepository()
    monkeypatch.setattr(commands, "get_repository", lambda _s: _Repository(objects))
    monkeypatch.setattr(commands, "get_full_agentic_starter", lambda _s: starter)
    monkeypatch.setattr(
        commands, "get_full_agentic_repository", lambda _s: agentic
    )
    monkeypatch.setattr(
        commands,
        "get_full_agentic_configuration",
        lambda: FullAgenticConfiguration(
            enabled=True,
            allowed_sources=("TEST",),
            budget=AgenticBudget(4, 12, 40, 5, 20),
            max_objects=ceiling,
        ),
    )
    return starter, agentic


@pytest.mark.asyncio
async def test_one_investigation_per_object_with_a_key_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    starter, agentic = _wire(monkeypatch, objects=3, ceiling=15)

    await commands._queue_autonomous_search(
        _Session(), ScientificReturnWatchId("watch-1"), "run-1"
    )

    assert [item.object_id for item in starter.requests] == [
        "object-1",
        "object-2",
        "object-3",
    ]
    # A shared key would return the first investigation three times instead of
    # creating three, and nothing would say so.
    assert len({item.idempotency_key for item in starter.requests}) == 3
    assert all(
        item.idempotency_key.startswith("scheduled-sweep:run-1:")
        for item in starter.requests
    )
    assert agentic.events == []


@pytest.mark.asyncio
async def test_objects_beyond_the_ceiling_are_recorded_not_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    starter, agentic = _wire(monkeypatch, objects=5, ceiling=2)

    await commands._queue_autonomous_search(
        _Session(), ScientificReturnWatchId("watch-1"), "run-1"
    )

    assert [item.object_id for item in starter.requests] == ["object-1", "object-2"]
    # Every investigation of the fan-out carries the notice, so whichever one a
    # curator opens says the project was not covered in full.
    assert len(agentic.events) == 2
    for event in agentic.events:
        assert event.kind is AgenticTrajectoryEventKind.COVERAGE_TRUNCATED
        assert event.payload["coveredObjects"] == 2
        assert event.payload["consultedObjects"] == 5
        assert event.payload["uncoveredObjectIds"] == [
            "object-3",
            "object-4",
            "object-5",
        ]


@pytest.mark.asyncio
async def test_one_object_already_live_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    starter, _ = _wire(monkeypatch, objects=3, ceiling=15, refuse={"object-2"})

    await commands._queue_autonomous_search(
        _Session(), ScientificReturnWatchId("watch-1"), "run-1"
    )

    assert [item.object_id for item in starter.requests] == [
        "object-1",
        "object-2",
        "object-3",
    ]
