"""Run the autonomous cycle over a sample set and record what it did.

The cycle reads a *snapshot* of the project, frozen when its watch was created,
never the live tables. So a bench cannot simply rewrite
``collection_use_objects`` and re-run: it has to rebuild the snapshot and point
the watch at the new one. That is the whole trick, and the reason a plain SQL
update appears to do nothing.

One project is reused for every sample, because a watch is unique per project
and deleting one would take its candidates, runs and investigations with it.
The project's object row and its requester's name are rewritten between samples
and restored at the end unless ``--keep`` is given.

The executor is driven directly rather than through the queue: a killed pass
would otherwise wait for a 15-minute lease to go cold before anything could
resume it.

    uv run python scripts/bench_full_agentic.py \
        --project cf57cc1c-b240-4516-9655-52b6472d228a \
        --samples scripts/bench_samples.example.csv \
        --out bench-results.json

Prerequisites: PostgreSQL up and migrated, a reachable model, and
``SCIENTIFIC_RETURN_FULL_AGENTIC_ENABLED=true``. ``scripts/bench.sh`` checks all
three before calling this.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

import app.orm_registry  # noqa: E402, F401  (registers every mapper)
from app.database import async_session_factory  # noqa: E402
from app.identity.public import Actor, GroupName  # noqa: E402
from app.scientific_return.application.full_agentic import (  # noqa: E402
    ExecuteFullAgenticInput,
    StartFullAgenticInput,
)
from app.scientific_return.application.run_deadline import RunDeadline  # noqa: E402
from app.scientific_return.application.use_cases import (  # noqa: E402
    ActivateScientificReturnWatch,
    ActivateWatchInput,
)
from app.scientific_return.domain.enums import InvestigationObjective  # noqa: E402
from app.scientific_return.domain.models import (  # noqa: E402
    ScientificReturnProjectSnapshot,
    ScientificReturnSnapshotId,
    ScientificReturnWatchId,
)
from app.scientific_return.presentation.dependencies import (  # noqa: E402
    build_full_agentic_executor,
    get_full_agentic_repository,
    get_full_agentic_starter,
    get_project_provider,
    get_repository,
)
from app.shared.kernel import PermissionId  # noqa: E402

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
BENCH = Actor(
    id=PermissionId("system-full-agentic-bench"),
    group=GroupName.CURATORIAL,
    email="",
)


@dataclass(frozen=True, slots=True)
class Sample:
    reference_number: str
    scientific_name: str
    author: str
    expected_doi: str | None


@dataclass(frozen=True, slots=True)
class Target:
    """The rows a sample is written into, resolved from the project itself."""

    project_id: str
    object_id: str
    user_id: str
    original_object_name: str
    original_inventory_number: str
    original_user_name: str


def read_samples(path: Path) -> list[Sample]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"reference_number", "scientific_name", "author"}
    if not rows or not required.issubset(rows[0]):
        raise SystemExit(f"{path} must have columns: {', '.join(sorted(required))}")
    return [
        Sample(
            reference_number=row["reference_number"].strip(),
            scientific_name=row["scientific_name"].strip(),
            author=row["author"].strip(),
            expected_doi=(row.get("expected_doi") or "").strip() or None,
        )
        for row in rows
        if row.get("reference_number", "").strip()
    ]


async def resolve_target(project_id: str, object_id: str | None) -> Target:
    """Find the object and the requester behind the project, and keep the originals."""
    async with async_session_factory() as session:
        project = (
            (
                await session.execute(
                    text(
                        "SELECT status, requested_by FROM collection_use_projects "
                        "WHERE id = :p"
                    ),
                    {"p": project_id},
                )
            )
            .mappings()
            .first()
        )
        if project is None:
            raise SystemExit(f"project {project_id} not found")
        if project["status"] != "COMPLETED":
            raise SystemExit(
                f"project {project_id} is {project['status']}; a watch can only be "
                "created for a completed project"
            )
        objects = (
            (
                await session.execute(
                    text(
                        "SELECT id, object_name, inventory_number "
                        "FROM collection_use_objects WHERE project_id = :p ORDER BY id"
                    ),
                    {"p": project_id},
                )
            )
            .mappings()
            .all()
        )
        if not objects:
            raise SystemExit(f"project {project_id} has no consulted objects")
        if len(objects) > 1 and object_id is None:
            listed = ", ".join(row["id"] for row in objects)
            raise SystemExit(
                f"project {project_id} has {len(objects)} objects; choose one with "
                f"--object ({listed})"
            )
        chosen = next(
            (row for row in objects if object_id is None or row["id"] == object_id),
            None,
        )
        if chosen is None:
            raise SystemExit(f"object {object_id} does not belong to {project_id}")
        requester = (
            (
                await session.execute(
                    text(
                        "SELECT u.id, u.name FROM identity_permissions p "
                        "JOIN identity_users u ON u.id = p.user_id WHERE p.id = :i"
                    ),
                    {"i": project["requested_by"]},
                )
            )
            .mappings()
            .first()
        )
        if requester is None:
            raise SystemExit(
                f"the requester permission {project['requested_by']} has no user; "
                "the snapshot takes the researcher name from it"
            )
        return Target(
            project_id=project_id,
            object_id=chosen["id"],
            user_id=requester["id"],
            original_object_name=chosen["object_name"] or "",
            original_inventory_number=chosen["inventory_number"] or "",
            original_user_name=requester["name"] or "",
        )


async def write_rows(target: Target, name: str, reference: str, author: str) -> None:
    async with async_session_factory() as session:
        await session.execute(
            text("UPDATE identity_users SET name = :n WHERE id = :i"),
            {"n": author, "i": target.user_id},
        )
        await session.execute(
            text(
                "UPDATE collection_use_objects "
                "SET object_name = :n, inventory_number = :r WHERE id = :i"
            ),
            {"n": name, "r": reference, "i": target.object_id},
        )
        await session.commit()


async def refresh_snapshot(target: Target) -> tuple[str, dict[str, str]]:
    """Rebuild the snapshot from the rows just written and point the watch at it.

    Creates the watch on the first sample. Later samples repoint the existing
    one: deleting a watch would delete the candidates, runs and investigations
    that hang off it, which is the measurement itself.
    """
    async with async_session_factory() as session:
        repository = get_repository(session)
        watch = await repository.get_watch_by_project(target.project_id)
        if watch is None:
            watch = await ActivateScientificReturnWatch(
                repository, get_project_provider(session)
            ).execute(
                ActivateWatchInput(
                    project_id=target.project_id,
                    review_interval_days=90,
                    start_immediately=True,
                    caller=BENCH,
                )
            )
            await session.commit()
        else:
            assessment = await get_project_provider(session).assess_completed_project(
                target.project_id
            )
            if assessment.payload is None:
                raise SystemExit(
                    f"project is no longer eligible: {assessment.ineligibility_reason}"
                )
            snapshot = ScientificReturnProjectSnapshot(
                id=ScientificReturnSnapshotId(str(uuid4())),
                project_id=target.project_id,
                payload=assessment.payload,
                payload_hash=str(uuid4()),
                builder_version="bench",
                created_at=datetime.now(tz=UTC),
            )
            await repository.add_snapshot(snapshot)
            await session.execute(
                text(
                    "UPDATE scientific_return_watches SET project_snapshot_id = :s "
                    "WHERE id = :w"
                ),
                {"s": str(snapshot.id), "w": str(watch.id)},
            )
            await session.commit()
        stored = await repository.get_snapshot_for_watch(watch.id)
        assert stored is not None
        obj = stored.payload.consulted_objects[0]
        return str(watch.id), {
            "researcher": stored.payload.researcher,
            "objectName": obj.object_name,
            "inventoryNumber": obj.inventory_number,
        }


async def run_investigation(
    watch_id: str, reference: str, deadline_seconds: float, passes: int
) -> dict[str, object]:
    async with async_session_factory() as session:
        investigation = await get_full_agentic_starter(session).execute_scheduled(
            StartFullAgenticInput(
                watch_id=ScientificReturnWatchId(watch_id),
                objective=InvestigationObjective.DISCOVER_CANDIDATE,
                candidate_id=None,
                idempotency_key=f"bench:{reference}:{uuid4()}",
                caller=BENCH,
            )
        )
        await session.commit()
        identifier = investigation.id

    for attempt in range(1, passes + 1):
        async with async_session_factory() as session:
            item = await build_full_agentic_executor(
                session, RunDeadline(deadline_seconds)
            ).execute(
                ExecuteFullAgenticInput(
                    investigation_id=identifier,
                    worker_id=f"bench-{reference}-{attempt}",
                )
            )
            await session.commit()
            if item.status.value in TERMINAL:
                break

    async with async_session_factory() as session:
        repository = get_full_agentic_repository(session)
        item = await repository.get_investigation(identifier)
        events = await repository.list_events(identifier)
        candidates = (
            (
                await session.execute(
                    text(
                        "SELECT c.doi, c.title, c.source, l.relation_kind "
                        "FROM scientific_return_candidates c "
                        "JOIN sr_agentic_investigation_candidates l "
                        "  ON l.candidate_id = c.id "
                        "WHERE l.investigation_id = :i"
                    ),
                    {"i": str(identifier)},
                )
            )
            .mappings()
            .all()
        )
        assert item is not None
        return {
            "investigationId": str(identifier),
            "status": item.status.value,
            "degradedReason": item.degraded_reason,
            "failureReason": item.failure_reason,
            "recoveryCount": item.recovery_count,
            "usage": {
                "iterations": item.usage.iterations,
                "queries": item.usage.queries,
                "results": item.usage.results,
                "candidates": item.usage.candidates,
                "llmCalls": item.usage.llm_calls,
            },
            "candidates": [dict(row) for row in candidates],
            "trajectory": [
                {
                    "sequence": event.sequence,
                    "kind": event.kind.value,
                    "occurredAt": event.occurred_at.isoformat(),
                    "payload": event.payload,
                }
                for event in events
            ],
        }


def summarise(results: list[dict[str, object]]) -> None:
    scored = [r for r in results if r.get("expectedDoi")]
    found = sum(1 for r in scored if r.get("expectedFound"))
    degraded = sum(1 for r in results if r.get("degradedReason"))
    print("\n" + "=" * 72)
    print(f"samples          {len(results)}")
    if scored:
        print(f"expected DOIs    {found}/{len(scored)}")
    print(f"degraded         {degraded}")
    print(f"candidates       {sum(len(r.get('candidates') or []) for r in results)}")
    print(
        "model calls      "
        f"{sum((r.get('usage') or {}).get('llmCalls', 0) for r in results)}"
    )
    for row in results:
        if row.get("expectedDoi") and not row.get("expectedFound"):
            print(f"  MISSED {row['sample']} -> {row['expectedDoi']}")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="completed project to reuse")
    parser.add_argument("--samples", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path("bench-results.json"))
    parser.add_argument("--object", help="which consulted object, if several")
    parser.add_argument("--deadline", type=float, default=3000.0)
    parser.add_argument("--passes", type=int, default=5)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave the last sample loaded instead of restoring the original rows",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    samples = read_samples(args.samples)
    target = await resolve_target(args.project, args.object)

    print(f"project {target.project_id}")
    print(
        f"  object  {target.object_id}  (currently "
        f"{target.original_inventory_number} · {target.original_object_name})"
    )
    print(f"  user    {target.user_id}  (currently {target.original_user_name})")
    print(f"  samples {len(samples)}")
    print(
        "\nthis rewrites those two rows once per sample"
        f"{'' if args.keep else ' and restores them at the end'}\n"
    )
    if args.dry_run:
        for sample in samples:
            print(f"  would run {sample.reference_number} · {sample.scientific_name}")
        return 0

    results: list[dict[str, object]] = []
    started = time.monotonic()
    try:
        for index, sample in enumerate(samples, start=1):
            began = time.monotonic()
            print(
                f"[{index}/{len(samples)}] {sample.reference_number} · "
                f"{sample.scientific_name} · {sample.author}",
                flush=True,
            )
            try:
                await write_rows(
                    target,
                    sample.scientific_name,
                    sample.reference_number,
                    sample.author,
                )
                watch_id, snapshot = await refresh_snapshot(target)
                outcome = await run_investigation(
                    watch_id, sample.reference_number, args.deadline, args.passes
                )
            except Exception as exc:  # noqa: BLE001 - one bad sample must not end the run
                print(f"    ERROR {type(exc).__name__}: {exc}", flush=True)
                results.append(
                    {
                        "sample": sample.reference_number,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                args.out.write_text(json.dumps(results, indent=2, default=str))
                continue
            dois = {(c.get("doi") or "").casefold() for c in outcome["candidates"]}
            expected_found = (
                sample.expected_doi.casefold() in dois if sample.expected_doi else None
            )
            outcome |= {
                "sample": sample.reference_number,
                "scientificName": sample.scientific_name,
                "author": sample.author,
                "expectedDoi": sample.expected_doi,
                "expectedFound": expected_found,
                "snapshot": snapshot,
                "seconds": round(time.monotonic() - began, 1),
            }
            results.append(outcome)
            args.out.write_text(json.dumps(results, indent=2, default=str))
            usage = outcome["usage"]
            if expected_found is None:
                mark = ""
            else:
                mark = " expected:FOUND" if expected_found else " expected:MISSED"
            print(
                f"    {outcome['status']} candidates={len(outcome['candidates'])} "
                f"llm={usage['llmCalls']} queries={usage['queries']} "
                f"degraded={'yes' if outcome['degradedReason'] else 'no'} "
                f"({outcome['seconds']}s){mark}",
                flush=True,
            )
            for candidate in outcome["candidates"]:
                print(
                    f"      [{candidate.get('relation_kind', '?'):12}] "
                    f"{candidate.get('doi')} | {str(candidate.get('title'))[:70]}",
                    flush=True,
                )
    finally:
        if not args.keep:
            await write_rows(
                target,
                target.original_object_name,
                target.original_inventory_number,
                target.original_user_name,
            )
            print("\noriginal object and researcher rows restored")

    summarise(results)
    print(f"\nwrote {args.out}  ({time.monotonic() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
