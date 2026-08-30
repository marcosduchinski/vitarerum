"""Build the consultation project the bench starts from.

``bench_full_agentic.py`` measures the autonomous cycle against a *completed*
in-situ consultation: it rewrites that project's object and researcher rows
once per sample, rebuilds the snapshot, and runs an investigation. It never
creates the project, so until now reproducing the measurements began with an
undocumented manual setup — the single largest barrier to anyone outside this
machine repeating them.

This script closes that gap. It creates the smallest structure the bench needs:

    identity_users ──< identity_permissions ──< collection_use_projects
                                                          │
                                                collection_use_objects

The watch is deliberately *not* created here. The bench creates it on the first
sample and repoints it afterwards, because deleting a watch would take the
candidates, runs and investigations with it — which are the measurement.

Idempotent by reference number: run it twice and the second run reuses what the
first created rather than accumulating projects. That is what makes a teardown
unnecessary, which matters because none of the foreign keys cascade and an
ordered delete would span a dozen tables.

    uv run python scripts/full_agentic/seed_bench_project.py
    uv run python scripts/full_agentic/seed_bench_project.py --objects 2

The seeded researcher cannot log in: the password hash is a literal that no
verifier accepts. The rows are placeholders for a measurement, not an account.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4


def _project_root() -> Path:
    """Walk up to the directory holding ``app``, wherever this script sits."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "app").is_dir():
            return candidate
    raise SystemExit("could not find the project root: no ancestor contains app/")


sys.path.insert(0, str(_project_root()))

from sqlalchemy import text  # noqa: E402

import app.orm_registry  # noqa: E402, F401  (registers every mapper)
from app.database import async_session_factory  # noqa: E402

# Anything the bench writes to is disposable. The prefix keeps that promise
# visible in the data itself, and the guard below keeps this script from
# manufacturing something that reads like a real MUHNAC consultation.
BENCH_PREFIX = "PR-BENCH/"
NO_LOGIN = "!seeded-by-bench-no-login"

# Placeholders. The bench overwrites both on its first sample; they exist only
# so the snapshot the watch is built from has the shape it expects.
PLACEHOLDER_INVENTORY = "BENCH-000000"
PLACEHOLDER_OBJECT = "Placeholder specimen"
PLACEHOLDER_RESEARCHER = "Bench Researcher"


async def seed(reference: str, object_count: int) -> dict[str, object]:
    async with async_session_factory() as session:
        existing = (
            (
                await session.execute(
                    text(
                        "SELECT id, status, requested_by FROM collection_use_projects "
                        "WHERE reference_number = :r"
                    ),
                    {"r": reference},
                )
            )
            .mappings()
            .first()
        )

        if existing is not None:
            objects = (
                (
                    await session.execute(
                        text(
                            "SELECT id, inventory_number FROM collection_use_objects "
                            "WHERE project_id = :p ORDER BY id"
                        ),
                        {"p": existing["id"]},
                    )
                )
                .mappings()
                .all()
            )
            return {
                "created": False,
                "project_id": existing["id"],
                "reference": reference,
                "objects": [dict(row) for row in objects],
            }

        now = datetime.now(UTC)
        user_id = str(uuid4())
        permission_id = str(uuid4())
        project_id = str(uuid4())

        await session.execute(
            text(
                "INSERT INTO identity_users (id, name, email, password_hash, status) "
                "VALUES (:i, :n, :e, :p, 'ACTIVE')"
            ),
            {
                "i": user_id,
                "n": PLACEHOLDER_RESEARCHER,
                # .invalid is reserved by RFC 2606 and can never be delivered to.
                "e": f"bench-{project_id[:8]}@example.invalid",
                "p": NO_LOGIN,
            },
        )
        await session.execute(
            text(
                "INSERT INTO identity_permissions (id, user_id, group_id) "
                "VALUES (:i, :u, 'grp-ext')"
            ),
            {"i": permission_id, "u": user_id},
        )
        await session.execute(
            text(
                "INSERT INTO collection_use_projects "
                "(id, reference_number, title, purpose, type, status, result, "
                " begin_date, end_date, requested_by) "
                "VALUES (:i, :r, :t, :pu, 'IN_SITU_VISIT', 'COMPLETED', 'COMPLETED', "
                " :b, :e, :rq)"
            ),
            {
                "i": project_id,
                "r": reference,
                "t": "Bench consultation for autonomous-search measurement",
                "pu": (
                    "Synthetic project created by seed_bench_project.py so the "
                    "autonomous-search bench has a completed consultation to run "
                    "against. Not a real consultation."
                ),
                "b": date(now.year, 1, 1),
                "e": date(now.year, 1, 2),
                "rq": permission_id,
            },
        )

        objects: list[dict[str, str]] = []
        for index in range(object_count):
            object_id = str(uuid4())
            inventory = (
                PLACEHOLDER_INVENTORY
                if object_count == 1
                else f"{PLACEHOLDER_INVENTORY}-{index + 1}"
            )
            await session.execute(
                text(
                    "INSERT INTO collection_use_objects "
                    "(id, project_id, inventory_number, object_name, category, "
                    " description, requested_at, requested_by) "
                    "VALUES (:i, :p, :inv, :n, :c, :d, :at, :by)"
                ),
                {
                    "i": object_id,
                    "p": project_id,
                    "inv": inventory,
                    "n": PLACEHOLDER_OBJECT,
                    "c": "ZOOLOGY",
                    "d": "Placeholder consulted object; the bench rewrites it.",
                    "at": now,
                    "by": permission_id,
                },
            )
            objects.append({"id": object_id, "inventory_number": inventory})

        await session.commit()
        return {
            "created": True,
            "project_id": project_id,
            "reference": reference,
            "user_id": user_id,
            "objects": objects,
        }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference",
        default=f"{BENCH_PREFIX}COL/0001",
        help="reference number of the seeded project",
    )
    parser.add_argument(
        "--objects",
        type=int,
        default=1,
        help="consulted objects to create; more than one exercises the fan-out",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=f"allow a reference that does not start with {BENCH_PREFIX}",
    )
    args = parser.parse_args()

    if not args.reference.startswith(BENCH_PREFIX) and not args.force:
        raise SystemExit(
            f"refusing to seed {args.reference!r}: a bench project should be "
            f"recognisable as one, so its reference must start with "
            f"{BENCH_PREFIX!r}. Pass --force if you meant it."
        )
    if args.objects < 1:
        raise SystemExit("--objects must be at least 1")

    result = await seed(args.reference, args.objects)
    verb = "created" if result["created"] else "already present, reused"
    print(f"project {result['project_id']}  ({verb})")
    print(f"  reference {result['reference']}")
    for row in result["objects"]:
        print(f"  object    {row['id']}  {row['inventory_number']}")

    print("\nrun the bench against it:\n")
    objects = result["objects"]
    flag = "" if len(objects) == 1 else f" \\\n      --object {objects[0]['id']}"
    print(
        f"  ./scripts/full_agentic/bench.sh \\\n"
        f"      --project {result['project_id']}{flag} \\\n"
        f"      --samples scripts/full_agentic/bench_samples.example.csv"
    )
    if not result["created"]:
        print(
            "\nthe object and researcher rows carry whatever the last bench run "
            "left there;\nthe next run overwrites them on its first sample."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
