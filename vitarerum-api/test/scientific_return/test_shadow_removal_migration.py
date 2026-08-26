from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Protocol

from sqlalchemy.sql.elements import TextClause


class _NamedTable(Protocol):
    name: str


class _Operations:
    def __init__(self) -> None:
        self.statements: list[TextClause] = []
        self.inserts: list[tuple[str, list[dict[str, object]]]] = []

    def execute(self, statement: TextClause) -> None:
        self.statements.append(statement)

    def bulk_insert(
        self, table: _NamedTable, rows: list[dict[str, object]]
    ) -> None:
        self.inserts.append((str(table.name), rows))


def _migration() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "alembic/versions/00000075_0075_remove_scientific_return_shadow_analysis.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0075", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_deletes_only_shadow_rows_and_prompt_structure() -> None:
    migration = _migration()
    operations = _Operations()
    migration.op = operations

    migration.upgrade()

    sql = "\n".join(str(statement) for statement in operations.statements)
    assert "pver-scientific-return-shadow%" in sql
    assert "pver-sr-full-reader" not in sql
    assert "DELETE FROM scientific_return_agent_analyses" in sql
    assert "DELETE FROM ai_prompt_template_versions" in sql
    assert "DELETE FROM ai_prompt_templates" in sql


def test_downgrade_restores_prompt_structure_but_not_deleted_analysis_data() -> None:
    migration = _migration()
    operations = _Operations()
    migration.op = operations

    migration.downgrade()

    assert [table for table, _ in operations.inserts] == [
        "ai_prompt_templates",
        "ai_prompt_template_versions",
    ]
