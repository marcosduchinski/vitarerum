# syntax=docker/dockerfile:1.7

FROM node:22-slim AS ui-builder

WORKDIR /ui
COPY vitarerum-ui/package.json vitarerum-ui/package-lock.json ./
RUN npm ci
COPY vitarerum-ui/ ./
# src/config e' copiado como asset literal (o angular.json nao tem
# fileReplacements), entao o que estiver em src/config/environment.json e' o que
# vai ao ar. Se ele apontar a API para localhost, e' a maquina de quem abrir o
# site que sera' chamada, e nada funciona.
RUN npm run build

FROM python:3.12-slim AS api-builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

RUN pip install --no-cache-dir uv

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=vitarerum-api/uv.lock,target=uv.lock \
    --mount=type=bind,source=vitarerum-api/pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

COPY vitarerum-api/ /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app
COPY --from=api-builder --chown=app:app /app /app
COPY --from=ui-builder --chown=app:app /ui/dist/vitarerum-ui/browser /app/static
RUN mkdir -p /app/data && chown app:app /app/data

USER app
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
