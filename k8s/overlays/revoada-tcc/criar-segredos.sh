#!/usr/bin/env bash
# Cria os Secrets app-secret e postgres-credentials do namespace de testes no
# Revoada, com senhas aleatórias que nunca passam pelo repositório. Idempotente:
# um Secret que já existe não é tocado (trocar a senha do Postgres depois do
# initdb do CNPG quebraria o acesso ao banco).
#
#   k8s/overlays/revoada-tcc/criar-segredos.sh [--context revoada-testes] [--namespace querido-diario-tcc]
#
# Para recriar do zero, apague os dois Secrets e o Cluster postgres (o banco
# junto) antes de rodar de novo.
set -euo pipefail

CONTEXT=revoada-testes
NAMESPACE=querido-diario-tcc
while [[ $# -gt 0 ]]; do
  case "$1" in
    --context) CONTEXT="$2"; shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    *) echo "opção desconhecida: $1" >&2; exit 2 ;;
  esac
done

k() { kubectl --context "$CONTEXT" -n "$NAMESPACE" "$@"; }
existe() { k get secret "$1" >/dev/null 2>&1; }
hex() { openssl rand -hex "$1"; }

if existe postgres-credentials; then
  echo "postgres-credentials já existe; mantido"
  DB_USER=$(k get secret postgres-credentials -o jsonpath='{.data.username}' | base64 -d)
  DB_PASSWORD=$(k get secret postgres-credentials -o jsonpath='{.data.password}' | base64 -d)
else
  DB_USER=admin
  DB_PASSWORD=$(hex 24)
  k create secret generic postgres-credentials \
    --type=kubernetes.io/basic-auth \
    --from-literal=username="$DB_USER" \
    --from-literal=password="$DB_PASSWORD"
fi

if existe app-secret; then
  echo "app-secret já existe; mantido"
  exit 0
fi

# Mesmas chaves do overlay dev (patch-secret-dev.yaml). O OpenSearch roda sem o
# plugin de segurança, como no dev: usuário e senha não são conferidos.
# Garage v2: key ID = GK + 24 hex; secret = 64 hex.
k create secret generic app-secret \
  --from-literal=QD_BACKEND_SECRET_KEY="$(hex 32)" \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_HOST=http://opensearch:9200 \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_USER=admin \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_PASSWORD=admin \
  --from-literal=QD_DATA_DB_HOST=postgres-rw \
  --from-literal=QD_DATA_DB_USER="$DB_USER" \
  --from-literal=QD_DATA_DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=QD_BACKEND_DB_HOST=postgres-rw \
  --from-literal=QD_BACKEND_DB_USER="$DB_USER" \
  --from-literal=QD_BACKEND_DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=QD_BACKEND_DB_URL="postgres://$DB_USER:$DB_PASSWORD@postgres-rw:5432/backend" \
  --from-literal=POSTGRES_COMPANIES_HOST=postgres-rw \
  --from-literal=POSTGRES_COMPANIES_USER="$DB_USER" \
  --from-literal=POSTGRES_COMPANIES_PASSWORD="$DB_PASSWORD" \
  --from-literal=STORAGE_ACCESS_KEY="GK$(hex 12)" \
  --from-literal=STORAGE_ACCESS_SECRET="$(hex 32)" \
  --from-literal=STORAGE_BUCKET=queridodiariobucket \
  --from-literal=MAILJET_API_KEY= \
  --from-literal=MAILJET_SECRET_KEY= \
  --from-literal=QUERIDO_DIARIO_SUGGESTION_RECIPIENT_EMAIL= \
  --from-literal=QUERIDO_DIARIO_SCRAPER_API_KEYS="$(hex 24)"
