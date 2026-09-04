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
import ast
import collections
import pathlib
import re
import subprocess
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEST_ROOT = ROOT / "vitarerum-api" / "test"

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


# --------------------------------------------------------------------------- 4
DIAGRAM_DIRS = ("docs/diagrams", "docs/architecture")


def check_diagrams(files: list[pathlib.Path]) -> list[str]:
    """Every diagram has a source, a name that matches what it renders to, and
    a document that points at it.

    PlantUML names its output after the `@startuml <name>` line, not after the
    file. When the two disagree, regenerating writes a file nobody references
    and the old one silently goes stale — so the two are required to match.
    """
    prose = "\n".join(
        p.read_text(encoding="utf-8") for p in files if p.suffix == ".md"
    )
    problems = []
    for directory in DIAGRAM_DIRS:
        d = ROOT / directory
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix == ".puml":
                first = f.read_text(encoding="utf-8").split("\n", 1)[0]
                m = re.match(r"@startuml\s+(\S+)", first)
                if not m:
                    problems.append(f"{rel(f)} has no `@startuml <name>` line")
                elif m.group(1) != f.stem:
                    problems.append(
                        f"{rel(f)} renders to {m.group(1)}.svg; "
                        f"rename the source to match"
                    )
                if not f.with_suffix(".svg").exists():
                    problems.append(f"{rel(f)} has no rendered .svg")
            elif f.suffix in {".svg", ".mmd"}:
                if f.name not in prose:
                    problems.append(f"{rel(f)} is referenced by no document")
                if f.suffix == ".svg" and not f.with_suffix(".puml").exists():
                    problems.append(f"{rel(f)} has no .puml source")
    return problems


# --------------------------------------------------------------------------- 5
CITATION = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|ts|yaml|yml|html|sql))(?::(\d+))?`")
CITATION_ROOTS = (
    "", "vitarerum-api", "vitarerum-api/app", "vitarerum-ui", "vitarerum-ui/src",
)


def _resolve_citation(
    target: str, index: dict[str, list[pathlib.Path]]
) -> pathlib.Path | None:
    """Find the file a citation names.

    Specifications cite fragments relative to the bounded context named in their
    own header - `domain/models.py` inside a spec about `app/identity`. So a
    fragment counts as resolved when some tracked file's path ends with it;
    anything that matches nothing at all is dangling.
    """
    for root in CITATION_ROOTS:
        candidate = ROOT / root / target
        if candidate.is_file():
            return candidate
    matches = index.get(pathlib.PurePosixPath(target).name, [])
    suffix = "/" + target
    return next((m for m in matches if str(m).endswith(suffix)), None)


def check_citations(files: list[pathlib.Path]) -> list[str]:
    """Every file a document cites exists, and every cited line is inside it.

    This proves a citation is not dangling, never that it is still true: line
    numbers drift silently as code moves around them, and no check can read a
    document's intent. A passing result means the target exists.
    """
    index: dict[str, list[pathlib.Path]] = collections.defaultdict(list)
    for path in subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n"):
        if path:
            index[pathlib.PurePosixPath(path).name].append(pathlib.PurePosixPath(path))

    problems = []
    for p in files:
        if p.suffix != ".md":
            continue
        for m in CITATION.finditer(p.read_text(encoding="utf-8")):
            target, line = m.group(1), m.group(2)
            found = _resolve_citation(target, index)
            if found is None:
                problems.append(
                    f"{rel(p)} cites {target}, which matches no tracked file"
                )
                continue
            if line:
                real = ROOT / found
                length = len(real.read_text(errors="ignore").split("\n"))
                if int(line) > length:
                    problems.append(
                        f"{rel(p)} cites {target}:{line}, but that file"
                        f" has {length} lines"
                    )
    return problems


# --------------------------------------------------------------------------- 6
API_ROOT = ROOT / "vitarerum-api" / "app"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
# Routes that carry no domain behaviour, so no specification owns them.
ROUTE_EXEMPT = {"/health", "/{full_path:path}"}


def _string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _declared_routes() -> list[str]:
    """Route paths, read from the decorators without importing the application.

    Static on purpose: the documentation check must run with the standard
    library alone, and importing the app would drag in the whole backend.
    """
    trees, prefixes = {}, {}
    for f in sorted(API_ROOT.rglob("*.py")):
        try:
            trees[f] = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(trees[f]):
            if not (isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)):
                continue
            fn = n.value.func
            if getattr(fn, "id", getattr(fn, "attr", "")) != "APIRouter":
                continue
            pre = next(
                (_string(k.value) for k in n.value.keywords if k.arg == "prefix"), ""
            )
            for t in n.targets:
                if isinstance(t, ast.Name):
                    prefixes[t.id] = pre or ""

    routes = set()
    for tree in trees.values():
        for n in ast.walk(tree):
            if not isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for dec in n.decorator_list:
                is_route = isinstance(dec, ast.Call) and isinstance(
                    dec.func, ast.Attribute
                )
                if not is_route:
                    continue
                if dec.func.attr not in HTTP_METHODS or not dec.args:
                    continue
                path = _string(dec.args[0])
                if path is None:
                    continue
                router = getattr(dec.func.value, "id", None)
                routes.add(prefixes.get(router, "") + path)
    return sorted(routes)


def check_routes(files: list[pathlib.Path]) -> list[str]:
    """Every HTTP route the backend declares is named by some specification.

    Matching is by the route's last non-parameter segment, which is what makes a
    route findable by grep. A route nobody specified is the failure that this
    repository kept rediscovering by hand.
    """
    if not API_ROOT.is_dir():
        return []
    spec_dir = ROOT / "docs" / "specs"
    specs = "\n".join(
        p.read_text(encoding="utf-8") for p in spec_dir.rglob("spec.md")
    )
    problems = []
    for route in _declared_routes():
        if route in ROUTE_EXEMPT:
            continue
        segments = [s for s in route.split("/") if s and not s.startswith("{")]
        if segments and segments[-1] not in specs:
            problems.append(
                f"{route} is declared in code but named by no specification"
            )
    return problems


CHECKS = {
    "links": ("broken local links", lambda f: check_links(f)),
    "tests": ("spec references to tests", lambda f: check_spec_tests()),
    "status": ("document status", lambda f: check_status(f)),
    "diagrams": ("diagrams", lambda f: check_diagrams(f)),
    "citations": ("code citations", lambda f: check_citations(f)),
    "routes": ("routes named by a spec", lambda f: check_routes(f)),
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

    print(f"      {len(files)} tracked Markdown files checked")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
