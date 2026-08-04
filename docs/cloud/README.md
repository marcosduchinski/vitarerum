# Tutorial de Deploy na Google Cloud

Este tutorial descreve como publicar `vitarerum-api` (FastAPI) e
`vitarerum-ui` (Angular) em uma unica imagem/container no Google Cloud Run,
usando Postgres acessivel pela rede privada da VPC e Ollama Cloud como
dependencias externas.

O objetivo final e ter:

- um unico servico Cloud Run chamado `vitarerum`;
- uma unica imagem no Artifact Registry;
- FastAPI servindo `/api/v1/*`;
- FastAPI servindo o build estatico do Angular para `/*`;
- migracoes Alembic executadas por um Cloud Run Job separado;
- uploads persistidos em Google Cloud Storage antes de liberar uso real;
- secrets sensiveis guardados no Secret Manager.

## Arquitetura final

```
Browser
  |
  | HTTPS
  v
Cloud Run service: vitarerum
  |
  |-- GET /api/v1/*  -> FastAPI routers
  |-- GET /*         -> Angular static files + SPA fallback
  |
  |-- HTTPS          -> Ollama Cloud
  |-- TCP Postgres   -> Postgres na VPC
  |-- HTTPS          -> Google Cloud Storage

Cloud Run job: vitarerum-migrate
  |
  |-- alembic upgrade head -> Postgres na VPC
```

Recomendacao: comece com um unico servico Cloud Run. Isso atende ao requisito
de build unico e elimina cross-origin nas chamadas normais do Angular para a
API. Separar UI e API em servicos diferentes pode ser feito depois, se houver
necessidade real de escala independente.

Regiao recomendada para este tutorial: `us-east1`. O motivo principal e custo:
o Always Free do Cloud Storage inclui 5 GB-mes de storage regional apenas em
`us-east1`, `us-west1` e `us-central1` (uso agregado entre essas tres regioes).
Usar `us-east1` tambem mantem Cloud Run, Artifact Registry e bucket no mesmo
recorte regional para este deploy inicial.

## Configuracao atual de rede e banco

O ambiente de producao atual usa Postgres em rede privada, acessado pelo Cloud
Run por meio da VPC `default` com egress `private-ranges-only`.

Parametros operacionais atuais:

```text
Compute Engine VM: postgres-gratis
Zona: us-east1-d
Postgres IP interno: 10.142.0.2
Postgres IP externo: 34.148.187.188
Subrede: 10.142.0.0/20
Usuario: vitarerum
Banco: vitarerum
Porta: 5432
```

A aplicacao deve usar o IP interno no Secret Manager:

```text
DATABASE_URL=postgresql+asyncpg://vitarerum:<senha>@10.142.0.2:5432/vitarerum
```

Nao grave a senha do banco em arquivos versionados. Atualize o secret
`DATABASE_URL` diretamente no Secret Manager.

Em um Postgres recem-criado, crie o role e o database antes de executar o Job
de migracao:

```bash
gcloud compute ssh postgres-gratis \
  --zone us-east1-d \
  --command "sudo -u postgres psql -c \"CREATE ROLE vitarerum WITH LOGIN PASSWORD '<senha>';\""

gcloud compute ssh postgres-gratis \
  --zone us-east1-d \
  --command "sudo -u postgres createdb -O vitarerum vitarerum"
```

Depois disso, `vitarerum-migrate` deve conseguir executar `alembic upgrade
head` usando o secret `DATABASE_URL`.

## Pre-requisitos

Ferramentas locais:

```bash
gcloud --version
docker --version
node --version
npm --version
python --version
```

Projeto Google Cloud:

- billing ativo;
- APIs habilitadas: Cloud Run, Cloud Build, Artifact Registry, Secret Manager
  e Cloud Storage;
- `gcloud` autenticado no projeto correto.

Checkpoint:

```bash
gcloud config get-value project
gcloud services list --enabled
```

Sucesso esperado: o projeto correto aparece e as APIs acima estao habilitadas.

## Passo 1: Validar o build Angular local

Entre no frontend e rode o build:

```bash
cd vitarerum-ui
npm ci
npm run build
```

Confirme o diretorio gerado:

```bash
ls dist/vitarerum-ui/browser
```

Sucesso esperado:

- `index.html` existe em `vitarerum-ui/dist/vitarerum-ui/browser`;
- os assets versionados do Angular tambem aparecem nesse diretorio.

Recomendacao: declarar `outputPath` explicitamente em `vitarerum-ui/angular.json`
para nao depender de default implicito do Angular CLI em upgrades futuros. O
Dockerfile deste tutorial assume:

```text
vitarerum-ui/dist/vitarerum-ui/browser
```

## Passo 2: Ajustar a configuracao runtime do Angular

O frontend le `/config/environment.json` em runtime. Para uma imagem unica,
API e UI ficam no mesmo origin, entao a API deve ser relativa.

Atualize `vitarerum-ui/src/config/environment.json`:

```json
{
  "app-name": "Vitarerum",
  "app-version": "0.0.0",
  "api-base-url": "/api/v1",
  "use-mock-api": false,
  "use-mock-auth": false,
  "turnstile-site-key": "<turnstile-site-key-publica-de-producao>"
}
```

Checkpoint:

```bash
cd vitarerum-ui
npm run build
cat dist/vitarerum-ui/browser/config/environment.json
```

Sucesso esperado: o arquivo no `dist` contem `"api-base-url": "/api/v1"`.

Recomendacao: para este projeto, manter `/api/v1` versionado e simples. Se um
dia a mesma imagem precisar rodar em origens diferentes, crie um pequeno script
de start para reescrever `/app/static/config/environment.json` a partir de env
vars antes de iniciar o Uvicorn.

## Passo 3: Servir o Angular pelo FastAPI

Adicione no `vitarerum-api/app/main.py`, depois de todos os `include_router`,
uma rota de fallback para SPA.

Implementacao recomendada:

```python
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

STATIC_DIR = (Path(__file__).resolve().parent.parent / "static").resolve()
API_PREFIX = settings.api_v1_prefix.strip("/")  # ex.: "api/v1"


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str) -> FileResponse:
    if full_path == API_PREFIX or full_path.startswith(f"{API_PREFIX}/"):
        raise HTTPException(status_code=404)

    candidate = (STATIC_DIR / full_path).resolve()
    if candidate.is_relative_to(STATIC_DIR) and candidate.is_file():
        return FileResponse(candidate)

    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(index_file)
```

Pontos importantes:

- a rota precisa ficar depois dos routers da API;
- nao monte `/assets` manualmente, porque o fallback ja serve arquivos reais;
- a checagem `is_relative_to(STATIC_DIR)` evita path traversal;
- se `static/index.html` ainda nao existir em dev/test, o fallback devolve 404
  em vez de erro interno;
- `/api/v1/rota-inexistente` deve continuar devolvendo 404, nao `index.html`;
- **(ajustado)** a comparacao `full_path == API_PREFIX` cobre o caso de borda
  de uma requisicao para exatamente `/api/v1` (sem barra final), que
  `full_path.startswith("api/v1/")` sozinho deixaria escapar para o fallback
  SPA.

Para testar isso localmente sem Docker, gere o build do Angular e copie o
resultado para `vitarerum-api/static/` (diretorio ja ignorado pelo
`.gitignore` do backend; se nao estiver, adicione `static/` a ele):

```bash
cd vitarerum-ui && npm run build && cd ..
rm -rf vitarerum-api/static
cp -r vitarerum-ui/dist/vitarerum-ui/browser vitarerum-api/static
```

Depois suba a API localmente (`uvicorn app.main:app --reload`, a partir de
`vitarerum-api/`) e valide o checkpoint:

```bash
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/config/environment.json
curl -i http://127.0.0.1:8000/api/v1/health
curl -i http://127.0.0.1:8000/api/v1/rota-inexistente
curl -i http://127.0.0.1:8000/api/v1
```

Sucesso esperado:

- `/` devolve HTML do Angular;
- `/config/environment.json` devolve JSON;
- `/api/v1/health` devolve status da API;
- `/api/v1/rota-inexistente` devolve 404;
- `/api/v1` (sem barra final, sem rota registrada) tambem devolve 404, nao `index.html`.

## Passo 4: Criar o Dockerfile unico

Crie um `Dockerfile` na raiz do repositorio:

```dockerfile
# syntax=docker/dockerfile:1.7

FROM node:22-slim AS ui-builder
WORKDIR /ui
COPY vitarerum-ui/package.json vitarerum-ui/package-lock.json ./
RUN npm ci
COPY vitarerum-ui/ ./
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
```

Cloud Run injeta a env var `PORT`; por isso o `CMD` usa `sh -c`. Nao recoloque
`alembic upgrade head` no entrypoint do servico. Migracao sera tratada por Job.

Crie tambem `.dockerignore` na raiz:

```dockerignore
.git
.gitignore
.github
**/__pycache__
**/*.py[cod]
**/.venv
**/.pytest_cache
**/.mypy_cache
**/.ruff_cache
**/.grimp_cache
**/.import_linter_cache
**/.idea
**/.vscode
**/.angular
**/node_modules
**/dist
**/test-results
**/playwright-report
**/.env
**/.env.local
**/.env.*.local
vitarerum-api/data
vitarerum-api/uploads
vitarerum-api/static
```

**(ajustado)** `**/.venv` precisa estar na lista: `vitarerum-api/.venv` existe
no repositorio e mede ~200 MB — sem essa exclusao, todo `docker build`
carrega esse diretorio inteiro para o contexto de build, tornando-o
sensivelmente mais lento sem nenhum beneficio (o builder Python resolve as
dependencias do zero via `uv sync`, nao reaproveita esse `.venv` local).

Checkpoint:

```bash
docker build -t vitarerum:local .
docker run --rm -p 8080:8080 \
  -e APP_ENV=local \
  -e DATABASE_URL=postgresql+asyncpg://vitarerum:vitarerum@host.docker.internal:5432/vitarerum \
  vitarerum:local
```

**(ajustado)** `host.docker.internal` resolve automaticamente no Docker
Desktop (macOS/Windows). Em Docker Engine no Linux, adicione
`--add-host=host.docker.internal:host-gateway` ao `docker run` acima (Docker
20.10+), ou troque pelo IP da bridge do Docker.

Em outro terminal:

```bash
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/api/v1/health
```

Sucesso esperado: a mesma imagem responde HTML e API.

## Passo 5: Resolver armazenamento de arquivos

O backend atual usa `LocalDiskFileStorage`, que grava em `settings.data_dir`.
Isso nao e adequado para producao no Cloud Run, porque o filesystem do
container e efemero e cada instancia tem seu proprio disco.

Antes de liberar uploads reais, implemente um adapter GCS para `FileStoragePort`:

```python
class FileStoragePort(Protocol):
    async def save(self, content: bytes, filename: str) -> str: ...
    async def read(self, file_reference: str) -> bytes: ...
    async def delete(self, file_reference: str) -> None: ...
```

**(ajustado)** `FILE_STORAGE_BACKEND` e `GCS_BUCKET_NAME` **nao existem
ainda** em `app/config.py` — sao nomes de configuracao propostos por este
tutorial, nao settings ja implementadas. Implementar este passo inclui, no
minimo:

- adicionar `file_storage_backend: Literal["local", "gcs"] = "local"` e
  `gcs_bucket_name: str = ""` em `app/config.py`;
- escrever o adapter GCS (nova classe ao lado de `LocalDiskFileStorage` em
  `app/use_of_collections/infrastructure/file_storage.py`, ou um modulo
  novo, implementando o mesmo protocolo);
- trocar `LocalDiskFileStorage(settings.data_dir)` pela fabrica que escolhe
  o adapter certo com base em `file_storage_backend` nos **quatro** pontos
  de injecao de dependencia que hoje instanciam `LocalDiskFileStorage`
  diretamente: `app/use_of_collections/presentation/dependencies.py`,
  `app/collection_object_index/presentation/dependencies.py`,
  `app/document_templates/presentation/dependencies.py` e
  `app/public_submission/presentation/dependencies.py` (varios call sites
  neste ultimo);
- testes automatizados para o novo adapter (save/read/delete), cobrindo os
  mesmos casos que `LocalDiskFileStorage` ja cobre hoje.

Recomendacao de configuracao (apos a implementacao acima existir):

- `FILE_STORAGE_BACKEND=local|gcs`;
- `GCS_BUCKET_NAME=${PROJECT_ID}-vitarerum-prod-files`;
- manter `LocalDiskFileStorage` para local/test;
- usar a identidade do servico Cloud Run para acessar o bucket, sem chave JSON.

**(ajustado)** Crie uma service account dedicada para o runtime (service +
job), em vez de depender da service account default do Compute Engine — ela
normalmente tem permissoes bem mais amplas do que o necessario:

```bash
export PROJECT_ID="$(gcloud config get-value project)"
export RUNTIME_SA="vitarerum-run@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create vitarerum-run \
  --display-name="Vitarerum Cloud Run runtime"
```

Crie o bucket e conceda a essa service account somente o necessario para
ler/gravar/apagar objetos (`roles/storage.objectUser`), sem privilegios de
administracao do bucket:

```bash
export REGION="us-east1"
export BUCKET="${PROJECT_ID}-vitarerum-prod-files"

gcloud storage buckets create "gs://$BUCKET" \
  --location="$REGION" \
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$RUNTIME_SA" \
  --role="roles/storage.objectUser"
```

Checkpoint:

```bash
gcloud storage buckets describe "gs://$BUCKET"
gcloud storage buckets get-iam-policy "gs://$BUCKET" \
  --format='table(bindings.role,bindings.members)'
```

Sucesso esperado: o bucket existe e o binding para `$RUNTIME_SA` com
`roles/storage.objectUser` aparece na policy.

Checkpoint da aplicacao:

- upload de documento/proposta salva objeto no bucket;
- download le do bucket;
- delete remove do bucket ou torna a operacao idempotente;
- testes automatizados cobrem save/read/delete do adapter.

Bloqueio: nao habilite fluxos reais de proposta/documento enquanto esse passo
nao estiver concluido.

## Passo 6: Preparar secrets e variaveis

Use Secret Manager para valores sensiveis:

```text
DATABASE_URL
JWT_SECRET
OLLAMA_API_KEY
TURNSTILE_SECRET_KEY
SMTP_PASSWORD
```

Variaveis nao sensiveis:

```text
APP_ENV=production
OLLAMA_BASE_URL=https://ollama.com
CORS_ORIGINS=["https://vitarerum-qmp4ozxwxa-ue.a.run.app"]
PUBLIC_ORIGIN=https://vitarerum-qmp4ozxwxa-ue.a.run.app
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=vitarerum.collections@gmail.com
SMTP_FROM_ADDRESS=vitarerum.collections@gmail.com
SMTP_USE_TLS=true
GCS_BUCKET_NAME=vitarerum-vitarerum-prod-files
FILE_STORAGE_BACKEND=gcs
NARRATIVE_MODEL=gpt-oss:120b-cloud
TRIAGE_MODEL=gpt-oss:120b-cloud
```

Para reduzir erros de shell com aspas e virgulas, coloque essas variaveis em um
arquivo local nao versionado, por exemplo `/tmp/vitarerum-cloudrun.env.yaml`:

```yaml
APP_ENV: production
OLLAMA_BASE_URL: https://ollama.com
CORS_ORIGINS: '["https://vitarerum-qmp4ozxwxa-ue.a.run.app"]'
PUBLIC_ORIGIN: https://vitarerum-qmp4ozxwxa-ue.a.run.app
SMTP_HOST: smtp.gmail.com
SMTP_PORT: "587"
SMTP_USERNAME: vitarerum.collections@gmail.com
SMTP_FROM_ADDRESS: vitarerum.collections@gmail.com
SMTP_USE_TLS: "true"
GCS_BUCKET_NAME: vitarerum-vitarerum-prod-files
FILE_STORAGE_BACKEND: gcs
NARRATIVE_MODEL: gpt-oss:120b-cloud
TRIAGE_MODEL: gpt-oss:120b-cloud
```

Importante: mesmo com UI e API no mesmo origin, `CORS_ORIGINS` precisa ser
definido sem `"*"`, porque `app/config.py` bloqueia startup em producao quando
o default permissivo esta ativo.

Formato recomendado para o Postgres privado atual:

```text
postgresql+asyncpg://vitarerum:<senha>@10.142.0.2:5432/vitarerum
```

Checkpoint:

```bash
gcloud secrets versions access latest --secret DATABASE_URL
gcloud secrets versions access latest --secret OLLAMA_API_KEY
```

Sucesso esperado: os secrets existem e apontam para os valores atuais. Nao
copie senhas para arquivos versionados; `DATABASE_URL` e `SMTP_PASSWORD` devem
ser atualizados com `gcloud secrets versions add`.

**(ajustado)** Criar o secret nao concede acesso a ele. `--set-secrets` no
`gcloud run deploy`/`gcloud run jobs` so funciona em runtime se a service
account do servico/job (`$RUNTIME_SA`, criada no Passo 5) puder ler cada
secret. Sem isso, o deploy manual do Passo 9 costuma emitir um prompt
interativo perguntando se deve conceder acesso — e o Job/servico automatizado
via Cloud Build (Passo 11) nao tem terminal para responder esse prompt, o que
faz a revisao subir mas falhar ao ler os secrets em runtime. Conceda o acesso
explicitamente, uma vez, para cada secret:

```bash
for SECRET in DATABASE_URL JWT_SECRET OLLAMA_API_KEY TURNSTILE_SECRET_KEY SMTP_PASSWORD; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:$RUNTIME_SA" \
    --role="roles/secretmanager.secretAccessor"
done
```

Checkpoint:

```bash
gcloud secrets get-iam-policy DATABASE_URL \
  --format='table(bindings.role,bindings.members)'
```

Sucesso esperado: `roles/secretmanager.secretAccessor` aparece para
`$RUNTIME_SA` em cada um dos cinco secrets.

## Passo 7: Publicar a imagem no Artifact Registry

Crie o repositorio:

```bash
gcloud artifacts repositories create vitarerum \
  --repository-format=docker \
  --location=us-east1
```

Configure a tag:

```bash
export PROJECT_ID="$(gcloud config get-value project)"
export REGION="us-east1"
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/vitarerum/vitarerum:manual"
```

Build e push:

```bash
gcloud auth configure-docker "$REGION-docker.pkg.dev"
docker build -t "$IMAGE" .
docker push "$IMAGE"
```

Checkpoint:

```bash
gcloud artifacts docker images list "$REGION-docker.pkg.dev/$PROJECT_ID/vitarerum"
```

Sucesso esperado: a imagem aparece no Artifact Registry.

## Passo 8: Criar o Cloud Run Job de migracao

Crie um Job dedicado que usa a mesma imagem e sobrescreve o comando para rodar
apenas Alembic.

O Job precisa receber as mesmas env vars/secrets necessarias para importar
`app.config.settings`. Nao basta passar `DATABASE_URL`, porque `alembic/env.py`
importa os settings e as validacoes de producao tambem rodam.

Exemplo:

```bash
gcloud run jobs create vitarerum-migrate \
  --image "$IMAGE" \
  --region "$REGION" \
  --service-account "$RUNTIME_SA" \
  --max-retries 0 \
  --command alembic \
  --args upgrade,head \
  --env-vars-file /tmp/vitarerum-cloudrun.env.yaml \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,OLLAMA_API_KEY=OLLAMA_API_KEY:latest,TURNSTILE_SECRET_KEY=TURNSTILE_SECRET_KEY:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest
```

**(ajustado)** `--service-account "$RUNTIME_SA"` usa a service account
dedicada criada no Passo 5, ja com acesso aos secrets (Passo 6) e ao bucket.
`--max-retries 0` evita que uma migracao com falha real seja re-executada
silenciosamente ate 3 vezes (default do Cloud Run Jobs) antes do erro
aparecer — para `alembic upgrade head` isso so atrasa o diagnostico, sem
ganho de robustez.

Em deploys seguintes, atualize a imagem do Job:

```bash
gcloud run jobs update vitarerum-migrate \
  --image "$IMAGE" \
  --region "$REGION"
```

Execute a migracao:

```bash
gcloud run jobs execute vitarerum-migrate \
  --region "$REGION" \
  --wait
```

Checkpoint:

```bash
gcloud run jobs executions list \
  --job vitarerum-migrate \
  --region "$REGION"
```

Sucesso esperado: a ultima execucao aparece como concluida com sucesso.

Recomendacao: migrations devem ser backward-compatible durante rollout. Se for
remover/renomear coluna usada pela revisao anterior, separe em dois deploys:
primeiro tornar o codigo compativel, depois remover a estrutura antiga.

## Passo 8.1: Bootstrap seguro do primeiro admin

Depois de migrar um banco Postgres vazio, a aplicacao ainda precisa de dados
minimos de identidade: instituicao inicial, grupos base e uma primeira permissao
`SYS_ADMIN`. Sem isso, nao ha como criar usuarios pela API, porque as rotas de
administracao exigem um caller que ja seja `SYS_ADMIN`.

Nao use `vitarerum-api/scripts/seed.sql` em producao: esse arquivo e para
desenvolvimento/smoke local e cria usuarios com senha conhecida.

Implementacao recomendada:

- criar um script idempotente de bootstrap de producao, por exemplo
  `vitarerum-api/scripts/bootstrap_admin.py`;
- ler `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_NAME` e
  `BOOTSTRAP_ADMIN_PASSWORD` de secrets/env vars temporarios;
- gerar o hash da senha com `BcryptPasswordHasher`, nunca com hash fixo
  versionado;
- criar somente instituicao/grupos obrigatorios e o primeiro usuario/permissao
  `SYS_ADMIN`;
- apagar ou rotacionar o secret `BOOTSTRAP_ADMIN_PASSWORD` depois do primeiro
  login e forcar troca de senha.

Checkpoint:

- o script roda uma vez com sucesso contra o Postgres;
- uma segunda execucao nao duplica instituicao, grupos, usuario ou permissao;
- o primeiro admin consegue autenticar;
- o usuario inicial troca a senha antes de uso real.

Bloqueio: nao anuncie o ambiente como pronto enquanto nao houver pelo menos uma
permissao `SYS_ADMIN` de producao criada sem usar senha conhecida.

## Passo 9: Deploy manual do servico Cloud Run

Depois que a migracao passar, publique o servico:

```bash
gcloud run deploy vitarerum \
  --image "$IMAGE" \
  --region "$REGION" \
  --allow-unauthenticated \
  --service-account "$RUNTIME_SA" \
  --env-vars-file /tmp/vitarerum-cloudrun.env.yaml \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,OLLAMA_API_KEY=OLLAMA_API_KEY:latest,TURNSTILE_SECRET_KEY=TURNSTILE_SECRET_KEY:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest
```

Checkpoint:

```bash
SERVICE_URL="$(gcloud run services describe vitarerum --region "$REGION" --format='value(status.url)')"
curl -i "$SERVICE_URL/"
curl -i "$SERVICE_URL/config/environment.json"
curl -i "$SERVICE_URL/api/v1/health"
curl -i "$SERVICE_URL/api/v1/rota-inexistente"
```

Sucesso esperado:

- `/` devolve o HTML do Angular;
- `/config/environment.json` devolve `"api-base-url": "/api/v1"`;
- `/api/v1/health` devolve `{"status":"ok",...}`;
- rota inexistente sob `/api/v1` devolve 404;
- rotas Angular profundas, como `/submit-proposal`, devolvem `index.html`.

## Passo 10: Verificacoes funcionais pos-deploy

Execute estas verificacoes antes de anunciar o ambiente como pronto:

```bash
curl -i "$SERVICE_URL/api/v1/health"
```

`/api/v1/health` e apenas um liveness check da aplicacao: ele confirma que o
processo FastAPI subiu, mas nao testa Postgres, Ollama Cloud nem GCS. Complemente
com smoke tests que exercitem dependencias reais.

No browser:

- abrir a URL do servico;
- autenticar com um usuario valido;
- navegar para dashboard;
- validar uma chamada real da API no DevTools;
- testar uma rota profunda com refresh;
- testar fluxo publico que usa Turnstile;
- fazer pelo menos uma leitura protegida que consulte o Postgres;
- se GCS ja estiver implementado, fazer upload, download e remocao de um
  documento;
- executar uma chamada controlada de IA que use Ollama Cloud, com prompt curto
  e timeout observado.

Logs:

```bash
gcloud run services logs read vitarerum \
  --region "$REGION" \
  --limit 100
```

Sucesso esperado:

- sem erro de startup de settings;
- sem erro de conexao Postgres;
- sem erro de autenticacao Ollama;
- smoke test de banco passa usando dados reais de producao;
- smoke test de GCS passa quando uploads estiverem habilitados;
- smoke test de Ollama passa quando funcionalidades de IA estiverem habilitadas;
- sem 404 para assets Angular;
- sem 500 em downloads/uploads.

## Passo 11: Automatizar com Cloud Build

**(ajustado)** Pre-requisito: este passo assume que o Job `vitarerum-migrate`
ja foi criado manualmente no Passo 8. `gcloud run jobs update` (usado no
pipeline abaixo) falha se o Job ainda nao existir — o pipeline so troca a
imagem de um Job/servico ja existentes, nao os cria do zero.

**(ajustado)** A service account do Cloud Build tambem precisa de permissao
para publicar Jobs e servicos do Cloud Run, e para dar `push` no Artifact
Registry — sem isso, o `gcloud builds submit` do checkpoint deste passo
falha por permissao, mesmo com o Dockerfile e a imagem corretos.

**(ajustado)** Nao monte o e-mail da service account manualmente. Desde a
mudanca de 2024 no Cloud Build, projetos novos podem usar a service account
default do Compute Engine em vez da SA legada
`PROJECT_NUMBER@cloudbuild.gserviceaccount.com` — assumir o formato legado
quebra em projetos criados apos essa mudanca. Descubra a SA real:

```bash
export CLOUDBUILD_SA="$(gcloud builds get-default-service-account \
  --format='value(serviceAccountEmail)' \
  | sed -E 's#^projects/[^/]+/serviceAccounts/##; s#^serviceAccount:##')"
echo "$CLOUDBUILD_SA"
```

Conceda as permissoes a essa SA:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$CLOUDBUILD_SA" \
  --role="roles/run.admin"

gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:$CLOUDBUILD_SA" \
  --role="roles/iam.serviceAccountUser"

gcloud artifacts repositories add-iam-policy-binding vitarerum \
  --location="$REGION" \
  --member="serviceAccount:$CLOUDBUILD_SA" \
  --role="roles/artifactregistry.writer"
```

Checkpoint:

```bash
gcloud projects get-iam-policy "$PROJECT_ID" \
  --flatten="bindings[].members" \
  --filter="bindings.members:$CLOUDBUILD_SA"

gcloud iam service-accounts get-iam-policy "$RUNTIME_SA" \
  --flatten="bindings[].members" \
  --filter="bindings.members:$CLOUDBUILD_SA"

gcloud artifacts repositories get-iam-policy vitarerum \
  --location="$REGION" \
  --flatten="bindings[].members" \
  --filter="bindings.members:$CLOUDBUILD_SA"
```

Sucesso esperado: `roles/run.admin` aparece no primeiro comando,
`roles/iam.serviceAccountUser` no segundo e `roles/artifactregistry.writer`
no terceiro — todos para `$CLOUDBUILD_SA`.

Crie `cloudbuild.yaml` na raiz. Estrutura minima:

```yaml
substitutions:
  _REGION: us-east1
  _SERVICE: vitarerum
  _REPOSITORY: vitarerum
  _IMAGE: vitarerum

steps:
  - name: gcr.io/cloud-builders/docker
    env:
      - DOCKER_BUILDKIT=1
    args:
      - build
      - -t
      - ${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPOSITORY}/${_IMAGE}:$BUILD_ID
      - .

  - name: gcr.io/cloud-builders/docker
    args:
      - push
      - ${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPOSITORY}/${_IMAGE}:$BUILD_ID

  - name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: gcloud
    args:
      - run
      - jobs
      - update
      - vitarerum-migrate
      - --image
      - ${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPOSITORY}/${_IMAGE}:$BUILD_ID
      - --region
      - ${_REGION}

  - name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: gcloud
    args:
      - run
      - jobs
      - execute
      - vitarerum-migrate
      - --region
      - ${_REGION}
      - --wait

  - name: gcr.io/google.com/cloudsdktool/cloud-sdk
    entrypoint: gcloud
    args:
      - run
      - deploy
      - ${_SERVICE}
      - --image
      - ${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPOSITORY}/${_IMAGE}:$BUILD_ID
      - --region
      - ${_REGION}
```

`$BUILD_ID` existe tanto em `gcloud builds submit` manual quanto em triggers.
Se preferir tags por commit em triggers, troque a tag para `$SHORT_SHA` ou
`$COMMIT_SHA` no `cloudbuild.yaml` do trigger; nao use `$COMMIT_SHA` como
default do tutorial, porque em builds manuais ele pode vir vazio.

**(ajustado)** `env: [DOCKER_BUILDKIT=1]` no primeiro step garante que o
`docker build` use o backend BuildKit — o Dockerfile do Passo 4 depende de
`RUN --mount=type=cache` e `RUN --mount=type=bind`, que so existem no
BuildKit. `# syntax=docker/dockerfile:1.7` no topo do Dockerfile seleciona a
versao da sintaxe, mas nao forca o daemon a usar BuildKit; sem a env var, o
build pode cair no builder legado (dependendo da versao do Docker no
executor do Cloud Build) e falhar com "the --mount option requires
BuildKit".

Recomendacao: configure env vars e secrets persistentes diretamente no Cloud Run
service e no Job. Assim o `cloudbuild.yaml` so troca a imagem. Se preferir
declarar tudo no pipeline, mantenha service e Job sincronizados; divergencia de
secrets entre eles e uma fonte comum de falha.

Checkpoint:

```bash
gcloud builds submit --config cloudbuild.yaml
```

Sucesso esperado:

- build da imagem passa;
- push passa;
- Job de migracao passa;
- deploy do servico passa;
- a URL final continua respondendo aos checks do Passo 9.

## Passo 12: Domínio e TLS

Para um primeiro ambiente simples, a URL `*.run.app` e suficiente.

Para dominio customizado, decida antes de divulgar a URL final:

- Cloud Run domain mapping direto: mais simples, mas tem limitacoes e deve ser
  validado na documentacao oficial no momento do deploy:
  https://cloud.google.com/run/docs/mapping-custom-domains
- HTTPS Load Balancer externo com Serverless NEG: recomendado para producao
  quando houver necessidade de CDN, WAF/Cloud Armor, controles de TLS ou
  arquitetura multi-regiao.

Checkpoint:

```bash
curl -I https://vitarerum.example.com/
curl -I https://vitarerum.example.com/api/v1/health
```

Sucesso esperado: certificado valido, redirect/HTTPS correto e API acessivel no
dominio final.

## Passo 13: Criterios finais de aceite

Considere o plano concluido somente quando todos estes pontos forem verdadeiros:

- imagem unica publicada no Artifact Registry;
- Cloud Run service `vitarerum` rodando com a imagem atual;
- Cloud Run Job `vitarerum-migrate` executando `alembic upgrade head` com sucesso;
- bootstrap de producao criou instituicao/grupos base e o primeiro
  `SYS_ADMIN` sem usar `scripts/seed.sql` nem senha conhecida;
- migracao nao roda no startup do container de serving;
- `/` serve Angular;
- `/config/environment.json` usa `/api/v1`;
- `/api/v1/health` responde;
- `/api/v1/*` inexistente devolve 404, nao HTML;
- refresh em rotas internas do Angular funciona;
- `DATABASE_URL` aponta para o Postgres privado com
  `postgresql+asyncpg://vitarerum:<senha>@10.142.0.2:5432/vitarerum`;
- `OLLAMA_BASE_URL` e `OLLAMA_API_KEY` funcionam contra Ollama Cloud;
- `APP_ENV=production` sobe sem defaults inseguros;
- `CORS_ORIGINS` esta explicito e nao contem `"*"`;
- `PUBLIC_ORIGIN` aponta para o dominio final;
- secrets sensiveis estao no Secret Manager;
- uploads reais usam GCS, nao disco local;
- `vitarerum-run` (service account dedicada) tem `roles/secretmanager.secretAccessor`
  em cada secret e `roles/storage.objectUser` no bucket;
- service/Job Cloud Run rodam com `--service-account vitarerum-run@...`, nao com a
  service account default do Compute Engine;
- service account do Cloud Build tem `roles/run.admin` no projeto e
  `roles/iam.serviceAccountUser` sobre `vitarerum-run` (necessario para o Passo 11);
- service account do Cloud Build tem `roles/artifactregistry.writer` no
  repositorio Artifact Registry que recebe a imagem;
- smoke tests reais validam Postgres, GCS (quando uploads estiverem habilitados) e
  Ollama Cloud (quando funcionalidades de IA estiverem habilitadas);
- logs do Cloud Run nao mostram erros de startup, migracao, banco, assets ou IA.

## Ordem recomendada de implementacao

1. Ajustar Angular para `/api/v1` e validar build.
2. Adicionar fallback SPA seguro no FastAPI.
3. Criar Dockerfile unico e `.dockerignore`.
4. Validar imagem local.
5. Implementar adapter GCS para arquivos.
6. Criar secrets, bucket e permissoes.
7. Publicar imagem manualmente.
8. Criar e executar Job de migracao.
9. Executar bootstrap seguro do primeiro admin em producao.
10. Fazer deploy manual do servico.
11. Rodar verificacoes funcionais.
12. Automatizar com Cloud Build.
13. Configurar dominio final.

## Referencias

- Cloud Run container runtime contract:
  https://docs.cloud.google.com/run/docs/container-contract
- Cloud Run secrets:
  https://docs.cloud.google.com/run/docs/configuring/services/secrets
- Cloud Run custom domains:
  https://cloud.google.com/run/docs/mapping-custom-domains
- Mudanca da service account default do Cloud Build (2024):
  https://docs.cloud.google.com/build/docs/cloud-build-service-account-updates
- Deploy no Cloud Run via Cloud Build (permissoes exigidas, incl.
  Artifact Registry Writer):
  https://docs.cloud.google.com/build/docs/deploying-builds/deploy-cloud-run
- Docker `RUN --mount` (recurso exclusivo do BuildKit):
  https://docs.docker.com/reference/dockerfile/#run---mount
- Google Cloud Free Tier / Cloud Storage Always Free:
  https://docs.cloud.google.com/free/docs/free-cloud-features
