# Comandos Executados no Deploy Google Cloud

Este documento registra os comandos usados para preparar, publicar e validar o
deploy unico de `vitarerum-api` + `vitarerum-ui` no Google Cloud Run.

Data da execucao: 2026-07-21.

Regra de seguranca: valores sensiveis nao sao repetidos aqui. Os comandos que
criaram secrets estao documentados com placeholders.

## Resultado Final

- Projeto Google Cloud usado: `vitarerum`.
- Regiao usada: `us-east1`.
- Service account de runtime: `vitarerum-run@vitarerum.iam.gserviceaccount.com`.
- Repositorio Artifact Registry: `us-east1-docker.pkg.dev/vitarerum/vitarerum`.
- Imagem final publicada pelo Cloud Build:
  `us-east1-docker.pkg.dev/vitarerum/vitarerum/vitarerum:5a5f87a3-8b8c-46a4-bd8e-a68b5e09b160`.
- Cloud Run service: `vitarerum`.
- Revisao final ativa: `vitarerum-00004-v7w`.
- URL canonico do servico:
  `https://vitarerum-qmp4ozxwxa-ue.a.run.app`.
- Cloud Run Job de migracao: `vitarerum-migrate`.
- Ultima execucao do pipeline Cloud Build: `SUCCESS`.

## 1. Inspecao e Validacao Local

### Verificar projeto e arquivos

```bash
rg --files
sed -n '1,80p' docs/cloud/README.md
```

Objetivo: entender a estrutura do repositorio, revisar o plano existente e
identificar lacunas de deploy.

Resultado: confirmada a estrutura com backend FastAPI em `vitarerum-api`,
frontend Angular em `vitarerum-ui` e plano em `docs/cloud/README.md`.

### Validar import da API

```bash
cd vitarerum-api
uv run python -c "from app.main import app; print(app.title)"
```

Objetivo: confirmar que a aplicacao FastAPI carrega localmente.

Resultado: retornou `vitarerum-api`.

### Build do Angular

```bash
cd vitarerum-ui
npm run build
```

Objetivo: gerar o bundle estatico que sera servido pelo FastAPI dentro do mesmo
container.

Resultado: build concluido com sucesso. O Angular reportou avisos de budget:

- bundle inicial acima do limite configurado;
- alguns SCSS de componentes acima do limite configurado.

Esses avisos nao bloquearam o deploy.

### Copiar build Angular para o backend para teste local

```bash
mkdir -p vitarerum-api/static
cp -R vitarerum-ui/dist/vitarerum-ui/browser/. vitarerum-api/static/
```

Objetivo: simular localmente o layout final do container, no qual o FastAPI
serve os arquivos estaticos do Angular a partir de `/app/static`.

Resultado: `vitarerum-api/static/index.html` passou a existir.

### Validar fallback SPA e API localmente

```bash
cd vitarerum-api
uv run python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
for path in ["/", "/config/environment.json", "/api/v1/health", "/api/v1/rota-inexistente", "/api/v1"]:
    response = client.get(path)
    print(path, response.status_code, response.headers.get("content-type"))
PY
```

Objetivo: verificar que:

- `/` serve a SPA;
- `/config/environment.json` serve a configuracao do Angular;
- `/api/v1/health` continua roteado para a API;
- rotas inexistentes sob `/api/v1` retornam JSON 404, nao `index.html`.

Resultado:

- `/` -> `200`, `text/html`;
- `/config/environment.json` -> `200`, `application/json`;
- `/api/v1/health` -> `200`, `application/json`;
- `/api/v1/rota-inexistente` -> `404`, `application/json`;
- `/api/v1` -> `404`, `application/json`.

### Verificar whitespace nos diffs

```bash
git diff --check
```

Objetivo: confirmar que as alteracoes locais nao introduziram erros triviais de
espacamento.

Resultado: sem erros.

## 2. Arquivos Criados ou Ajustados no Repositorio

### Arquivos de build e deploy

```bash
Dockerfile
.dockerignore
.gcloudignore
cloudbuild.yaml
cloudbuild.image.yaml
docs/cloud/vitarerum-cloudrun.env.example.yaml
```

Objetivo:

- construir o Angular em um stage Node;
- construir o backend Python com `uv`;
- copiar o build Angular para `/app/static`;
- publicar uma imagem unica no Artifact Registry;
- executar migracoes via Cloud Run Job;
- fazer deploy do Cloud Run service.

Resultado: imagem unica gerada e publicada com sucesso.

### Arquivos de aplicacao alterados

```bash
vitarerum-api/app/main.py
vitarerum-ui/src/config/environment.json
.gitignore
docs/cloud/README.md
```

Objetivo:

- adicionar fallback SPA sem capturar rotas `/api/v1`;
- usar API relativa `"/api/v1"` no Angular;
- ignorar `vitarerum-api/static/`;
- atualizar o tutorial de deploy.

Resultado: Cloud Run serve UI e API no mesmo dominio.

## 3. Configuracao Inicial do Google Cloud

### Confirmar projeto ativo

```bash
gcloud config get-value project
```

Objetivo: confirmar que o projeto alvo era `vitarerum`.

Resultado: projeto confirmado como `vitarerum`.

### Habilitar APIs necessarias

```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable storage.googleapis.com
```

Objetivo: habilitar os servicos necessarios para Cloud Run, Cloud Build,
Artifact Registry, Secret Manager e Cloud Storage.

Resultado: APIs habilitadas ou ja disponiveis.

### Confirmar servicos habilitados

```bash
gcloud services list --enabled
```

Objetivo: conferir se os servicos esperados estavam ativos.

Resultado: APIs necessarias confirmadas.

## 4. Escolha da Regiao

### Confirmacao operacional

```bash
gcloud run regions list
```

Objetivo: confirmar disponibilidade de Cloud Run na regiao pretendida.

Resultado: `us-east1` disponivel.

Decisao: usar `us-east1`. Motivo principal: o Always Free do Cloud Storage
inclui 5 GB-mes de storage regional apenas em `us-east1`, `us-west1` e
`us-central1`, considerando uso agregado entre essas regioes.

## 5. Service Account, Bucket e Artifact Registry

### Criar service account de runtime

```bash
gcloud iam service-accounts create vitarerum-run \
  --display-name "Vitarerum Cloud Run runtime"
```

Objetivo: isolar as permissoes de runtime do Cloud Run em uma conta dedicada.

Resultado: service account criada:
`vitarerum-run@vitarerum.iam.gserviceaccount.com`.

### Criar repositorio Artifact Registry

```bash
gcloud artifacts repositories create vitarerum \
  --repository-format=docker \
  --location=us-east1 \
  --description="Vitarerum container images"
```

Objetivo: armazenar imagens Docker em `us-east1`.

Resultado: repositorio criado.

### Criar bucket GCS

```bash
gcloud storage buckets create gs://vitarerum-vitarerum-prod-files \
  --location=us-east1 \
  --uniform-bucket-level-access
```

Objetivo: preparar storage regional para arquivos persistentes.

Resultado: bucket criado em `us-east1`.

Observacao: a infraestrutura foi criada, mas o backend ainda nao implementa o
adaptador GCS; uploads reais ainda nao estao production-safe em Cloud Run.

### Conceder permissao de escrita no bucket ao runtime

```bash
gcloud storage buckets add-iam-policy-binding gs://vitarerum-vitarerum-prod-files \
  --member=serviceAccount:vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --role=roles/storage.objectUser
```

Objetivo: permitir que a aplicacao grave objetos no bucket quando o adaptador
GCS for implementado.

Resultado: binding aplicado.

## 6. Secrets

### Criar secrets

```bash
gcloud secrets create DATABASE_URL --replication-policy=automatic
gcloud secrets create JWT_SECRET --replication-policy=automatic
gcloud secrets create OLLAMA_API_KEY --replication-policy=automatic
gcloud secrets create TURNSTILE_SECRET_KEY --replication-policy=automatic
gcloud secrets create SMTP_PASSWORD --replication-policy=automatic
```

Objetivo: criar os containers logicos dos secrets no Secret Manager.

Resultado: cinco secrets criados.

### Adicionar versoes aos secrets

```bash
printf '%s' '<DATABASE_URL>' | gcloud secrets versions add DATABASE_URL --data-file=-
printf '%s' '<JWT_SECRET>' | gcloud secrets versions add JWT_SECRET --data-file=-
printf '%s' '<OLLAMA_API_KEY>' | gcloud secrets versions add OLLAMA_API_KEY --data-file=-
printf '%s' '<TURNSTILE_SECRET_KEY>' | gcloud secrets versions add TURNSTILE_SECRET_KEY --data-file=-
printf '%s' '<SMTP_PASSWORD>' | gcloud secrets versions add SMTP_PASSWORD --data-file=-
```

Objetivo: inserir os valores sensiveis informados pelo operador.

Resultado: uma versao criada para cada secret.

### Conceder acesso aos secrets para o runtime

```bash
gcloud secrets add-iam-policy-binding DATABASE_URL \
  --member=serviceAccount:vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding JWT_SECRET \
  --member=serviceAccount:vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding OLLAMA_API_KEY \
  --member=serviceAccount:vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding TURNSTILE_SECRET_KEY \
  --member=serviceAccount:vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

gcloud secrets add-iam-policy-binding SMTP_PASSWORD \
  --member=serviceAccount:vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor
```

Objetivo: permitir que o Cloud Run leia os secrets em runtime.

Resultado: bindings aplicados aos cinco secrets.

## 7. Permissoes do Cloud Build

### Identificar service account usada pelo Cloud Build

```bash
gcloud projects describe vitarerum --format='value(projectNumber)'
```

Objetivo: obter o numero do projeto para montar o email da service account.

Resultado: numero do projeto `824725454969`; service account usada:
`824725454969-compute@developer.gserviceaccount.com`.

### Permissoes para administrar Cloud Run

```bash
gcloud projects add-iam-policy-binding vitarerum \
  --member=serviceAccount:824725454969-compute@developer.gserviceaccount.com \
  --role=roles/run.admin
```

Objetivo: permitir que o Cloud Build atualize Jobs e Services do Cloud Run.

Resultado: binding aplicado.

### Permissao para usar a service account de runtime

```bash
gcloud iam service-accounts add-iam-policy-binding \
  vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --member=serviceAccount:824725454969-compute@developer.gserviceaccount.com \
  --role=roles/iam.serviceAccountUser
```

Objetivo: permitir que o Cloud Build faca deploy usando
`vitarerum-run@vitarerum.iam.gserviceaccount.com`.

Resultado: binding aplicado.

### Permissao de escrita no Artifact Registry

```bash
gcloud artifacts repositories add-iam-policy-binding vitarerum \
  --location=us-east1 \
  --member=serviceAccount:824725454969-compute@developer.gserviceaccount.com \
  --role=roles/artifactregistry.writer
```

Objetivo: permitir push de imagens para o repositorio Docker.

Resultado: binding aplicado.

### Permissao de logs para Cloud Build

```bash
gcloud projects add-iam-policy-binding vitarerum \
  --member=serviceAccount:824725454969-compute@developer.gserviceaccount.com \
  --role=roles/logging.logWriter
```

Objetivo: corrigir a falha inicial do Cloud Build ao escrever logs.

Resultado: binding aplicado.

### Permissao de leitura no bucket de fontes do Cloud Build

```bash
gcloud storage buckets add-iam-policy-binding gs://vitarerum_cloudbuild \
  --member=serviceAccount:824725454969-compute@developer.gserviceaccount.com \
  --role=roles/storage.objectViewer
```

Objetivo: corrigir falha de leitura do pacote fonte enviado pelo
`gcloud builds submit`.

Resultado: binding aplicado.

## 8. Arquivo de Variaveis Nao Sensiveis

### Criar arquivo local temporario

```bash
cat >/tmp/vitarerum-cloudrun.env.yaml <<'YAML'
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
YAML
```

Objetivo: separar env vars nao sensiveis dos secrets.

Resultado: arquivo temporario criado e usado nos deploys.

Observacao: este arquivo fica em `/tmp` e nao deve conter secrets.

## 9. Primeiro Build Manual

### Tentativa inicial com `--tag`

```bash
gcloud builds submit \
  --tag us-east1-docker.pkg.dev/vitarerum/vitarerum/vitarerum:manual \
  .
```

Objetivo: fazer build e push direto da imagem.

Resultado: falhou porque esse modo nao usou o `cloudbuild.yaml` e o Docker
BuildKit nao estava ativo. O Dockerfile usa `RUN --mount`, que exige BuildKit.

Correcao: criar `cloudbuild.image.yaml` com `DOCKER_BUILDKIT=1`.

### Build inicial com config dedicada

```bash
gcloud builds submit --config cloudbuild.image.yaml .
```

Objetivo: construir e publicar a imagem inicial `manual` usando BuildKit.

Resultado: sucesso. Imagem publicada:
`us-east1-docker.pkg.dev/vitarerum/vitarerum/vitarerum:manual`.

Digest observado:
`sha256:d0947bc5dc646ae932c1b44d22ded861177cb137c48eae999103732c00502564`.

## 10. Cloud Run Job de Migracao

### Criar Job

```bash
gcloud run jobs create vitarerum-migrate \
  --image us-east1-docker.pkg.dev/vitarerum/vitarerum/vitarerum:manual \
  --region us-east1 \
  --service-account vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --max-retries 0 \
  --command alembic \
  --args upgrade,head \
  --env-vars-file /tmp/vitarerum-cloudrun.env.yaml \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,OLLAMA_API_KEY=OLLAMA_API_KEY:latest,TURNSTILE_SECRET_KEY=TURNSTILE_SECRET_KEY:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest
```

Objetivo: criar um Job separado para executar migracoes Alembic contra o Neon
Postgres.

Resultado: Job `vitarerum-migrate` criado.

### Executar Job

```bash
gcloud run jobs execute vitarerum-migrate \
  --region us-east1 \
  --wait
```

Objetivo: aplicar migracoes no banco externo.

Resultado: execucao `vitarerum-migrate-dz9kz` concluida com sucesso.

## 11. Primeiro Deploy do Cloud Run Service

```bash
gcloud run deploy vitarerum \
  --image us-east1-docker.pkg.dev/vitarerum/vitarerum/vitarerum:manual \
  --region us-east1 \
  --allow-unauthenticated \
  --service-account vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --env-vars-file /tmp/vitarerum-cloudrun.env.yaml \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,OLLAMA_API_KEY=OLLAMA_API_KEY:latest,TURNSTILE_SECRET_KEY=TURNSTILE_SECRET_KEY:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest
```

Objetivo: publicar o container unico no Cloud Run.

Resultado:

- revisao inicial: `vitarerum-00001-b5x`;
- URL retornado: `https://vitarerum-824725454969.us-east1.run.app`.

## 12. Ajuste de URL Publico e CORS

### Atualizar env vars apos conhecer o URL

```bash
gcloud run services update vitarerum \
  --region us-east1 \
  --env-vars-file /tmp/vitarerum-cloudrun.env.yaml
```

Objetivo: trocar placeholders de `PUBLIC_ORIGIN` e `CORS_ORIGINS` pelo URL
real do Cloud Run.

Resultado:

- revisao `vitarerum-00002-lx6` criada inicialmente;
- depois, ao alinhar ao URL canonico do `gcloud describe`, revisao
  `vitarerum-00004-v7w` criada e servindo 100% do trafego.

### Confirmar URL, revisao e service account

```bash
gcloud run services describe vitarerum \
  --region us-east1 \
  --format='value(status.latestReadyRevisionName,status.url,spec.template.spec.serviceAccountName)'
```

Objetivo: confirmar o estado ativo do servico.

Resultado:

```text
vitarerum-00003-hr4  https://vitarerum-qmp4ozxwxa-ue.a.run.app  vitarerum-run@vitarerum.iam.gserviceaccount.com
```

Depois do ultimo update de env vars:

```bash
gcloud run services describe vitarerum \
  --region us-east1 \
  --format='value(status.latestReadyRevisionName,status.url)'
```

Resultado:

```text
vitarerum-00004-v7w  https://vitarerum-qmp4ozxwxa-ue.a.run.app
```

## 13. Pipeline Cloud Build Completo

```bash
gcloud builds submit --config cloudbuild.yaml .
```

Objetivo: validar o fluxo completo automatizado:

1. build da imagem;
2. push para Artifact Registry;
3. update do Cloud Run Job;
4. execucao das migracoes;
5. deploy do Cloud Run service.

Resultado:

```text
ID: 5a5f87a3-8b8c-46a4-bd8e-a68b5e09b160
STATUS: SUCCESS
```

Imagem gerada:

```text
us-east1-docker.pkg.dev/vitarerum/vitarerum/vitarerum:5a5f87a3-8b8c-46a4-bd8e-a68b5e09b160
```

Digest observado:

```text
sha256:102241cbcaf0aac3501929f6446c02fdd5c98d7b3b9f012af5eaa7dca664f9f2
```

Execucao de migracao no pipeline:

```text
vitarerum-migrate-zqd9n
```

Revisao publicada pelo pipeline:

```text
vitarerum-00003-hr4
```

## 14. Verificacao dos Secrets Montados

```bash
gcloud run services describe vitarerum \
  --region us-east1 \
  --format='flattened(spec.template.spec.containers[0].env)'
```

Objetivo: confirmar que os env vars e secrets estavam montados no Cloud Run sem
imprimir valores sensiveis.

Resultado:

- `DATABASE_URL` vindo de Secret Manager;
- `JWT_SECRET` vindo de Secret Manager;
- `OLLAMA_API_KEY` vindo de Secret Manager;
- `TURNSTILE_SECRET_KEY` vindo de Secret Manager;
- `SMTP_PASSWORD` vindo de Secret Manager;
- `APP_ENV=production`;
- `OLLAMA_BASE_URL=https://ollama.com`;
- `PUBLIC_ORIGIN=https://vitarerum-qmp4ozxwxa-ue.a.run.app`;
- `CORS_ORIGINS=["https://vitarerum-qmp4ozxwxa-ue.a.run.app"]`;
- SMTP configurado;
- `GCS_BUCKET_NAME=vitarerum-vitarerum-prod-files`;
- `FILE_STORAGE_BACKEND=gcs`.

## 15. Verificacoes HTTP Publicas

### SPA

```bash
curl -s -i https://vitarerum-qmp4ozxwxa-ue.a.run.app/
```

Objetivo: verificar se o Angular e servido pelo Cloud Run.

Resultado: `HTTP/2 200`, `content-type: text/html`.

### Configuracao do Angular

```bash
curl -s -i https://vitarerum-qmp4ozxwxa-ue.a.run.app/config/environment.json
```

Objetivo: confirmar que o frontend recebe configuracao de producao.

Resultado: `HTTP/2 200`, `content-type: application/json`, com
`api-base-url` apontando para `/api/v1`.

### Health check da API

```bash
curl -s -i https://vitarerum-qmp4ozxwxa-ue.a.run.app/api/v1/health
```

Objetivo: confirmar que a API responde dentro do mesmo dominio.

Resultado:

```json
{"status":"ok","application":"vitarerum-api"}
```

### 404 de API preservado

```bash
curl -s -i https://vitarerum-qmp4ozxwxa-ue.a.run.app/api/v1/rota-inexistente
```

Objetivo: garantir que rotas inexistentes de API nao sejam tratadas como rotas
da SPA.

Resultado: `HTTP/2 404`, `content-type: application/json`.

## 16. Estado Local ao Final

```bash
git status --short
```

Resultado observado:

```text
A  .dockerignore
A  .gcloudignore
 M .gitignore
A  Dockerfile
 M README.md
A  cloudbuild.image.yaml
AM cloudbuild.yaml
AM docs/cloud/README.md
A  docs/cloud/vitarerum-cloudrun.env.example.yaml
 M vitarerum-api/app/main.py
 M vitarerum-ui/package-lock.json
 M vitarerum-ui/src/config/environment.json
```

Observacao: `README.md` e `vitarerum-ui/package-lock.json` ja tinham alteracoes
locais no worktree e nao foram revertidos.

## 17. Lacunas Restantes

- Nao foi executado smoke test autenticado, porque ainda nao existe bootstrap
  seguro de usuario admin para producao.
- O bucket GCS e as permissoes foram criados, mas o backend ainda precisa de um
  adaptador real de storage GCS. Enquanto isso, uploads em Cloud Run continuam
  usando filesystem efemero do container.
- Os secrets devem ser rotacionados depois, pois seus valores foram informados
  manualmente durante a sessao.
- Os avisos de budget do Angular nao impedem o deploy, mas devem ser tratados
  antes de considerar o frontend otimizado para producao.

