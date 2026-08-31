# Subir o Vitarerum numa conta Google Cloud nova

Recria o ambiente de producao inteiro num projeto novo, mantendo a regiao
(`us-east1`) e o desenho do banco de dados (PostgreSQL auto-hospedado numa VM
`e2-micro`, alcancado pelo Cloud Run por egress VPC direto), e acrescentando o
sweep agendado de retorno cientifico, que o ambiente atual nunca chegou a ter.

O banco comeca vazio: nenhum dado e' migrado do projeto antigo.

## O que existe aqui

| Arquivo | Papel |
|---|---|
| `deploy/env.example` | Modelo do `deploy/.env` — copie e preencha |
| `deploy/provision.sh` | Provisiona tudo, de ponta a ponta, de forma idempotente |
| `deploy/postgres-setup.sh` | Roda dentro da VM; instala e configura o PostgreSQL |

`deploy/.env` e' ignorado pelo git (`.gitignore: .env`) e pelo Cloud Build
(`.gcloudignore: **/.env`).

## Antes de comecar

1. **Autentique-se com a conta nova.** O script nao faz login por voce:

   ```
   gcloud auth login
   ```

   A conta antiga **continua autenticada ao lado** — nao a remova. O
   `provision.sh` a usa (via `SOURCE_ACCOUNT`) so' para ler os segredos de
   producao do projeto antigo; a conta ativa, que cria tudo, e' a nova. Sem
   isso a heranca falharia calada e o `TURNSTILE_SECRET_KEY`, que so' existe no
   Secret Manager de producao, apareceria como `NAO ENCONTRADA`.

2. **Tenha uma conta de faturamento ativa.** A `e2-micro` em `us-east1` cabe no
   nivel gratuito, mas Artifact Registry e Cloud Build nao. Descubra o id com
   `gcloud billing accounts list` e coloque em `BILLING_ACCOUNT_ID`.

3. **Preencha o `deploy/.env`:**

   ```
   cp deploy/env.example deploy/.env && $EDITOR deploy/.env
   ```

   Um unico valor precisa ser preenchido a mao:

   | Variavel | Por que |
   |---|---|
   | `INSTITUTION_NAME` | Nome da instituicao, publicado como `dcterms:creator` dos grafos CIDOC-CRM. E' posterior ao ultimo deploy, entao nao existe nem em producao nem no `.env` local — la' ha' so' a linha comentada `# INSTITUTION_NAME=Museum`, e `Museum` e' justamente o valor que o `config.py` recusa |

   **Todo o resto e' herdado do ambiente atual.** Cada segredo e' resolvido
   nesta ordem:

   1. `deploy/.env`, se voce preencher explicitamente
   2. **Secret Manager do projeto de producao** (`SOURCE_PROJECT`)
   3. `vitarerum-api/.env`, so' para o que producao nao tiver

   Na pratica isso significa:

   | Segredo | De onde vem |
   |---|---|
   | `JWT_SECRET`, `FILE_ENCRYPTION_KEY`, `OLLAMA_API_KEY`, `SMTP_PASSWORD`, `TURNSTILE_SECRET_KEY` | producao |
   | `DB_FIELD_ENCRYPTION_KEY` | `vitarerum-api/.env` — producao nao tem, por ser posterior ao ultimo deploy |
   | `DATABASE_URL`, `DB_PASSWORD` | **gerados**, nunca herdados |

   `DATABASE_URL` fica de fora de proposito: o valor de producao aponta para o
   IP interno e a senha da VM antiga, que nao existem no projeto novo. O script
   sempre o remonta a partir da VM recem-criada.

   O preflight imprime a procedencia de cada segredo — tamanho e origem, nunca
   o valor — antes de criar recurso algum, e valida ali mesmo o que o
   `config.py` exigiria no startup: `JWT_SECRET` com pelo menos 32 bytes e as
   duas chaves de cifra decodificando para exatamente 32.

## Rodar

```
./deploy/provision.sh
```

Leva de 15 a 25 minutos, quase todo o tempo no primeiro build da imagem (o
Dockerfile compila a UI Angular e resolve as dependencias Python do zero).

O script e' idempotente: cada passo checa se o recurso ja' existe antes de
criar, entao depois de uma falha basta rodar de novo. Para repetir um passo
isolado:

```
STEP=scheduler ./deploy/provision.sh
```

Passos, em ordem: `project` `apis` `registry` `network` `vm` `postgres`
`serviceaccounts` `secrets` `bucket` `buildaccess` `image` `migrate` `seed`
`service` `sweepjob` `scheduler` `origins` `summary`.

## O que fica provisionado

- **Projeto** com 11 APIs habilitadas. `sqladmin` fica de fora de proposito: o
  banco e' a VM, nao Cloud SQL. `cloudscheduler` entra — e' nova.
- **VM `postgres-gratis`** (`e2-micro`, `us-east1-d`, Ubuntu 24.04 minimal,
  disco de 30 GB) com PostgreSQL, swap de 2 GB e `shared_buffers` ajustado para
  1 GB de RAM. O IP externo e' **estatico** (`postgres-gratis-ip`): o efemero
  muda a cada parada da VM e quebraria um tunel SSH ja' configurado. Anexado a
  uma instancia em execucao, o endereco reservado nao tem custo.
- **Firewall `permitir-postgres-interno`**: `tcp:5432` apenas da sub-rede
  interna, que e' de onde o Cloud Run sai.
- **Tres contas de servico**: `vitarerum-run` (runtime, sem papel algum no
  projeto — so' permissoes por recurso), `vitarerum-build` (deploy) e
  `vitarerum-scheduler` (dispara o sweep).
- **Oito segredos** no Secret Manager, acessiveis so' pela `vitarerum-run`.
- **Servico Cloud Run** `vitarerum`: 1 vCPU / 512 MiB, concorrencia 80,
  `max-instances` 20, egress VPC direto, publico (`allUsers`/`run.invoker`).
- **Job `vitarerum-migrate`**: `alembic upgrade head`.
- **Job `vitarerum-scientific-return`** + **Cloud Scheduler**.

## Duas coisas que mudaram em relacao ao ambiente atual

### Duas configuracoes novas passaram a ser obrigatorias

O deploy em producao hoje e' de 07/08/2026. Depois dele, dois commits tornaram
obrigatorias, fora de `local`/`test`, configuracoes que a revisao no ar nao tem:

- `DB_FIELD_ENCRYPTION_KEY` — commit `70635eb`, *Implement database field
  encryption phase 1*. Base64 de exatamente 32 bytes.
- `INSTITUTION_NAME` — commit `fb0fba8`, *capture the producing institution on
  the visit snapshot*. Nao pode ser `Museum`.

`Settings.validate_non_local_security` recusa subir sem elas, e o container
morre no startup. O provisionamento ja' cria as duas; a nota fica registrada
porque **o projeto antigo tambem vai precisar delas no proximo deploy**.

### O job do sweep tinha de ser criado antes do primeiro build

O `cloudbuild.yaml` faz `gcloud run jobs update vitarerum-scientific-return`, o
que exige o job ja' existente. Por isso o bootstrap usa o `cloudbuild.image.yaml`
(que so' constroi e publica), cria os dois jobs a partir dessa imagem, e so'
entao os deploys seguintes passam a usar o `cloudbuild.yaml` completo.

O `--task-timeout` do job e' `1800s`, casando com
`scientific_return_platform_window_seconds`. Nao mexa num sem mexer no outro:
`config.py` valida que a janela da plataforma comporta a fatia do worker
(`1500s`) mais a chamada externa mais longa (`300s`), e recusa subir se nao
couber.

## Depois do provisionamento

1. **Crie o administrador inicial.** A API exige um `X-Permission-Id` apontando
   para uma linha existente em `identity_permissions`, e nao ha' endpoint de
   bootstrap. O `scripts/seed.sql` resolve isso, mas e' um seed de
   desenvolvimento: cria quatro usuarios cuja senha e' literalmente `password`.
   Por isso o passo `seed` e' pulado por padrao. Para aplica-lo mesmo assim:

   ```
   APPLY_DEV_SEED=yes STEP=seed ./deploy/provision.sh
   ```

   Troque as senhas antes de divulgar a URL.

2. **Deploys seguintes:**

   ```
   gcloud builds submit --project <PROJECT_ID> \
     --service-account=projects/<PROJECT_ID>/serviceAccounts/vitarerum-build@<PROJECT_ID>.iam.gserviceaccount.com
   ```

## Acessar o banco de fora

O Postgres so' aceita conexoes de dentro da sub-rede (`permitir-postgres-interno`),
entao de fora e' sempre por tunel SSH na VM. Pelo terminal:

```
gcloud --project <PROJECT_ID> compute ssh postgres-gratis --zone us-east1-d \
  --command "sudo -u postgres psql -d vitarerum"
```

Num cliente grafico (DBeaver e afins), a aba SSH aponta para o IP externo
estatico da VM, com o usuario local e a chave que o `gcloud compute ssh` ja'
criou em `~/.ssh/google_compute_engine`; a aba principal usa `localhost:5432`,
porque esse host e' resolvido de dentro da VM, depois do tunel montado. A
senha e' a do segredo `DB_PASSWORD`.

## O que continua pendente

Nenhum destes e' regressao da migracao — sao lacunas do ambiente atual que
foram reproduzidas como estao:

- **Arquivos ainda vao para disco efemero.** `FILE_STORAGE_BACKEND=gcs` e
  `GCS_BUCKET_NAME` estao na env e o bucket e' criado, mas nao ha' cliente GCS
  no codigo: `build_file_storage()` devolve sempre `LocalDiskFileStorage` em
  `/app/data`, que o Cloud Run descarta a cada revisao. Implementar exige
  `google-cloud-storage` e uma `GcsFileStorage` em
  `app/shared/file_storage.py`.
- **O sweep nao investiga nada por padrao.** `run-sweep` faz a busca
  deterministica e depois roda as investigacoes que ela enfileirou — mas
  `scientific_return_full_agentic_enabled` e `scientific_return_agent_mode`
  vem desligados. Ligue-os na env do job quando quiser o fluxo agentico.
- **O banco nao tem backup.** VM sem snapshot agendado e com
  `deletionProtection: false`.
- **Sem CI.** Nao ha' trigger no Cloud Build; todo deploy e' manual.
