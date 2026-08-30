#!/usr/bin/env bash
#
# Start what the autonomous-search bench needs, check it, and run it.
#
# The bench exercises the real cycle against live bibliographic sources and a
# real model, so its prerequisites are not optional and a missing one produces
# a confusing failure hours later rather than immediately. This checks them all
# before spending anything.
#
# Prerequisites (this script starts or verifies each):
#   1. PostgreSQL     — started with docker compose and waited for
#   2. Migrations     — brought to head
#   3. A model        — reachable, with the configured model pulled
#   4. Feature switch — SCIENTIFIC_RETURN_FULL_AGENTIC_ENABLED=true
#   5. Sources        — at least one inspectable source operational, or the
#                       configuration refuses to start an investigation
#
# Usage:
#   ./scripts/full_agentic/bench.sh --project <uuid> \
#       --samples scripts/full_agentic/bench_samples.example.csv
#   ./scripts/full_agentic/bench.sh --project <uuid> --samples my.csv --dry-run
#
# Any further arguments are passed through to bench_full_agentic.py.
#
# The API itself is not needed: the bench drives the use cases directly. To
# inspect the results in the panel afterwards:
#   uv run uvicorn app.main:app --reload

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# Walk up to the project root rather than counting directories, so filing this
# script deeper does not break it.
ROOT="$HERE"
while [ ! -d "$ROOT/app" ] && [ "$ROOT" != "/" ]; do ROOT="$(dirname "$ROOT")"; done
[ -d "$ROOT/app" ] || { echo "could not find the project root" >&2; exit 1; }
cd "$ROOT"

RUN="${RUN:-uv run}"
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

say "1/5  PostgreSQL"
if ! docker compose ps --status running --services 2>/dev/null | grep -q postgres; then
  docker compose up -d postgres
fi
for _ in $(seq 1 30); do
  if docker compose exec -T postgres pg_isready -U vitarerum -d vitarerum >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker compose exec -T postgres pg_isready -U vitarerum -d vitarerum >/dev/null \
  || fail "PostgreSQL did not become ready"
echo "     ready"

say "2/5  Migrations"
$RUN alembic upgrade head >/dev/null
echo "     at $($RUN alembic current 2>/dev/null | tail -1)"

say "3/5  Model"
OLLAMA_URL="$($RUN python -c 'from app.config import settings; print(settings.ollama_base_url)')"
MODEL="$($RUN python -c 'from app.config import settings; print(settings.scientific_return_llm_model)')"
TAGS="$(curl -sS --max-time 10 "${OLLAMA_URL}/api/tags" || true)"
[ -n "$TAGS" ] || fail "no model server at ${OLLAMA_URL}"
if ! printf '%s' "$TAGS" | grep -q "\"${MODEL}\""; then
  fail "model ${MODEL} is not pulled — run: ollama pull ${MODEL}"
fi
echo "     ${MODEL} available at ${OLLAMA_URL}"

say "4/5  Configuration"
$RUN python - <<'PY'
import sys
from app.config import settings
from app.scientific_return.presentation.dependencies import (
    get_full_agentic_configuration,
)

configuration = get_full_agentic_configuration()
diagnostics = configuration.source_diagnostics()
if not configuration.enabled:
    sys.exit("     SCIENTIFIC_RETURN_FULL_AGENTIC_ENABLED is false")
if not diagnostics["configurationValid"]:
    sys.exit(f"     {diagnostics['message']}")
print(f"     enabled · sources {', '.join(diagnostics['operationalSources'])}")
print(f"     inspectable evidence from {', '.join(diagnostics['inspectableEvidenceSources'])}")
print(f"     reasoning {'ON' if settings.scientific_return_llm_reasoning else 'off'}"
      f" · num_predict {settings.scientific_return_llm_num_predict}")
PY

say "5/5  Bench"
exec $RUN python "$HERE/bench_full_agentic.py" "$@"
