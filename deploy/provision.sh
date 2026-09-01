#!/usr/bin/env bash
# Provisiona o Vitarerum inteiro num projeto Google Cloud novo.
#
#   1. gcloud auth login          # com a conta NOVA
#   2. cp deploy/env.example deploy/.env && $EDITOR deploy/.env
#   3. ./deploy/provision.sh
#
# E' idempotente: cada passo verifica se o recurso ja' existe antes de criar,
# entao rodar de novo depois de uma falha retoma de onde parou. Use STEP=<nome>
# para rodar um passo isolado:
#
#   STEP=scheduler ./deploy/provision.sh
#
# Passos: project apis registry network vm serviceaccounts secrets postgres
#         bucket buildaccess image migrate seed service sweepjob scheduler
#         origins summary
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/deploy/.env"

log()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m!!  %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------
[[ -f "${ENV_FILE}" ]] || die "${ENV_FILE} nao existe. Copie de deploy/env.example."
set -a; . "${ENV_FILE}"; set +a

: "${PROJECT_ID:?defina PROJECT_ID em deploy/.env}"
: "${REGION:=us-east1}"
: "${ZONE:=us-east1-d}"
: "${SERVICE:=vitarerum}"
: "${REPOSITORY:=vitarerum}"
: "${IMAGE:=vitarerum}"
: "${DB_VM_NAME:=postgres-gratis}"
: "${DB_NAME:=vitarerum}"
: "${DB_USER:=vitarerum}"
: "${SCIENTIFIC_RETURN_JOB:=vitarerum-scientific-return}"
: "${SCIENTIFIC_RETURN_LIMIT:=25}"
: "${SCIENTIFIC_RETURN_AGENT_LIMIT:=10}"
: "${SCIENTIFIC_RETURN_SCHEDULE:=0 3 * * 1}"
: "${SCIENTIFIC_RETURN_TIMEZONE:=Europe/Lisbon}"
# Fluxo agentico autonomo. Com 'false' (o default do config.py) o sweep faz so'
# a busca deterministica e a fila fica sempre vazia. Ligado, cada watch vencido
# enfileira uma investigacao POR OBJETO CONSULTADO, ate' max_objects (15).
: "${SCIENTIFIC_RETURN_FULL_AGENTIC_ENABLED:=false}"
: "${EUROPE_PMC_ENABLED:=true}"

# Credenciais nao precisam ser copiadas para deploy/.env: se estiverem vazias
# la', sao herdadas dos segredos de producao e, no que producao nao tiver, do
# .env local. Assim nenhum segredo passa a existir num arquivo novo.
: "${SOURCE_ENV_FILE:=${ROOT}/vitarerum-api/.env}"
: "${SOURCE_PROJECT:=vitarerum}"
# Conta que enxerga SOURCE_PROJECT. Depois do `gcloud auth login` com a conta
# nova ela vira a conta ativa, e a ativa nao tem acesso ao projeto antigo: sem
# isto a heranca falharia calada e cairia no .env local, que nao tem
# TURNSTILE_SECRET_KEY. As duas contas convivem no gcloud, entao basta dizer
# qual usar na leitura. Vazio = usa a conta ativa.
: "${SOURCE_ACCOUNT:=}"

# Segredos herdados do ambiente atual, na ordem em que sao criados.
# DATABASE_URL fica FORA de proposito: o valor de producao aponta para o IP
# interno e a senha da VM antiga, que nao existem no projeto novo. Ele e' sempre
# remontado a partir da VM recem-criada, junto com DB_PASSWORD.
INHERITED_SECRETS=(JWT_SECRET FILE_ENCRYPTION_KEY DB_FIELD_ENCRYPTION_KEY
                   OLLAMA_API_KEY SMTP_PASSWORD TURNSTILE_SECRET_KEY)

# Chaves que sao aleatorias por natureza: se nem producao nem o .env local
# tiverem, o script gera. As credenciais externas nao entram aqui - inventar
# uma chave da Ollama ou do Turnstile so' adiaria a falha para o runtime.
#
# Uma funcao, e nao um array associativo: o bash que a Apple entrega em
# /bin/bash e' o 3.2, que nao tem `declare -A`.
generator_for() {
  case "$1" in
    JWT_SECRET)                             printf 'openssl rand -base64 48' ;;
    FILE_ENCRYPTION_KEY|DB_FIELD_ENCRYPTION_KEY) printf 'openssl rand -base64 32' ;;
    *)                                      printf '' ;;
  esac
}

RUN_SA="vitarerum-run@${PROJECT_ID}.iam.gserviceaccount.com"
BUILD_SA="vitarerum-build@${PROJECT_ID}.iam.gserviceaccount.com"
SCHED_SA="vitarerum-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET="${PROJECT_ID}-vitarerum-prod-files"
MIGRATE_JOB="${SERVICE}-migrate"
FIREWALL_RULE="permitir-postgres-interno"
BOOTSTRAP_TAG="bootstrap"
IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE}"

# Toda chamada gcloud deste script fala com o projeto de destino, sem depender
# do `gcloud config set project` do operador.
export CLOUDSDK_CORE_PROJECT="${PROJECT_ID}"
GC=(gcloud --project "${PROJECT_ID}" --quiet)

SOURCE_GC=(gcloud --project "${SOURCE_PROJECT}")
[[ -n "${SOURCE_ACCOUNT}" ]] && SOURCE_GC+=(--account "${SOURCE_ACCOUNT}")

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT


# ---------------------------------------------------------------------------
# Credenciais herdadas do ambiente atual
# ---------------------------------------------------------------------------
# Ordem: deploy/.env  ->  Secret Manager de SOURCE_PROJECT  ->  SOURCE_ENV_FILE.
# Nenhum valor e' impresso; so' a origem e o tamanho.
# resolve_credential devolve o resultado em CREDENTIAL_VALUE/CREDENTIAL_ORIGIN
# em vez de escrever na saida: chamada por $(...) ela rodaria num subshell, e a
# origem atribuida la' dentro nunca chegaria de volta.
CREDENTIAL_VALUE=""
CREDENTIAL_ORIGIN=""

resolve_credential() {
  local name="$1"
  CREDENTIAL_VALUE=""
  CREDENTIAL_ORIGIN=""

  if [[ -n "${!name:-}" ]]; then
    CREDENTIAL_VALUE="${!name}"
    CREDENTIAL_ORIGIN="deploy/.env"
    return
  fi

  # Producao primeiro: e' o valor que o ambiente atual realmente usa.
  if [[ -n "${SOURCE_PROJECT}" ]]; then
    CREDENTIAL_VALUE="$("${SOURCE_GC[@]}" secrets versions access latest \
      --secret="${name}" 2>/dev/null || true)"
    if [[ -n "${CREDENTIAL_VALUE}" ]]; then
      CREDENTIAL_ORIGIN="producao (${SOURCE_PROJECT})"
      return
    fi
  fi

  # O .env local so' entra no que producao nao tem.
  if [[ -f "${SOURCE_ENV_FILE}" ]]; then
    # cut -d= -f2- preserva '=' internos (base64, tokens); sed tira as aspas.
    CREDENTIAL_VALUE="$(grep -m1 "^${name}=" "${SOURCE_ENV_FILE}" 2>/dev/null \
      | cut -d= -f2- \
      | sed -E 's/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/')"
    if [[ -n "${CREDENTIAL_VALUE}" ]]; then
      CREDENTIAL_ORIGIN="${SOURCE_ENV_FILE#"${ROOT}/"}"
      return
    fi
  fi
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
preflight() {
  command -v gcloud >/dev/null || die "gcloud nao encontrado no PATH."
  command -v openssl >/dev/null || die "openssl nao encontrado no PATH."
  local account
  account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || true)"
  [[ -n "${account}" ]] || die "Nenhuma conta autenticada. Rode: gcloud auth login"
  info "Autenticado como ${account}"
  info "Projeto de destino: ${PROJECT_ID} | regiao: ${REGION} | zona: ${ZONE}"

  if [[ -n "${SOURCE_ACCOUNT}" ]]; then
    if gcloud auth list --format='value(account)' 2>/dev/null \
       | grep -qx "${SOURCE_ACCOUNT}"; then
      info "Herdando segredos de ${SOURCE_PROJECT} como ${SOURCE_ACCOUNT}"
    else
      die "SOURCE_ACCOUNT=${SOURCE_ACCOUNT} nao esta autenticada.
Rode 'gcloud auth login ${SOURCE_ACCOUNT}' - ela continua disponivel ao lado da
conta nova, e so' e' usada para ler os segredos do projeto ${SOURCE_PROJECT}."
    fi
  fi

  # Relatorio de procedencia. O valor e' resolvido de novo em step_secrets;
  # aqui so' se confere que existe, antes de criar recurso nenhum.
  local v missing=()
  for v in "${INHERITED_SECRETS[@]}"; do
    resolve_credential "${v}"
    if [[ -n "${CREDENTIAL_VALUE}" ]]; then
      info "$(printf '%-24s %2d caracteres, de %s' \
        "${v}" "${#CREDENTIAL_VALUE}" "${CREDENTIAL_ORIGIN}")"
    elif [[ -n "$(generator_for "${v}")" ]]; then
      info "$(printf '%-24s sera gerada' "${v}")"
    else
      info "$(printf '%-24s NAO ENCONTRADA' "${v}")"
      missing+=("$v")
    fi
  done
  CREDENTIAL_VALUE=""

  [[ -n "${INSTITUTION_NAME:-}" ]] || missing+=(INSTITUTION_NAME)
  if ((${#missing[@]})); then
    die "Faltando: ${missing[*]}
INSTITUTION_NAME so' pode vir de voce: e' posterior ao ultimo deploy, entao nao
existe nem em producao nem no .env local (que traz apenas a linha comentada
'# INSTITUTION_NAME=Museum', e 'Museum' e' justamente o valor que config.py
recusa). Preencha em deploy/.env o que aparecer como NAO ENCONTRADA acima."
  fi
  [[ "${INSTITUTION_NAME}" != "Museum" ]] || die "INSTITUTION_NAME nao pode ser 'Museum'."
}

# ---------------------------------------------------------------------------
# Passos
# ---------------------------------------------------------------------------
step_project() {
  log "Projeto ${PROJECT_ID}"
  if gcloud projects describe "${PROJECT_ID}" >/dev/null 2>&1; then
    info "ja' existe"
  else
    gcloud projects create "${PROJECT_ID}" --name="${PROJECT_ID}" --quiet
    info "criado"
  fi

  if [[ -n "${BILLING_ACCOUNT_ID:-}" ]]; then
    if gcloud billing projects describe "${PROJECT_ID}" \
        --format='value(billingEnabled)' 2>/dev/null | grep -qi true; then
      info "faturamento ja' vinculado"
    else
      gcloud billing projects link "${PROJECT_ID}" \
        --billing-account="${BILLING_ACCOUNT_ID}" --quiet
      info "faturamento vinculado a ${BILLING_ACCOUNT_ID}"
    fi
  else
    warn "BILLING_ACCOUNT_ID vazio. Artifact Registry e Cloud Build exigem
    faturamento ativo; vincule antes de seguir (gcloud billing accounts list)."
  fi
}

step_apis() {
  log "Habilitando APIs"
  # cloudscheduler e sqladmin nao estavam habilitadas no projeto antigo; a
  # primeira passa a ser necessaria para o sweep agendado, a segunda continua
  # de fora porque o banco e' auto-hospedado numa VM, nao Cloud SQL.
  "${GC[@]}" services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    compute.googleapis.com \
    cloudscheduler.googleapis.com \
    logging.googleapis.com \
    monitoring.googleapis.com \
    iam.googleapis.com \
    iamcredentials.googleapis.com
  info "habilitadas"
}

step_registry() {
  log "Artifact Registry ${REPOSITORY} (${REGION})"
  if "${GC[@]}" artifacts repositories describe "${REPOSITORY}" \
      --location="${REGION}" >/dev/null 2>&1; then
    info "ja' existe"
  else
    "${GC[@]}" artifacts repositories create "${REPOSITORY}" \
      --repository-format=docker --location="${REGION}" \
      --description="Imagens do Vitarerum"
    info "criado"
  fi
}

step_network() {
  log "Rede"
  # Num projeto recem-criado a VPC default nasce de forma assincrona, minutos
  # depois de compute.googleapis.com ser habilitada. Olhar cedo demais faria o
  # script criar uma rede propria que depois colidiria com a automatica.
  local attempt
  for attempt in $(seq 1 18); do
    "${GC[@]}" compute networks describe default >/dev/null 2>&1 && break
    [[ ${attempt} -eq 1 ]] && info "aguardando a VPC default ser criada..."
    sleep 10
  done

  if ! "${GC[@]}" compute networks describe default >/dev/null 2>&1; then
    warn "A VPC 'default' nao apareceu em 3 min (politica de organizacao?)."
    "${GC[@]}" compute networks create default --subnet-mode=auto
    info "VPC default criada em modo auto"
  else
    info "VPC default disponivel"
  fi

  # A sub-rede regional pode aparecer alguns segundos depois da rede.
  for attempt in $(seq 1 18); do
    SUBNET_CIDR="$("${GC[@]}" compute networks subnets describe default \
      --region="${REGION}" --format='value(ipCidrRange)' 2>/dev/null || true)"
    [[ -n "${SUBNET_CIDR}" ]] && break
    sleep 10
  done

  [[ -n "${SUBNET_CIDR:-}" ]] || die "Sub-rede default de ${REGION} nao encontrada."
  info "sub-rede default de ${REGION}: ${SUBNET_CIDR}"

  if "${GC[@]}" compute firewall-rules describe "${FIREWALL_RULE}" >/dev/null 2>&1; then
    info "firewall ${FIREWALL_RULE} ja' existe"
  else
    # Mesma regra do ambiente atual: 5432 so' de dentro da sub-rede, que e'
    # de onde o Cloud Run sai com egress VPC direto.
    "${GC[@]}" compute firewall-rules create "${FIREWALL_RULE}" \
      --network=default --direction=INGRESS --priority=1000 \
      --action=ALLOW --rules=tcp:5432 --source-ranges="${SUBNET_CIDR}" \
      --description="Postgres acessivel apenas de dentro da sub-rede"
    info "firewall ${FIREWALL_RULE} criado para ${SUBNET_CIDR}"
  fi
}

step_vm() {
  log "VM de banco ${DB_VM_NAME} (${ZONE})"

  # IP externo estatico. O efemero muda a cada parada/religada da VM, o que
  # quebra qualquer tunel SSH ja' configurado (DBeaver, por exemplo). Anexado a
  # uma instancia em execucao, o endereco reservado nao custa nada.
  local db_ip_name="${DB_VM_NAME}-ip"
  if "${GC[@]}" compute addresses describe "${db_ip_name}" --region="${REGION}" \
      >/dev/null 2>&1; then
    info "IP estatico ${db_ip_name} ja' reservado"
  else
    "${GC[@]}" compute addresses create "${db_ip_name}" --region="${REGION}"
    info "IP estatico ${db_ip_name} reservado"
  fi
  DB_EXTERNAL_IP="$("${GC[@]}" compute addresses describe "${db_ip_name}" \
    --region="${REGION}" --format='value(address)')"

  if "${GC[@]}" compute instances describe "${DB_VM_NAME}" --zone="${ZONE}" \
      >/dev/null 2>&1; then
    info "ja' existe"
  else
    # A family leva sufixo de arquitetura: 'ubuntu-minimal-2404-lts' sozinho nao
    # existe. Esta e' a family da imagem que a VM do projeto atual usa
    # (ubuntu-minimal-2404-noble-amd64). Nao inserir comentarios no meio das
    # flags abaixo: um '#' apos um '\' encerra a continuacao e o resto das
    # flags vira comando solto.
    "${GC[@]}" compute instances create "${DB_VM_NAME}" \
      --zone="${ZONE}" \
      --machine-type=e2-micro \
      --image-family=ubuntu-minimal-2404-lts-amd64 \
      --image-project=ubuntu-os-cloud \
      --boot-disk-size=30GB \
      --boot-disk-type=pd-standard \
      --network-interface=network=default,subnet=default,address=${DB_EXTERNAL_IP} \
      --scopes=https://www.googleapis.com/auth/logging.write
    info "criada"
  fi
  DB_INTERNAL_IP="$("${GC[@]}" compute instances describe "${DB_VM_NAME}" \
    --zone="${ZONE}" --format='value(networkInterfaces[0].networkIP)')"
  info "IP interno: ${DB_INTERNAL_IP} | IP externo estatico: ${DB_EXTERNAL_IP}"
}

step_postgres() {
  log "Instalando o PostgreSQL na VM"
  [[ -n "${SUBNET_CIDR:-}" ]] || step_network >/dev/null
  DB_PASSWORD="$(secret_value DB_PASSWORD)"

  info "Aguardando o SSH responder (pode levar ~1 min numa VM recem-criada)"
  local attempt
  for attempt in $(seq 1 12); do
    if "${GC[@]}" compute ssh "${DB_VM_NAME}" --zone="${ZONE}" \
        --command=true >/dev/null 2>&1; then
      break
    fi
    [[ ${attempt} -lt 12 ]] || die "SSH na ${DB_VM_NAME} nao respondeu."
    sleep 10
  done

  "${GC[@]}" compute scp "${ROOT}/deploy/postgres-setup.sh" \
    "${DB_VM_NAME}:~/postgres-setup.sh" --zone="${ZONE}"
  # A senha vai pelo canal SSH ja' cifrado; nao fica em metadata da instancia.
  "${GC[@]}" compute ssh "${DB_VM_NAME}" --zone="${ZONE}" --command="\
sudo DB_NAME='${DB_NAME}' DB_USER='${DB_USER}' DB_PASSWORD='${DB_PASSWORD}' \
SUBNET_CIDR='${SUBNET_CIDR}' bash ~/postgres-setup.sh && rm -f ~/postgres-setup.sh"
  info "PostgreSQL pronto"
}

step_serviceaccounts() {
  log "Contas de servico"
  create_sa "vitarerum-run"       "Vitarerum Cloud Run runtime"
  create_sa "vitarerum-build"     "Vitarerum Cloud Build deployer"
  create_sa "vitarerum-scheduler" "Vitarerum Cloud Scheduler invoker"
}

create_sa() {
  local name="$1" display="$2"
  local email="${name}@${PROJECT_ID}.iam.gserviceaccount.com"
  if "${GC[@]}" iam service-accounts describe "${email}" >/dev/null 2>&1; then
    info "${name} ja' existe"
  else
    "${GC[@]}" iam service-accounts create "${name}" --display-name="${display}"
    info "${name} criada"
  fi
}

# --- segredos --------------------------------------------------------------
# Gera o valor uma unica vez e o guarda no Secret Manager; nas execucoes
# seguintes le' de volta o que ja' esta' la'. Trocar uma dessas chaves depois
# que houver dados em producao torna ilegivel o que foi cifrado com a anterior.
secret_value() {
  local name="$1"
  "${GC[@]}" secrets versions access latest --secret="${name}" 2>/dev/null
}

put_secret() {
  local name="$1" value="$2"
  if ! "${GC[@]}" secrets describe "${name}" >/dev/null 2>&1; then
    "${GC[@]}" secrets create "${name}" --replication-policy=automatic
  fi
  if [[ -n "$(secret_value "${name}")" ]]; then
    info "${name}: valor ja' existente preservado"
  else
    # printf sem \n: uma quebra de linha no fim entraria na chave.
    printf '%s' "${value}" | "${GC[@]}" secrets versions add "${name}" --data-file=-
    info "${name}: versao criada"
  fi
  "${GC[@]}" secrets add-iam-policy-binding "${name}" \
    --member="serviceAccount:${RUN_SA}" \
    --role=roles/secretmanager.secretAccessor >/dev/null
}

step_secrets() {
  log "Segredos"
  [[ -n "${DB_INTERNAL_IP:-}" ]] || step_vm >/dev/null

  # Sem '/' nem '+' para nao precisar de percent-encoding na DATABASE_URL.
  # Sempre novos: apontam para esta VM, nao para a antiga.
  put_secret DB_PASSWORD "$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-32)"
  local db_password; db_password="$(secret_value DB_PASSWORD)"
  put_secret DATABASE_URL \
    "postgresql+asyncpg://${DB_USER}:${db_password}@${DB_INTERNAL_IP}:5432/${DB_NAME}"

  local name
  for name in "${INHERITED_SECRETS[@]}"; do
    inherit_secret "${name}"
  done
}

inherit_secret() {
  local name="$1" generator
  generator="$(generator_for "$1")"
  resolve_credential "${name}"

  if [[ -z "${CREDENTIAL_VALUE}" && -n "${generator}" ]]; then
    # ${generator} sem aspas de proposito: e' uma linha de comando a dividir.
    CREDENTIAL_VALUE="$(${generator} | tr -d '\n')"
    CREDENTIAL_ORIGIN="gerada agora"
  fi
  [[ -n "${CREDENTIAL_VALUE}" ]] || die "${name} nao foi encontrada em lugar algum."

  # config.py: JWT_SECRET precisa de >= 32 bytes; as duas chaves de cifra
  # precisam decodificar para exatamente 32 bytes. Vale checar aqui, e nao
  # descobrir no startup do container.
  case "${name}" in
    JWT_SECRET)
      (( ${#CREDENTIAL_VALUE} >= 32 )) \
        || die "JWT_SECRET tem ${#CREDENTIAL_VALUE} bytes; config.py exige >= 32."
      ;;
    FILE_ENCRYPTION_KEY|DB_FIELD_ENCRYPTION_KEY)
      local bytes
      bytes="$(printf '%s' "${CREDENTIAL_VALUE}" | base64 -d 2>/dev/null | wc -c | tr -d ' ')"
      [[ "${bytes}" == "32" ]] \
        || die "${name} (origem: ${CREDENTIAL_ORIGIN}) decodifica para ${bytes} bytes; config.py exige exatamente 32."
      ;;
  esac

  info "$(printf '%-24s %s' "${name}" "${CREDENTIAL_ORIGIN}")"
  put_secret "${name}" "${CREDENTIAL_VALUE}"
  CREDENTIAL_VALUE=""
}

step_bucket() {
  log "Bucket ${BUCKET}"
  if "${GC[@]}" storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
    info "ja' existe"
  else
    "${GC[@]}" storage buckets create "gs://${BUCKET}" \
      --location="${REGION}" --uniform-bucket-level-access \
      --public-access-prevention
    info "criado"
  fi
  "${GC[@]}" storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --member="serviceAccount:${RUN_SA}" --role=roles/storage.objectUser >/dev/null
  warn "O bucket e' criado por paridade com o ambiente atual, mas o codigo
    ainda nao tem cliente GCS: build_file_storage() sempre devolve
    LocalDiskFileStorage em /app/data, que e' efemero no Cloud Run."
}

step_buildaccess() {
  log "Permissoes de deploy"
  local role
  for role in roles/artifactregistry.writer roles/run.admin \
              roles/logging.logWriter roles/storage.admin; do
    "${GC[@]}" projects add-iam-policy-binding "${PROJECT_ID}" \
      --member="serviceAccount:${BUILD_SA}" --role="${role}" \
      --condition=None >/dev/null
    info "${BUILD_SA} -> ${role}"
  done
  # Para implantar um servico que roda como vitarerum-run, quem faz o deploy
  # precisa poder agir como essa conta.
  "${GC[@]}" iam service-accounts add-iam-policy-binding "${RUN_SA}" \
    --member="serviceAccount:${BUILD_SA}" \
    --role=roles/iam.serviceAccountUser >/dev/null
  info "${BUILD_SA} pode agir como ${RUN_SA}"
}

step_image() {
  log "Construindo a imagem de bootstrap"
  # cloudbuild.yaml atualiza jobs que ainda nao existem, entao o primeiro build
  # usa cloudbuild.image.yaml, que so' constroi e publica.
  (cd "${ROOT}" && "${GC[@]}" builds submit \
    --config=cloudbuild.image.yaml \
    --service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}" \
    --substitutions="_REGION=${REGION},_REPOSITORY=${REPOSITORY},_IMAGE=${IMAGE},_TAG=${BOOTSTRAP_TAG}")
  info "imagem publicada: ${IMAGE_PATH}:${BOOTSTRAP_TAG}"
}

# Env nao-secreta compartilhada pelo servico e pelos dois jobs.
write_env_file() {
  local out="$1" public_origin="$2" cors="$3"
  cat >"${out}" <<YAML
APP_ENV: production
INSTITUTION_NAME: "${INSTITUTION_NAME}"
OLLAMA_BASE_URL: "${OLLAMA_BASE_URL:-https://ollama.com}"
NARRATIVE_MODEL: "${NARRATIVE_MODEL:-gemma4:31b-cloud}"
TRIAGE_MODEL: "${TRIAGE_MODEL:-gemma4:31b-cloud}"
SCIENTIFIC_RETURN_LLM_MODEL: "${SCIENTIFIC_RETURN_LLM_MODEL:-gemma4:31b-cloud}"
PUBLIC_ORIGIN: "${public_origin}"
CORS_ORIGINS: '${cors}'
SMTP_HOST: "${SMTP_HOST:-smtp.gmail.com}"
SMTP_PORT: "${SMTP_PORT:-587}"
SMTP_USERNAME: "${SMTP_USERNAME:-}"
SMTP_FROM_ADDRESS: "${SMTP_FROM_ADDRESS:-}"
SMTP_USE_TLS: "${SMTP_USE_TLS:-true}"
GCS_BUCKET_NAME: "${BUCKET}"
FILE_STORAGE_BACKEND: gcs
SCIENTIFIC_RETURN_FULL_AGENTIC_ENABLED: "${SCIENTIFIC_RETURN_FULL_AGENTIC_ENABLED}"
EUROPE_PMC_ENABLED: "${EUROPE_PMC_ENABLED}"
YAML
}

RUN_SECRETS="DATABASE_URL=DATABASE_URL:latest,JWT_SECRET=JWT_SECRET:latest,OLLAMA_API_KEY=OLLAMA_API_KEY:latest,TURNSTILE_SECRET_KEY=TURNSTILE_SECRET_KEY:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest,FILE_ENCRYPTION_KEY=FILE_ENCRYPTION_KEY:latest,DB_FIELD_ENCRYPTION_KEY=DB_FIELD_ENCRYPTION_KEY:latest"

# URL deterministica do Cloud Run, conhecida antes do primeiro deploy.
default_origin() {
  local number
  number="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
  printf 'https://%s-%s.%s.run.app' "${SERVICE}" "${number}" "${REGION}"
}

step_migrate() {
  log "Job de migracao ${MIGRATE_JOB}"
  local envfile origin
  origin="$(default_origin)"
  envfile="${WORKDIR}/env.yaml"
  write_env_file "${envfile}" "${origin}" "[\"${origin}\"]"

  local verb=create
  "${GC[@]}" run jobs describe "${MIGRATE_JOB}" --region="${REGION}" \
    >/dev/null 2>&1 && verb=update

  # alembic/env.py importa app.config, que valida TODAS as configuracoes de
  # producao no import; por isso o job de migracao recebe a env completa.
  "${GC[@]}" run jobs "${verb}" "${MIGRATE_JOB}" \
    --image="${IMAGE_PATH}:${BOOTSTRAP_TAG}" \
    --region="${REGION}" \
    --service-account="${RUN_SA}" \
    --command=alembic --args=upgrade,head \
    --cpu=1 --memory=512Mi --max-retries=0 --task-timeout=600s \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --env-vars-file="${envfile}" \
    --set-secrets="${RUN_SECRETS}"
  info "job ${verb}d"

  "${GC[@]}" run jobs execute "${MIGRATE_JOB}" --region="${REGION}" --wait
  info "schema aplicado"
}

step_seed() {
  log "Seed de identidade inicial"
  # scripts/seed.sql RECRIA a identidade do zero: apaga permissoes, grupos,
  # instituicoes e usuarios antes de inserir. So' e' aplicado sob pedido
  # explicito justamente porque apaga.
  if [[ "${APPLY_DEV_SEED:-no}" != "yes" ]]; then
    info "pulado (APPLY_DEV_SEED != yes)"
    warn "Sem seed nao ha' nenhum identity_permissions, e a API exige um
    X-Permission-Id existente em toda requisicao. Rode com APPLY_DEV_SEED=yes
    para criar a instituicao, os grupos e as contas do MUHNAC."
    return
  fi
  warn "O seed APAGA identity_permissions, identity_groups,
    identity_institutions e identity_users antes de recriar tudo."
  "${GC[@]}" compute scp "${ROOT}/vitarerum-api/scripts/seed.sql" \
    "${DB_VM_NAME}:~/seed.sql" --zone="${ZONE}"
  # Redirecionamento, e nao 'psql -f': com -f quem abre o arquivo e' o processo
  # do psql, ja' rodando como 'postgres', que nao le dentro de /home/<usuario>.
  # Com '<' quem abre e' o shell da sessao SSH, que e' o dono do arquivo.
  "${GC[@]}" compute ssh "${DB_VM_NAME}" --zone="${ZONE}" \
    --command="sudo -u postgres psql -v ON_ERROR_STOP=1 -d '${DB_NAME}' < ~/seed.sql && rm -f ~/seed.sql"
  info "seed aplicado: MUHNAC, 5 grupos, Bob e Carla"
}

step_service() {
  log "Servico Cloud Run ${SERVICE}"
  local envfile origin
  origin="$(default_origin)"
  envfile="${WORKDIR}/env.yaml"
  write_env_file "${envfile}" "${origin}" "[\"${origin}\"]"

  "${GC[@]}" run deploy "${SERVICE}" \
    --image="${IMAGE_PATH}:${BOOTSTRAP_TAG}" \
    --region="${REGION}" \
    --service-account="${RUN_SA}" \
    --allow-unauthenticated \
    --port=8080 --cpu=1 --memory=512Mi \
    --concurrency=80 --max-instances=20 --timeout=300 --cpu-boost \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --env-vars-file="${envfile}" \
    --set-secrets="${RUN_SECRETS}"
  info "implantado"
}

step_sweepjob() {
  log "Job de sweep ${SCIENTIFIC_RETURN_JOB}"
  local envfile origin
  origin="$(default_origin)"
  envfile="${WORKDIR}/env.yaml"
  write_env_file "${envfile}" "${origin}" "[\"${origin}\"]"

  local verb=create
  "${GC[@]}" run jobs describe "${SCIENTIFIC_RETURN_JOB}" --region="${REGION}" \
    >/dev/null 2>&1 && verb=update

  # --task-timeout tem de casar com scientific_return_platform_window_seconds
  # (1800s). config.py recusa subir se a janela declarada nao couber a fatia do
  # worker mais a chamada externa mais longa.
  "${GC[@]}" run jobs "${verb}" "${SCIENTIFIC_RETURN_JOB}" \
    --image="${IMAGE_PATH}:${BOOTSTRAP_TAG}" \
    --region="${REGION}" \
    --service-account="${RUN_SA}" \
    --command=python \
    --args="-m,app.jobs.scientific_return,run-sweep,--limit,${SCIENTIFIC_RETURN_LIMIT},--agent-limit,${SCIENTIFIC_RETURN_AGENT_LIMIT}" \
    --cpu=1 --memory=1Gi --max-retries=0 --task-timeout=1800s \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --env-vars-file="${envfile}" \
    --set-secrets="${RUN_SECRETS}"
  info "job ${verb}d (task-timeout 1800s)"
}

step_scheduler() {
  log "Cloud Scheduler"
  local name="${SCIENTIFIC_RETURN_JOB}-sweep"
  local uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/${SCIENTIFIC_RETURN_JOB}:run"

  "${GC[@]}" run jobs add-iam-policy-binding "${SCIENTIFIC_RETURN_JOB}" \
    --region="${REGION}" --member="serviceAccount:${SCHED_SA}" \
    --role=roles/run.invoker >/dev/null
  info "${SCHED_SA} pode executar o job"

  local verb=create
  "${GC[@]}" scheduler jobs describe "${name}" --location="${REGION}" \
    >/dev/null 2>&1 && verb=update

  "${GC[@]}" scheduler jobs "${verb}" http "${name}" \
    --location="${REGION}" \
    --schedule="${SCIENTIFIC_RETURN_SCHEDULE}" \
    --time-zone="${SCIENTIFIC_RETURN_TIMEZONE}" \
    --uri="${uri}" --http-method=POST \
    --oauth-service-account-email="${SCHED_SA}" \
    --attempt-deadline=180s
  info "agendado: '${SCIENTIFIC_RETURN_SCHEDULE}' (${SCIENTIFIC_RETURN_TIMEZONE})"
}

step_origins() {
  log "Reconciliando PUBLIC_ORIGIN / CORS_ORIGINS"
  # O Cloud Run tambem publica uma URL legada com hash imprevisivel. Ela so'
  # existe depois do primeiro deploy, entao as duas entram no CORS agora.
  local urls cors primary
  urls="$("${GC[@]}" run services describe "${SERVICE}" --region="${REGION}" \
    --format='value(metadata.annotations."run.googleapis.com/urls")')"
  primary="$(default_origin)"
  cors="$(printf '%s' "${urls}" | tr -d '[]"' | tr ',' '\n' | sed '/^$/d' \
    | awk '{printf "%s\"%s\"", (NR>1 ? "," : ""), $0}')"
  [[ -n "${cors}" ]] || cors="\"${primary}\""
  info "origens: [${cors}]"

  local envfile
  envfile="${WORKDIR}/env.yaml"
  write_env_file "${envfile}" "${primary}" "[${cors}]"

  local target
  for target in "${MIGRATE_JOB}" "${SCIENTIFIC_RETURN_JOB}"; do
    "${GC[@]}" run jobs update "${target}" --region="${REGION}" \
      --env-vars-file="${envfile}" --set-secrets="${RUN_SECRETS}" >/dev/null
  done
  "${GC[@]}" run services update "${SERVICE}" --region="${REGION}" \
    --env-vars-file="${envfile}" --set-secrets="${RUN_SECRETS}" >/dev/null
  info "servico e jobs atualizados"
}

step_summary() {
  log "Pronto"
  local url
  url="$("${GC[@]}" run services describe "${SERVICE}" --region="${REGION}" \
    --format='value(status.url)')"
  cat <<TXT

  Projeto ......... ${PROJECT_ID}  (${REGION})
  Aplicacao ....... ${url}
  Banco ........... ${DB_VM_NAME} @ ${ZONE}  (${DB_INTERNAL_IP:-IP interno: gcloud compute instances list})
  Imagem .......... ${IMAGE_PATH}:${BOOTSTRAP_TAG}
  Jobs ............ ${MIGRATE_JOB}, ${SCIENTIFIC_RETURN_JOB}
  Sweep ........... '${SCIENTIFIC_RETURN_SCHEDULE}' (${SCIENTIFIC_RETURN_TIMEZONE})

  Deploys seguintes passam a usar o cloudbuild.yaml normal:

    gcloud builds submit --project ${PROJECT_ID} \\
      --service-account=projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}

TXT
}

# ---------------------------------------------------------------------------
main() {
  preflight
  local all=(project apis registry network vm serviceaccounts secrets postgres
             bucket buildaccess image migrate seed service sweepjob scheduler
             origins summary)
  local steps=("${all[@]}")
  if [[ -n "${STEP:-}" ]]; then
    steps=("${STEP}")
    # Passos isolados dependem de valores descobertos pelos anteriores.
    case "${STEP}" in
      postgres|secrets|summary) step_network >/dev/null; step_vm >/dev/null ;;
    esac
  fi
  local s
  for s in "${steps[@]}"; do "step_${s}"; done
}

main "$@"
