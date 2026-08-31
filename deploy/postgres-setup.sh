#!/usr/bin/env bash
# Instala e configura o PostgreSQL na VM de banco.
#
# Nao rode isto na sua maquina: provision.sh copia o arquivo para a VM e o
# executa la via `gcloud compute ssh`. Para rodar a mao:
#
#   gcloud compute scp deploy/postgres-setup.sh postgres-gratis:~ --zone us-east1-d
#   gcloud compute ssh postgres-gratis --zone us-east1-d -- \
#     'sudo DB_NAME=vitarerum DB_USER=vitarerum DB_PASSWORD=... \
#      SUBNET_CIDR=10.142.0.0/20 bash ~/postgres-setup.sh'
#
# E' idempotente: rodar de novo so' reaplica a senha e a configuracao.
set -euo pipefail

: "${DB_NAME:?DB_NAME e' obrigatorio}"
: "${DB_USER:?DB_USER e' obrigatorio}"
: "${DB_PASSWORD:?DB_PASSWORD e' obrigatorio}"
: "${SUBNET_CIDR:?SUBNET_CIDR e' obrigatorio}"

if [[ $EUID -ne 0 ]]; then
  echo "ERRO: rode como root (sudo)." >&2
  exit 1
fi

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

# --- swap ------------------------------------------------------------------
# A e2-micro tem 1 GB de RAM. Sem swap o postgres e' morto pelo OOM killer no
# primeiro `alembic upgrade head` um pouco mais pesado.
if ! swapon --show --noheadings | grep -q .; then
  log "Criando swapfile de 2 GB"
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
else
  log "Swap ja' configurado, pulando"
fi

# --- pacotes ---------------------------------------------------------------
log "Instalando o PostgreSQL"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq postgresql postgresql-contrib

PG_VERSION="$(psql --version | grep -oE '[0-9]+' | head -1)"
PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
PG_HBA="/etc/postgresql/${PG_VERSION}/main/pg_hba.conf"
log "PostgreSQL ${PG_VERSION} detectado em /etc/postgresql/${PG_VERSION}/main"

# --- role e database -------------------------------------------------------
# Aspas simples dobradas: a senha e' interpolada dentro de uma string SQL.
ESCAPED_PASSWORD="${DB_PASSWORD//\'/\'\'}"

log "Criando role ${DB_USER} e database ${DB_NAME}"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} LOGIN PASSWORD '${ESCAPED_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_USER} LOGIN PASSWORD '${ESCAPED_PASSWORD}';
  END IF;
END
\$\$;
SQL

if ! sudo -u postgres psql -tAc \
  "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -q 1; then
  sudo -u postgres createdb -O "${DB_USER}" "${DB_NAME}"
else
  echo "database ${DB_NAME} ja' existe"
fi

# O alembic cria tipos e tabelas no schema public; no PostgreSQL 15+ o dono do
# database nao basta, o CREATE no public precisa ser concedido explicitamente.
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" <<SQL
GRANT ALL ON SCHEMA public TO ${DB_USER};
ALTER DATABASE ${DB_NAME} OWNER TO ${DB_USER};
SQL

# --- rede ------------------------------------------------------------------
# O Cloud Run chega pelo egress VPC direto, com um IP da sub-rede. O firewall
# `permitir-postgres-5432` ja' restringe a origem; aqui so' e' preciso escutar
# na interface interna e exigir senha com scram-sha-256.
log "Liberando conexoes vindas de ${SUBNET_CIDR}"
if grep -qE "^\s*listen_addresses" "${PG_CONF}"; then
  sed -i "s|^\s*#\?\s*listen_addresses.*|listen_addresses = '*'|" "${PG_CONF}"
else
  echo "listen_addresses = '*'" >>"${PG_CONF}"
fi

HBA_RULE="host    ${DB_NAME}    ${DB_USER}    ${SUBNET_CIDR}    scram-sha-256"
if ! grep -qF "${SUBNET_CIDR}" "${PG_HBA}"; then
  printf '\n# Cloud Run (egress VPC direto) - adicionado por deploy/postgres-setup.sh\n%s\n' \
    "${HBA_RULE}" >>"${PG_HBA}"
else
  echo "pg_hba ja' contem uma regra para ${SUBNET_CIDR}"
fi

# --- ajuste para 1 GB de RAM ----------------------------------------------
log "Ajustando o postgres para a e2-micro"
sed -i "s|^\s*#\?\s*shared_buffers.*|shared_buffers = 128MB|" "${PG_CONF}"
sed -i "s|^\s*#\?\s*max_connections.*|max_connections = 50|" "${PG_CONF}"

systemctl enable postgresql
systemctl restart postgresql

log "Pronto. Testando a conexao local"
PGPASSWORD="${DB_PASSWORD}" psql -h 127.0.0.1 -U "${DB_USER}" -d "${DB_NAME}" \
  -tAc 'SELECT version();'
