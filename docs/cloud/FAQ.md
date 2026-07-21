# FAQ de Operacao na Google Cloud

Este FAQ complementa o tutorial de deploy em `docs/cloud/README.md` e o
registro de execucao em `docs/cloud/comandos-deploy-executados.md`.

## O que fazer quando um secret mudar?

Crie uma nova versao do secret no Secret Manager. Nao edite o valor antigo.

```bash
printf '%s' '<NOVO_VALOR>' | gcloud secrets versions add NOME_DO_SECRET --data-file=-
```

Exemplo:

```bash
printf '%s' '<NOVA_SENHA_SMTP>' | gcloud secrets versions add SMTP_PASSWORD --data-file=-
```

Depois, gere uma nova revisao do Cloud Run para que o servico leia a versao
mais recente:

```bash
gcloud run services update vitarerum \
  --region us-east1 \
  --update-secrets NOME_DO_SECRET=NOME_DO_SECRET:latest
```

Exemplo:

```bash
gcloud run services update vitarerum \
  --region us-east1 \
  --update-secrets SMTP_PASSWORD=SMTP_PASSWORD:latest
```

Checkpoint:

```bash
gcloud run services describe vitarerum \
  --region us-east1 \
  --format='flattened(spec.template.spec.containers[0].env)'
```

Sucesso esperado: o secret aparece como `valueFrom.secretKeyRef` com `key:
latest`. O comando nao deve imprimir o valor secreto.

## E se o secret tambem for usado pelo Job de migracao?

Atualize tambem o Cloud Run Job:

```bash
gcloud run jobs update vitarerum-migrate \
  --region us-east1 \
  --update-secrets NOME_DO_SECRET=NOME_DO_SECRET:latest
```

Se o secret alterado for `DATABASE_URL`, execute o Job para validar conexao e
aplicar migracoes pendentes:

```bash
gcloud run jobs execute vitarerum-migrate \
  --region us-east1 \
  --wait
```

Checkpoint: a execucao deve terminar com `successfully completed`.

## Preciso fazer deploy quando o secret muda?

Sim, para o servico em execucao receber o novo valor. Secrets montados como
variaveis de ambiente sao resolvidos na criacao da revisao do Cloud Run. Criar
uma nova versao no Secret Manager nao reinicia automaticamente a revisao atual.

Para o service:

```bash
gcloud run services update vitarerum \
  --region us-east1 \
  --update-secrets NOME_DO_SECRET=NOME_DO_SECRET:latest
```

Para o Job:

```bash
gcloud run jobs update vitarerum-migrate \
  --region us-east1 \
  --update-secrets NOME_DO_SECRET=NOME_DO_SECRET:latest
```

## Como fazer deploy de uma nova versao da aplicacao?

Use o pipeline completo:

```bash
gcloud builds submit --config cloudbuild.yaml .
```

Esse comando executa o fluxo completo:

1. build da imagem unica com Angular + FastAPI;
2. push para o Artifact Registry;
3. update do Job `vitarerum-migrate`;
4. execucao das migracoes Alembic;
5. deploy do service `vitarerum`.

Checkpoint: o final do comando deve mostrar `STATUS: SUCCESS`.

## Como verificar se a nova versao esta no ar?

Confira a revisao ativa:

```bash
gcloud run services describe vitarerum \
  --region us-east1 \
  --format='value(status.latestReadyRevisionName,status.url)'
```

Depois valide os endpoints principais:

```bash
curl -i https://vitarerum-qmp4ozxwxa-ue.a.run.app/
curl -i https://vitarerum-qmp4ozxwxa-ue.a.run.app/config/environment.json
curl -i https://vitarerum-qmp4ozxwxa-ue.a.run.app/api/v1/health
curl -i https://vitarerum-qmp4ozxwxa-ue.a.run.app/api/v1/rota-inexistente
```

Sucesso esperado:

- `/` retorna `200` e `text/html`;
- `/config/environment.json` retorna `200` e `application/json`;
- `/api/v1/health` retorna `200`;
- `/api/v1/rota-inexistente` retorna `404` em JSON.

## Como fazer deploy sem rodar migracoes?

Use apenas quando tiver certeza de que nao ha alteracao de schema pendente.

```bash
gcloud builds submit --config cloudbuild.image.yaml .
```

Depois publique manualmente a imagem gerada. Se usar a tag `manual`:

```bash
gcloud run deploy vitarerum \
  --image us-east1-docker.pkg.dev/vitarerum/vitarerum/vitarerum:manual \
  --region us-east1 \
  --allow-unauthenticated \
  --service-account vitarerum-run@vitarerum.iam.gserviceaccount.com \
  --env-vars-file /tmp/vitarerum-cloudrun.env.yaml \
  --set-secrets DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,OLLAMA_API_KEY=OLLAMA_API_KEY:latest,TURNSTILE_SECRET_KEY=TURNSTILE_SECRET_KEY:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest
```

Recomendacao: para mudancas normais de produto, prefira
`gcloud builds submit --config cloudbuild.yaml .`, porque ele mantem o banco e a
aplicacao sincronizados.

## Como ver logs do servico?

```bash
gcloud run services logs read vitarerum \
  --region us-east1 \
  --limit 100
```

Objetivo: diagnosticar erros de startup, conexao com Neon, chamadas externas ou
falhas de runtime.

## Como ver logs do Job de migracao?

Liste execucoes recentes:

```bash
gcloud run jobs executions list \
  --job vitarerum-migrate \
  --region us-east1
```

Descreva uma execucao especifica:

```bash
gcloud run jobs executions describe EXECUTION_NAME \
  --region us-east1
```

Leia logs associados:

```bash
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="vitarerum-migrate"' \
  --limit 100
```

## Como voltar para uma revisao anterior?

Liste as revisoes:

```bash
gcloud run revisions list \
  --service vitarerum \
  --region us-east1
```

Direcione 100% do trafego para uma revisao anterior:

```bash
gcloud run services update-traffic vitarerum \
  --region us-east1 \
  --to-revisions REVISION_NAME=100
```

Checkpoint:

```bash
gcloud run services describe vitarerum \
  --region us-east1 \
  --format='flattened(status.traffic)'
```

Sucesso esperado: a revisao escolhida aparece com `percent: 100`.

## Quando rotacionar secrets?

Rotacione secrets quando:

- um valor foi exposto em conversa, commit, log ou terminal compartilhado;
- uma credencial de terceiro foi recriada;
- um membro da equipe saiu;
- houver suspeita de uso indevido;
- for politica periodica de seguranca.

Neste deploy, recomenda-se rotacionar os secrets informados manualmente durante
a preparacao.

## Quais lacunas ainda impedem considerar o ambiente totalmente pronto?

- Falta bootstrap seguro de usuario admin para producao.
- Falta smoke test autenticado end-to-end.
- Falta implementar o adaptador real de Google Cloud Storage no backend.
- Os avisos de budget do Angular ainda devem ser tratados.

