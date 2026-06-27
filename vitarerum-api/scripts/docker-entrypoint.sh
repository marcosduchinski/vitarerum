#!/usr/bin/env sh
# Apply database migrations, then exec the container's main process (CMD).
set -e

echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] Starting: $*"
exec "$@"
