#!/usr/bin/env bash
# setup.sh — Configura o cluster kind local para desenvolvimento do Querido Diário
# Idempotente: pode ser executado múltiplas vezes sem erros.
set -euo pipefail

CLUSTER_NAME="querido-diario-dev"
NAMESPACE="querido-diario"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()  { echo -e "${GREEN}[setup]${NC} $*"; }
info() { echo -e "${BLUE}[info]${NC}  $*"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $*"; }
err()  { echo -e "${RED}[erro]${NC}  $*" >&2; exit 1; }

# ─── 1. Verifica dependências ─────────────────────────────────────────────────

KIND_MIN_VERSION="0.20.0"
KIND_INSTALL_VERSION="0.24.0"
KIND_BIN="${HOME}/.local/bin/kind"

log "Verificando dependências..."
command -v kubectl >/dev/null 2>&1 || err "kubectl não encontrado."
command -v docker  >/dev/null 2>&1 || err "docker não encontrado."
docker info >/dev/null 2>&1        || err "Docker daemon não está rodando."

# Garante kind >= KIND_MIN_VERSION (v0.11 cria k8s 1.21, incompatível com Traefik chart moderno)
# Usa sort -V para comparação correta de versões semânticas.
_kind_ok() {
    local current
    current=$(kind version 2>/dev/null | grep -oP 'v\K[0-9]+\.[0-9]+\.[0-9]+' | head -1) || return 1
    # sort -V -C retorna 0 se a entrada já estiver em ordem crescente (MIN <= current)
    printf '%s\n%s\n' "$KIND_MIN_VERSION" "$current" | sort -V -C
}

if ! command -v kind >/dev/null 2>&1 || ! _kind_ok; then
    CURRENT=$(kind version 2>/dev/null || echo "não instalado")
    warn "kind desatualizado ou ausente ($CURRENT). Mínimo necessário: v${KIND_MIN_VERSION}."
    log "Instalando kind v${KIND_INSTALL_VERSION} em ${KIND_BIN}..."
    mkdir -p "$(dirname "$KIND_BIN")"
    curl -fsSLo "$KIND_BIN" \
        "https://kind.sigs.k8s.io/dl/v${KIND_INSTALL_VERSION}/kind-linux-amd64"
    chmod +x "$KIND_BIN"
    export PATH="$(dirname "$KIND_BIN"):$PATH"
    info "kind instalado: $(kind version)"
else
    info "kind ok: $(kind version)"
fi

# ─── 2. Verifica porta 80 ─────────────────────────────────────────────────────

if ss -tlnp 2>/dev/null | grep -q ':80 ' || netstat -tlnp 2>/dev/null | grep -q ':80 '; then
    warn "Porta 80 pode já estar em uso. Verifique antes de continuar."
    warn "Se tiver nginx/apache/outro serviço, pare-o primeiro."
fi

# ─── 3. Instala helm se necessário ───────────────────────────────────────────

if ! command -v helm >/dev/null 2>&1; then
    log "Instalando helm..."
    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
else
    info "helm já instalado: $(helm version --short)"
fi

# ─── 4. Cria cluster kind ────────────────────────────────────────────────────

if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    info "Cluster '${CLUSTER_NAME}' já existe, pulando criação."
else
    log "Criando cluster kind '${CLUSTER_NAME}'..."
    kind create cluster --name "$CLUSTER_NAME" --config "$SCRIPT_DIR/kind-config.yaml"
fi

log "Selecionando contexto kubectl: kind-${CLUSTER_NAME}"
kubectl config use-context "kind-${CLUSTER_NAME}"

# ─── 5. Instala Traefik via helm ─────────────────────────────────────────────

log "Configurando repositório helm do Traefik..."
helm repo add traefik https://traefik.github.io/charts 2>/dev/null || true
helm repo update traefik >/dev/null

log "Instalando/atualizando Traefik (aguarde ~60s)..."
helm upgrade --install traefik traefik/traefik \
    --namespace traefik \
    --create-namespace \
    --values "$SCRIPT_DIR/traefik-values.yaml" \
    --wait --timeout 120s

info "Traefik pronto."

# ─── 6. Aplica overlay dev ───────────────────────────────────────────────────

log "Aplicando manifestos de desenvolvimento..."
kubectl apply -k "$K8S_DIR/overlays/dev"

# ─── 7. Aguarda infra ficar pronta ───────────────────────────────────────────

log "Aguardando infra (postgres, opensearch, minio)..."
kubectl rollout status deployment/postgres    -n "$NAMESPACE" --timeout=120s
kubectl rollout status deployment/opensearch  -n "$NAMESPACE" --timeout=180s
kubectl rollout status deployment/minio       -n "$NAMESPACE" --timeout=120s

log "Aguardando serviços de aplicação..."
kubectl rollout status deployment/redis        -n "$NAMESPACE" --timeout=120s
kubectl rollout status deployment/apache-tika  -n "$NAMESPACE" --timeout=180s

log "Aguardando jobs de inicialização..."
kubectl wait job/minio-createbucket   -n "$NAMESPACE" --for=condition=complete --timeout=60s 2>/dev/null || \
    warn "Job minio-createbucket não concluiu em 60s (pode já ter rodado antes)"
kubectl wait job/opensearch-init      -n "$NAMESPACE" --for=condition=complete --timeout=60s 2>/dev/null || \
    warn "Job opensearch-init não concluiu em 60s (pode já ter rodado antes)"

# ─── 8. /etc/hosts ───────────────────────────────────────────────────────────

HOSTS=(
    "queridodiario.local"
    "api.queridodiario.local"
    "backend-api.queridodiario.local"
)

MISSING=()
for host in "${HOSTS[@]}"; do
    grep -q "$host" /etc/hosts 2>/dev/null || MISSING+=("$host")
done

if [ ${#MISSING[@]} -gt 0 ]; then
    warn "Entradas ausentes no /etc/hosts. Adicione com:"
    warn "  make k8s-local-hosts   (requer sudo)"
    warn "  ou manualmente:"
    for h in "${MISSING[@]}"; do
        warn "    echo '127.0.0.1  $h' | sudo tee -a /etc/hosts"
    done
else
    info "/etc/hosts já configurado."
fi

# ─── 9. Resumo ───────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Setup concluído!                                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo "  API:      http://api.queridodiario.local"
echo "  Backend:  http://backend-api.queridodiario.local"
echo "  MinIO UI: kubectl port-forward svc/minio 9001:9001 -n querido-diario"
echo "             → http://localhost:9001  (user: minio-access-key)"
echo ""
echo "  Outros comandos úteis:"
echo "    make k8s-local-hosts   # adiciona /etc/hosts (sudo)"
echo "    make k8s-local-status  # status dos pods"
echo "    make k8s-local-down    # destroi o cluster"
echo ""
