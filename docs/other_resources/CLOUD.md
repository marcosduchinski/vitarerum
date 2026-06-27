# Deploying to Google Cloud (Cloud Run + Cloud SQL)

This guide takes the containerized `vitarerum-api` from a local Docker build to a
running, internet-facing service on **Cloud Run**, backed by **Cloud SQL for
PostgreSQL**. Secrets are stored in **Secret Manager**, the image lives in
**Artifact Registry**, and database migrations run as a one-shot **Cloud Run
Job** (decoupled from the serving containers so autoscaled instances never race
on `alembic upgrade head`).

Target topology:

```
Internet ──HTTPS──> Cloud Run (vitarerum-api)  ──unix socket──> Cloud SQL (Postgres 16)
                          ▲                                          ▲
                    Secret Manager                          Cloud Run Job (migrate)
```

> ⚠️ **Uploaded files and Cloud Run.** Uploads are stored on the filesystem under
> `DATA_DIR`. Cloud Run's container filesystem is **ephemeral and per-instance**,
> so files written by one instance are lost on restart and invisible to other
> instances. Before relying on uploads in production, choose one of:
> - **Object storage (recommended):** store uploads in a **Cloud Storage**
>   bucket. This is the cheapest, durable, multi-instance-safe option, but
>   requires swapping the storage adapter for a GCS-backed one.
> - **Mounted volume:** attach a
>   [Cloud Run volume mount](https://cloud.google.com/run/docs/configuring/services/volume-mounts)
>   backed by a Cloud Storage bucket (GCS FUSE) or **Filestore**, and point
>   `DATA_DIR` at the mount path.
>
> The steps below deploy the app as-is; uploads will not persist until you adopt
> one of the above. Everything else (API, auth, database) works unchanged.

---

## 0. Prerequisites

- A Google Cloud project with billing enabled.
- The [`gcloud` CLI](https://cloud.google.com/sdk/docs/install) installed and authenticated:
  ```bash
  gcloud auth login
  gcloud auth application-default login
  ```
- Docker (only needed if you want to build locally; otherwise Cloud Build does it).

Set shell variables used throughout this guide (adjust values):

```bash
export PROJECT_ID="your-project-id"
export REGION="europe-west1"
export REPO="vitarerum"                 # Artifact Registry repo
export SERVICE="vitarerum-api"          # Cloud Run service
export SQL_INSTANCE="vitarerum-db"      # Cloud SQL instance
export DB_NAME="vitarerum"
export DB_USER="vitarerum"

gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"

# Derived
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/api:latest"
export SQL_CONN="${PROJECT_ID}:${REGION}:${SQL_INSTANCE}"
```

Enable the required APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com
```

---

## 1. Make the container Cloud Run–compatible (one-time code change)

Cloud Run injects a `PORT` env var (default **8080**) and the container **must**
listen on it. It also terminates TLS and forwards requests over a proxy. The
current image hardcodes port 8000 and always migrates on startup, so apply these
two small edits.

**`scripts/docker-entrypoint.sh`** — make migrations opt-in (off by default so
serving instances don't migrate):

```sh
#!/usr/bin/env sh
# Optionally migrate (RUN_MIGRATIONS=1), then exec the main process (CMD).
set -e

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
  alembic upgrade head
fi

echo "[entrypoint] Starting: $*"
exec "$@"
```

**`Dockerfile`** — replace the final `CMD` so it honors `$PORT` and trusts the
proxy headers:

```dockerfile
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
```

These changes are backward compatible: `docker compose` still works (no `PORT`
set → 8000; set `RUN_MIGRATIONS=1` in the compose `api` service to keep
migrate-on-boot locally).

---

## 2. Create the Artifact Registry repository

```bash
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Vitarerum container images"
```

---

## 3. Build and push the image

Cloud Build builds from the repo root using the existing `Dockerfile`:

```bash
gcloud builds submit --tag "$IMAGE"
```

(Local alternative: `docker build -t "$IMAGE" . && docker push "$IMAGE"` after
`gcloud auth configure-docker ${REGION}-docker.pkg.dev`.)

---

## 4. Provision Cloud SQL (PostgreSQL)

```bash
# Instance (db-f1-micro is fine for staging; size up for production)
gcloud sql instances create "$SQL_INSTANCE" \
  --database-version=POSTGRES_16 \
  --tier=db-f1-micro \
  --region="$REGION"

# Application database
gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE"

# Application user with a generated password
export DB_PASSWORD="$(openssl rand -base64 24)"
gcloud sql users create "$DB_USER" \
  --instance="$SQL_INSTANCE" \
  --password="$DB_PASSWORD"
```

Build the async connection string. Over the Cloud SQL **unix socket** (mounted
by Cloud Run at `/cloudsql/<CONN>`), asyncpg uses the `host` query parameter:

```bash
# URL-encode the password if it contains reserved characters (@ : / ? & = %).
export DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${SQL_CONN}"
```

> Alternative connection paths: a private-IP instance with the
> [Serverless VPC connector](https://cloud.google.com/run/docs/configuring/vpc-connectors),
> or the Cloud SQL Auth Proxy. The unix-socket form above is the simplest for
> Cloud Run and needs no networking setup.

---

## 5. Store secrets in Secret Manager

Keep the DB URL and app secrets out of plaintext env config:

```bash
printf '%s' "$DATABASE_URL"           | gcloud secrets create database-url   --data-file=-
printf '%s' "$(openssl rand -base64 48)" | gcloud secrets create jwt-secret  --data-file=-
```

Grant the Cloud Run runtime service account access (defaults to the Compute
Engine default SA unless you create a dedicated one):

```bash
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for S in database-url jwt-secret; do
  gcloud secrets add-iam-policy-binding "$S" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="roles/secretmanager.secretAccessor"
done
```

---

## 6. Run database migrations (Cloud Run Job)

Create a Job from the same image that runs Alembic directly (overriding the
entrypoint), with the Cloud SQL socket attached:

```bash
gcloud run jobs create "${SERVICE}-migrate" \
  --image="$IMAGE" \
  --region="$REGION" \
  --add-cloudsql-instances="$SQL_CONN" \
  --set-secrets="DATABASE_URL=database-url:latest" \
  --set-env-vars="APP_ENV=production" \
  --command="alembic" \
  --args="upgrade,head"

# Execute it (re-run after every deploy that adds migrations)
gcloud run jobs execute "${SERVICE}-migrate" --region="$REGION" --wait
```

If you change schema later, push a new image and re-run this Job before (or as
part of) the deploy.

---

## 7. Deploy the Cloud Run service

`CORS_ORIGINS` is a JSON list whose commas clash with the default
`--set-env-vars` delimiter, so use a custom delimiter (`^@^`):

```bash
gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --add-cloudsql-instances="$SQL_CONN" \
  --set-secrets="DATABASE_URL=database-url:latest,JWT_SECRET=jwt-secret:latest" \
  --set-env-vars="^@^APP_ENV=production@CORS_ORIGINS=[\"https://app.example.com\"]@ACCESS_TOKEN_TTL_MINUTES=720" \
  --port=8080 \
  --cpu=1 --memory=512Mi \
  --min-instances=0 --max-instances=10 \
  --allow-unauthenticated
```

Notes:
- `APP_ENV=production` activates `validate_non_local_security`, which is why all
  three secrets and an explicit (non-`*`) `CORS_ORIGINS` are mandatory — a
  misconfigured deploy fails fast instead of starting insecurely.
- `RUN_MIGRATIONS` is intentionally **unset** here, so serving instances do not
  migrate. Migrations are owned by the Job in Step 6.
- Drop `--allow-unauthenticated` if the API should sit behind IAP / an internal
  load balancer instead of being public.
- **File uploads do not persist** with this plain deployment — see the warning at
  the top of this guide and configure object storage or a volume mount before
  going live.

---

## 8. Seed initial identity data (first deploy only)

Load the fixed groups and the initial `SYS_ADMIN` permission. `gcloud sql
connect` temporarily allowlists your IP and opens `psql`:

```bash
gcloud sql connect "$SQL_INSTANCE" --user="$DB_USER" --database="$DB_NAME" < scripts/seed.sql
```

---

## 9. Verify

```bash
export SERVICE_URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
curl -s "${SERVICE_URL}/api/v1/health"
# => {"status":"ok","application":"vitarerum-api"}
```

You can also tail logs:

```bash
gcloud run services logs read "$SERVICE" --region="$REGION"
```

---

## 10. Redeploying (subsequent releases)

```bash
# 1) Build the new image
gcloud builds submit --tag "$IMAGE"

# 2) Apply any new migrations
gcloud run jobs execute "${SERVICE}-migrate" --region="$REGION" --wait

# 3) Roll out the new revision
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION"
```

For zero-surprise rollouts, deploy with `--no-traffic` and shift traffic with
`gcloud run services update-traffic` once the revision is verified.

---

## Cost / cleanup

To tear everything down:

```bash
gcloud run services delete "$SERVICE" --region="$REGION" --quiet
gcloud run jobs delete "${SERVICE}-migrate" --region="$REGION" --quiet
gcloud sql instances delete "$SQL_INSTANCE" --quiet
gcloud artifacts repositories delete "$REPO" --location="$REGION" --quiet
for S in database-url jwt-secret; do gcloud secrets delete "$S" --quiet; done
```

---

## Checklist

- [ ] Step 1 container changes applied (`$PORT`, `--proxy-headers`, opt-in migrations)
- [ ] APIs enabled, Artifact Registry repo created
- [ ] Image built and pushed
- [ ] Cloud SQL instance, database, and user created
- [ ] `DATABASE_URL`, `JWT_SECRET` in Secret Manager + IAM granted
- [ ] Migration Job created and executed
- [ ] Service deployed with `APP_ENV=production` and explicit `CORS_ORIGINS`
- [ ] Identity data seeded
- [ ] `/api/v1/health` returns 200
