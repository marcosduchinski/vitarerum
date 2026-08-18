"""The ORM registry is what lets a job process talk to the database.

The API registers every mapper by accident: ``app.main`` imports every router,
which imports every model. Anything else that opens a session — a migration, the
scheduled scientific-return sweep — registers nothing unless it says so, and a
cross-context foreign key then fails to resolve at runtime.

Contexts used to paper over this by importing each other's model modules, which
broke the architecture contracts. The registry replaces that, so these tests are
also what keeps those imports from creeping back.

These run in a clean interpreter on purpose. Inside the test session hundreds of
modules are already imported, so an in-process assertion would pass whether the
registry works or not.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_APP = Path(__file__).resolve().parent.parent / "app"



def _resolve(module: str, record: str, column: str) -> str:
    return (
        f"from {module} import {record}\n"
        f"print(next(iter({record}.__table__.c.{column}.foreign_keys)).column)\n"
    )


# One foreign key per direction that crosses a context boundary. Both point at a
# context the owner is forbidden to import, so only the registry can resolve them.
_CROSS_CONTEXT_KEYS = [
    pytest.param(
        _resolve(
            "app.scientific_return.infrastructure.models",
            "CandidatePublicationRecord",
            "confirmed_publication_entry_id",
        ),
        "publication_log_entries.id",
        id="scientific_return -> use_of_collections",
    ),
    pytest.param(
        _resolve(
            "app.use_of_collections.infrastructure.models",
            "StaffProjectTodoItemRecord",
            "owner_permission_id",
        ),
        "identity_permissions.id",
        id="use_of_collections -> identity",
    ),
]


def _run(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(("code", "target"), _CROSS_CONTEXT_KEYS)
def test_a_context_alone_cannot_resolve_its_cross_context_key(
    code: str, target: str
) -> None:
    """Guards the assumption: without the registry these genuinely fail."""
    result = _run(code)

    assert result.returncode != 0
    assert "NoReferencedTableError" in result.stderr


@pytest.mark.parametrize(("code", "target"), _CROSS_CONTEXT_KEYS)
def test_the_registry_resolves_a_cross_context_key(code: str, target: str) -> None:
    result = _run("import app.orm_registry\n" + code)

    assert result.returncode == 0, result.stderr
    assert target in result.stdout


@pytest.mark.parametrize(("code", "target"), _CROSS_CONTEXT_KEYS)
def test_the_scheduled_sweep_entry_point_registers_the_orm(
    code: str, target: str
) -> None:
    """The Cloud Run job runs this module; it must not import a broken ORM."""
    result = _run("import app.jobs.scientific_return\n" + code)

    assert result.returncode == 0, result.stderr
    assert target in result.stdout


def test_every_model_module_is_registered() -> None:
    """The registry is the one list; a new context must not be forgotten in it.

    Forgetting one is invisible until a job process — never the API — resolves a
    foreign key into that context's tables.
    """
    discovered = sorted(
        ".".join(path.relative_to(_APP.parent).with_suffix("").parts)
        for path in _APP.glob("**/infrastructure/models.py")
    )
    assert discovered, "no model modules found; the glob is wrong"

    result = _run(
        "import app.orm_registry, sys\n"
        "for name in sys.modules:\n"
        "    if name.endswith('.infrastructure.models'):\n"
        "        print(name)\n"
    )

    assert result.returncode == 0, result.stderr
    registered = set(result.stdout.split())
    assert set(discovered) - registered == set()
