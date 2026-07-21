# Tutorial para Remover o Vitarerum da Google Cloud

Este tutorial descreve como remover os recursos criados para o deploy do
Vitarerum na Google Cloud.

Data base do ambiente documentado: 2026-07-21.

Projeto usado no deploy: `vitarerum`.

Regiao usada: `us-east1`.

## Antes de Comecar

Estes comandos sao destrutivos. Revise o projeto ativo antes de apagar qualquer
recurso:

```bash
gcloud config get-value project
```

Sucesso esperado:

```text
vitarerum
```

Liste os recursos principais:

```bash
gcloud run services list --region us-east1
gcloud run jobs list --region us-east1
gcloud artifacts repositories list --location us-east1
gcloud storage buckets list
gcloud secrets list
gcloud iam service-accounts list
```

Checkpoint: confirme que os recursos listados pertencem ao ambiente que voce
quer remover.

## Opcao A: Apagar o Projeto Inteiro

Use esta opcao se o projeto Google Cloud `vitarerum` foi criado apenas para este
deploy e nao contem outros recursos importantes.

### 1. Confirmar o projeto

```bash
gcloud projects describe vitarerum
```

Objetivo: confirmar nome, numero e estado do projeto antes da exclusao.

### 2. Apagar o projeto

```bash
gcloud projects delete vitarerum
```

Objetivo: marcar o projeto inteiro para exclusao.

Resultado esperado: o projeto entra em estado de exclusao. A Google Cloud pode
manter o projeto recuperavel por um periodo antes da remocao definitiva.

### 3. Confirmar estado

```bash
gcloud projects describe vitarerum
```

Sucesso esperado: o projeto aparece em estado de encerramento/exclusao ou deixa
de estar disponivel apos a janela de remocao.

Recomendacao: esta e a forma mais simples de remover tudo, incluindo Cloud Run,
Artifact Registry, Secret Manager, buckets, logs, IAM e APIs do projeto.

## Opcao B: Remover Apenas os Recursos do Vitarerum

Use esta opcao se o projeto `vitarerum` deve continuar existindo.

### 1. Remover o Cloud Run Service

```bash
gcloud run services delete vitarerum \
  --region us-east1
```

Objetivo: remover o endpoint publico da aplicacao.

Checkpoint:

```bash
gcloud run services list --region us-east1
```

Sucesso esperado: `vitarerum` nao aparece mais na lista.

### 2. Remover o Cloud Run Job de migracao

```bash
gcloud run jobs delete vitarerum-migrate \
  --region us-east1
```

Objetivo: remover o Job usado para executar `alembic upgrade head`.

Checkpoint:

```bash
gcloud run jobs list --region us-east1
```

Sucesso esperado: `vitarerum-migrate` nao aparece mais na lista.

### 3. Remover imagens do Artifact Registry

Se o repositorio `vitarerum` em `us-east1` foi usado apenas por este projeto,
remova o repositorio inteiro:

```bash
gcloud artifacts repositories delete vitarerum \
  --location us-east1
```

Objetivo: apagar o repositorio Docker e todas as imagens armazenadas nele.

Checkpoint:

```bash
gcloud artifacts repositories list --location us-east1
```

Sucesso esperado: o repositorio `vitarerum` nao aparece mais.

Se o repositorio for compartilhado com outras aplicacoes, nao apague o
repositorio inteiro. Nesse caso, liste e remova apenas as imagens do Vitarerum:

```bash
gcloud artifacts docker images list \
  us-east1-docker.pkg.dev/vitarerum/vitarerum
```

Depois apague os artefatos especificos que pertencem ao Vitarerum.

### 4. Remover bucket de arquivos da aplicacao

Liste o conteudo antes de apagar:

```bash
gcloud storage ls -r gs://vitarerum-vitarerum-prod-files
```

Remova o bucket e seus objetos:

```bash
gcloud storage rm -r gs://vitarerum-vitarerum-prod-files
```

Objetivo: apagar arquivos persistidos ou preparados para persistencia.

Checkpoint:

```bash
gcloud storage buckets list
```

Sucesso esperado: `gs://vitarerum-vitarerum-prod-files` nao aparece mais.

Observacao: se o backend ainda nao usava GCS em producao, o bucket pode estar
vazio.

### 5. Remover bucket de fontes do Cloud Build, se nao for mais necessario

Durante o deploy foi usado o bucket:

```text
gs://vitarerum_cloudbuild
```

Liste o conteudo:

```bash
gcloud storage ls -r gs://vitarerum_cloudbuild
```

Se o projeto nao usara mais Cloud Build, remova:

```bash
gcloud storage rm -r gs://vitarerum_cloudbuild
```

Objetivo: apagar pacotes fonte enviados por `gcloud builds submit`.

Checkpoint:

```bash
gcloud storage buckets list
```

Sucesso esperado: `gs://vitarerum_cloudbuild` nao aparece mais.

### 6. Remover secrets

Secrets criados para o deploy:

- `DATABASE_URL`;
- `JWT_SECRET`;
- `OLLAMA_API_KEY`;
- `TURNSTILE_SECRET_KEY`;
- `SMTP_PASSWORD`.

Comandos:

```bash
gcloud secrets delete DATABASE_URL
gcloud secrets delete JWT_SECRET
gcloud secrets delete OLLAMA_API_KEY
gcloud secrets delete TURNSTILE_SECRET_KEY
gcloud secrets delete SMTP_PASSWORD
```

Objetivo: apagar os valores sensiveis guardados no Secret Manager.

Checkpoint:

```bash
gcloud secrets list
```

Sucesso esperado: os cinco secrets nao aparecem mais.

Recomendacao: alem de apagar os secrets na Google Cloud, revogue ou rotacione
as credenciais nos provedores externos quando aplicavel:

- Neon Postgres;
- Ollama Cloud;
- Cloudflare Turnstile;
- provedor SMTP.

### 7. Remover bindings IAM do Cloud Build

Service account usada pelo Cloud Build neste projeto:

```text
824725454969-compute@developer.gserviceaccount.com
```

Remova permissoes concedidas durante a preparacao:

```bash
gcloud projects remove-iam-policy-binding vitarerum \
  --member=serviceAccount:824725454969-compute@developer.gserviceaccount.com \
  --role=roles/run.admin

gcloud projects remove-iam-policy-binding vitarerum \
  --member=serviceAccount:824725454969-compute@developer.gserviceaccount.com \
  --role=roles/logging.logWriter
```

Se o repositorio Artifact Registry ainda existir:

```bash
gcloud artifacts repositories remove-iam-policy-binding vitarerum \
  --location=us-east1 \
  --member=serviceAccount:824725454969-compute@developer.gserviceaccount.com \
  --role=roles/artifactregistry.writer
```

Se o bucket `gs://vitarerum_cloudbuild` ainda existir:

```bash
gcloud storage buckets remove-iam-policy-binding gs://vitarerum_cloudbuild \
  --member=serviceAccount:824725454969-compute@developer.gserviceaccount.com \
  --role=roles/storage.objectViewer
```

Objetivo: retirar permissoes adicionadas para o pipeline.

Checkpoint:

```bash
gcloud projects get-iam-policy vitarerum \
  --flatten='bindings[].members' \
  --filter='bindings.members:824725454969-compute@developer.gserviceaccount.com' \
  --format='table(bindings.role)'
```

Sucesso esperado: as roles especificas acima nao aparecem mais.

### 8. Remover permissao de uso da service account de runtime

```bash
gcloud iam service-accounts remove-iam-policy-binding \
  vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --member=serviceAccount:824725454969-compute@developer.gserviceaccount.com \
  --role=roles/iam.serviceAccountUser
```

Objetivo: impedir que o Cloud Build volte a usar a service account de runtime.

Checkpoint:

```bash
gcloud iam service-accounts get-iam-policy \
  vitarerum-run@vitarerum.iam.gserviceaccount.com
```

Sucesso esperado: o membro
`824725454969-compute@developer.gserviceaccount.com` nao aparece com
`roles/iam.serviceAccountUser`.

### 9. Remover service account de runtime

```bash
gcloud iam service-accounts delete \
  vitarerum-run@vitarerum.iam.gserviceaccount.com
```

Objetivo: apagar a identidade usada pelo Cloud Run em runtime.

Checkpoint:

```bash
gcloud iam service-accounts list
```

Sucesso esperado:
`vitarerum-run@vitarerum.iam.gserviceaccount.com` nao aparece mais.

### 10. Desabilitar APIs opcionais

Se o projeto nao sera mais usado para Cloud Run ou builds, desabilite as APIs:

```bash
gcloud services disable run.googleapis.com
gcloud services disable cloudbuild.googleapis.com
gcloud services disable artifactregistry.googleapis.com
gcloud services disable secretmanager.googleapis.com
gcloud services disable storage.googleapis.com
```

Objetivo: reduzir superficie ativa do projeto.

Checkpoint:

```bash
gcloud services list --enabled
```

Sucesso esperado: as APIs acima nao aparecem mais, desde que nenhum recurso
remanescente dependa delas.

## 3. Validacao Final

### Verificar Cloud Run

```bash
gcloud run services list --region us-east1
gcloud run jobs list --region us-east1
```

Sucesso esperado: nao ha `vitarerum` nem `vitarerum-migrate`.

### Verificar Artifact Registry

```bash
gcloud artifacts repositories list --location us-east1
```

Sucesso esperado: o repositorio `vitarerum` nao aparece, se ele foi removido.

### Verificar buckets

```bash
gcloud storage buckets list
```

Sucesso esperado: os buckets `gs://vitarerum-vitarerum-prod-files` e
`gs://vitarerum_cloudbuild` nao aparecem, se foram removidos.

### Verificar secrets

```bash
gcloud secrets list
```

Sucesso esperado: os secrets do Vitarerum nao aparecem.

### Verificar endpoint publico

```bash
curl -i https://vitarerum-qmp4ozxwxa-ue.a.run.app/
```

Sucesso esperado: o endpoint nao responde mais como aplicacao ativa. O retorno
pode ser `404`, `403`, `SERVFAIL`, erro de DNS ou outro erro de servico
indisponivel, dependendo do tempo de propagacao.

## 4. O Que Nao E Removido Pela Google Cloud

Os recursos externos precisam ser tratados nos respectivos provedores:

- banco Neon Postgres;
- credencial ou projeto da Ollama Cloud;
- site e secret do Cloudflare Turnstile;
- senha de app ou credencial SMTP;
- dominio proprio, se algum for configurado depois;
- repositorio Git local ou remoto.

Recomendacao: depois do teardown na Google Cloud, rotacione credenciais externas
que foram usadas no deploy.

## 5. Checklist de Conclusao

- Projeto inteiro apagado, ou todos os recursos granulares removidos.
- Cloud Run service removido.
- Cloud Run Job removido.
- Imagens ou repositorio Artifact Registry removidos.
- Buckets GCS removidos ou esvaziados.
- Secrets apagados.
- Service account `vitarerum-run` apagada.
- IAM extra do Cloud Build removido.
- APIs desabilitadas, se o projeto continuar existindo e nao precisar delas.
- Credenciais externas rotacionadas ou revogadas.

