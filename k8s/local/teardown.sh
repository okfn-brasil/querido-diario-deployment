#!/usr/bin/env bash
# teardown.sh — Destroi o cluster kind local do Querido Diário
set -euo pipefail

CLUSTER_NAME="querido-diario-dev"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[teardown]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }

if ! kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    warn "Cluster '${CLUSTER_NAME}' não existe. Nada a fazer."
    exit 0
fi

log "Destruindo cluster '${CLUSTER_NAME}'..."
kind delete cluster --name "$CLUSTER_NAME"

log "Cluster removido. Dados locais (PVCs) foram destruídos junto com o cluster."
warn "Para remover as entradas do /etc/hosts, edite /etc/hosts manualmente"
warn "e remova as linhas com queridodiario.local"
