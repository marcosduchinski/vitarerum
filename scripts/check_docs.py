#!/usr/bin/env python3
"""Documentation checks for the Vitarerum repository.

Three things go stale silently in Markdown, and each has bitten this repository:

1. a link to a file that moved or was deleted;
2. a spec citing a test that no longer exists, which quietly turns a verified
   acceptance criterion into a claim;
3. a document that describes behaviour the code no longer has, with nothing
   saying so.

Standard library only, so it runs anywhere Python 3 does.

    python3 scripts/check_docs.py           # all checks
    python3 scripts/check_docs.py --links   # one check
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import subprocess
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEST_ROOT = ROOT / "vitarerum-api" / "test"

# Stale test references that predate the 2026-09-04 documentation pass. Each is
# a spec describing behaviour removed from the code; they are recorded as
# declared divergences 3 and 4 in docs/specs/README.md. Listed here so a *new*
# stale reference fails the check while these stay visible and counted.
# Removing a spec's stale requirement should remove its line from this list.
KNOWN_STALE = {
    ("002-vigilancia-retorno-cientifico", name)
    for name in ["test_a_new_interval_moves_the_next_review_from_the_last_search"]
} | {
    ("004-decisao-candidato-publicacao", name)
    for name in ["test_snooze_requires_a_future_date"]
} | {
    ("005-analise-llm-sombra", name)
    for name in [
        "test_shadow_analysis_is_audited_without_changing_candidate",
        "test_invalid_llm_response_is_persisted_as_failed_analysis",
        "test_shadow_analysis_feature_flag_prevents_llm_call",
        "test_llm_analysis_parser_rejects_fields_outside_the_contract",
    ]
}

VALID_STATUS = {"current", "proposed"}

# What a document may declare, by the directory it sits in. `proposed` is
# allowed outside docs/proposals/ because a specification may describe
# behaviour that is specified but not yet built (SPEC-021 does). `historical`
# is not allowed anywhere: a document that no longer describes the system is
# removed, not kept alongside the ones that do.
ALLOWED_STATUS = {
    "docs/proposals": {"proposed"},
}
DEFAULT_ALLOWED = {"current", "proposed"}

# Specs carry their status in a metadata row instead of front-matter; one source
# of truth per document, so nothing can drift between two of them.
SPEC_STATUS = {
    "implementado": "current",
    "especificado, nao implementado": "proposed",
}


def tracked_markdown() -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "*.md"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [ROOT / f for f in out.split("\0") if f and (ROOT / f).exists()]


def rel(p: pathlib.Path) -> str:
    return str(p.relative_to(ROOT))


# --------------------------------------------------------------------------- 1
def check_links(files: list[pathlib.Path]) -> list[str]:
    """Every relative link in a tracked Markdown file resolves to a real path."""
    problems = []
    for p in files:
        for m in re.finditer(r"\]\(([^)\s]+)\)", p.read_text(encoding="utf-8")):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = urllib.parse.unquote(target.split("#")[0])
            if path and not (p.parent / path).exists():
                problems.append(f"{rel(p)} -> {target}")
    return problems


# --------------------------------------------------------------------------- 2
def _test_index() -> dict[str, set[str]]:
    index: dict[str, set[str]] = collections.defaultdict(set)
    for p in TEST_ROOT.rglob("test_*.py"):
        text = p.read_text(encoding="utf-8")
        names = re.findall(r"^(?:async )?def (test_\w+)", text, re.M)
        index[p.name].update(names)
        index[str(p.relative_to(ROOT / "vitarerum-api"))].update(names)
    return index


def check_spec_tests() -> list[str]:
    """Every `file.py::test_name` a spec cites names a test that exists.

    A citation may abbreviate as `::test_other`, inheriting the file from the
    citation before it — the convention the specs already use.
    """
    if not TEST_ROOT.is_dir():
        return ["test tree not found: " + rel(TEST_ROOT)]
    index = _test_index()
    problems = []
    for spec in sorted((ROOT / "docs" / "specs").rglob("spec.md")):
        current = None
        text = spec.read_text(encoding="utf-8")
        for m in re.finditer(r"`(?:([\w./-]+\.py))?::(test_\w+)`", text):
            if m.group(1):
                current = m.group(1)
            name, path = m.group(2), m.group(1) or current
            if path is None:
                continue
            if (spec.parent.name, name) in KNOWN_STALE:
                continue
            if path not in index:
                problems.append(
                    f"{rel(spec)} -> {path}::{name} (no such test file)"
                )
            elif name not in index[path]:
                problems.append(f"{rel(spec)} -> {path}::{name} (no such test)")
    return problems


# --------------------------------------------------------------------------- 3
def _declared_status(p: pathlib.Path) -> str | None:
    text = p.read_text(encoding="utf-8")
    if p.name == "spec.md":
        m = re.search(r"^\| Estado \| (.+?) \|$", text, re.M)
        if not m:
            return None
        value = re.sub(r"\s*\(.*?\)", "", m.group(1)).replace("*", "").strip().lower()
        return SPEC_STATUS.get(value, value)
    if text.startswith("---\n"):
        m = re.search(r"^status:\s*(\w+)\s*$", text.split("---\n")[1], re.M)
        if m:
            return m.group(1)
    return None


def check_status(files: list[pathlib.Path]) -> list[str]:
    """Every tracked document under docs/ declares a status the directory
    it lives in allows."""
    problems = []
    for p in files:
        r = rel(p)
        if not r.startswith("docs/"):
            continue
        allowed = DEFAULT_ALLOWED
        for prefix, values in ALLOWED_STATUS.items():
            if r.startswith(prefix + "/"):
                allowed = values
        status = _declared_status(p)
        expected = " or ".join(f"`{v}`" for v in sorted(allowed))
        if status is None:
            problems.append(f"{r} declares no status (expected {expected})")
        elif status not in VALID_STATUS:
            problems.append(f"{r} declares unknown status `{status}`")
        elif status not in allowed:
            problems.append(
                f"{r} declares `{status}` where this directory allows {expected}"
            )
    return problems


CHECKS = {
    "links": ("broken local links", lambda f: check_links(f)),
    "tests": ("spec references to tests", lambda f: check_spec_tests()),
    "status": ("document status", lambda f: check_status(f)),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for name, (label, _) in CHECKS.items():
        ap.add_argument(f"--{name}", action="store_true", help=f"only check {label}")
    args = ap.parse_args()

    selected = [n for n in CHECKS if getattr(args, n)] or list(CHECKS)
    files = tracked_markdown()
    failed = False
    for name in selected:
        label, run = CHECKS[name]
        problems = run(files)
        if problems:
            failed = True
            print(f"FAIL  {label}: {len(problems)}")
            for problem in problems:
                print(f"        {problem}")
        else:
            print(f"ok    {label}")

    if KNOWN_STALE and "tests" in selected:
        print(f"note  {len(KNOWN_STALE)} stale test references tolerated "
              f"(docs/specs/README.md, divergences 3 and 4)")
    print(f"      {len(files)} tracked Markdown files checked")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
