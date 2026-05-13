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

# Extrai a versão de nó esperada do kind-config.yaml
EXPECTED_NODE_IMAGE=$(grep 'image:' "$SCRIPT_DIR/kind-config.yaml" | awk '{print $2}' | head -1)

_cluster_node_ok() {
    # Verifica se o cluster existente usa a imagem de nó esperada
    local current_image
    current_image=$(kubectl get nodes -o jsonpath='{.items[0].status.nodeInfo.osImage}' 2>/dev/null) || return 1
    # Compara a versão k8s do nó com a versão esperada na imagem
    local expected_ver current_ver
    expected_ver=$(echo "$EXPECTED_NODE_IMAGE" | grep -oP 'v\K[0-9]+\.[0-9]+' | head -1)
    current_ver=$(kubectl version --short 2>/dev/null | grep 'Server' | grep -oP 'v\K[0-9]+\.[0-9]+' | head -1) || \
        current_ver=$(kubectl version 2>/dev/null | grep 'Server' | grep -oP 'v\K[0-9]+\.[0-9]+' | head -1)
    [ "$current_ver" = "$expected_ver" ]
}

if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    kubectl config use-context "kind-${CLUSTER_NAME}" 2>/dev/null || true
    if _cluster_node_ok; then
        info "Cluster '${CLUSTER_NAME}' já existe com a versão correta, pulando criação."
    else
        CURRENT_VER=$(kubectl version 2>/dev/null | grep -i server | grep -oP 'v[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo "desconhecida")
        warn "Cluster existe com k8s ${CURRENT_VER}, mas a config requer ${EXPECTED_NODE_IMAGE}."
        warn "Recriando cluster (dados locais serão perdidos)..."
        kind delete cluster --name "$CLUSTER_NAME"
        log "Criando cluster kind '${CLUSTER_NAME}' com ${EXPECTED_NODE_IMAGE}..."
        kind create cluster --name "$CLUSTER_NAME" --config "$SCRIPT_DIR/kind-config.yaml"
    fi
else
    log "Criando cluster kind '${CLUSTER_NAME}'..."
    kind create cluster --name "$CLUSTER_NAME" --config "$SCRIPT_DIR/kind-config.yaml"
fi

log "Selecionando contexto kubectl: kind-${CLUSTER_NAME}"
kubectl config use-context "kind-${CLUSTER_NAME}"

# ─── 5. Instala Traefik via helm ─────────────────────────────────────────────

log "Configurando repositório helm do Traefik..."
helm repo add traefik https://traefik.github.io/charts 2>/dev/null || true
helm repo update traefik 2>/dev/null || warn "helm repo update falhou, usando cache local."

# Release em estado 'failed' (ex: timeout anterior) impede upgrade — remove para reinstalar limpo
if helm status traefik -n traefik 2>/dev/null | grep -q 'STATUS: failed'; then
    warn "Release traefik em estado 'failed'. Removendo para reinstalar..."
    helm uninstall traefik -n traefik 2>/dev/null || true
    kubectl delete namespace traefik --ignore-not-found 2>/dev/null || true
    sleep 3
fi

log "Instalando/atualizando Traefik (pode levar até 5min no primeiro pull)..."

# Tenta pré-carregar a imagem do Traefik no nó kind para evitar timeout no --wait.
# Feito em subshell com set +e para nunca interromper o script principal.
_preload_traefik_image() (
    set +e
    local chart_meta values registry repo tag full_image
    # appVersion é a versão real usada quando tag: está vazio no values.yaml
    chart_meta=$(helm show chart traefik/traefik 2>/dev/null) || return 0
    tag=$(echo "$chart_meta" | awk '/^appVersion:/{print $2}')
    values=$(helm show values traefik/traefik 2>/dev/null) || return 0
    registry=$(echo "$values" | awk '/^image:/{f=1} f && /registry:/{gsub(/"/, "", $2); print $2; exit}')
    repo=$(echo "$values"    | awk '/^image:/{f=1} f && /repository:/{gsub(/"/, "", $2); print $2; exit}')
    # Remove aspas e ignora valores vazios ou comentários
    tag=${tag//\"/};  tag=${tag//\'/}
    repo=${repo//\"/}; repo=${repo//\'/}
    registry=${registry//\"/}; registry=${registry//\'/}
    [[ "$tag"  =~ ^#|^$ ]] && return 0
    [[ "$repo" =~ ^#|^$ ]] && return 0
    # Monta imagem: registry/repo:tag ou repo:tag se registry estiver vazio
    if [ -n "$registry" ] && [[ ! "$registry" =~ ^# ]]; then
        full_image="${registry}/${repo}:${tag}"
    else
        full_image="${repo}:${tag}"
    fi
    log "Pré-carregando ${full_image} no nó kind..."
    docker pull "$full_image" 2>&1 || return 0
    kind load docker-image "$full_image" --name "$CLUSTER_NAME" 2>&1 || return 0
)
_preload_traefik_image || true

helm upgrade --install traefik traefik/traefik \
    --namespace traefik \
    --create-namespace \
    --values "$SCRIPT_DIR/traefik-values.yaml"

log "Aguardando Traefik ficar pronto..."
kubectl rollout status daemonset/traefik -n traefik --timeout=300s

info "Traefik pronto."

# ─── 6. Pré-carrega imagens de infra dev ─────────────────────────────────────

# Imagens grandes (postgres ~300MB, opensearch ~800MB) que demorariam muito
# para baixar dentro do cluster. Puxamos no host e carregamos via kind load.
_preload_image() (
    set +e
    local image="$1"
    log "Pré-carregando ${image}..."
    docker pull "$image" 2>&1 || { warn "Pull de ${image} falhou, continuando."; return 0; }
    kind load docker-image "$image" --name "$CLUSTER_NAME" 2>&1 || true
)

DEV_INFRA_IMAGES=(
    "postgres:13"
    "opensearchproject/opensearch:2.9.0"
    "quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z"
    "quay.io/minio/mc:RELEASE.2025-03-12T17-29-24Z"
    "curlimages/curl:latest"
    "busybox"
)

log "Pré-carregando imagens de infra dev no nó kind..."
for img in "${DEV_INFRA_IMAGES[@]}"; do
    _preload_image "$img" || true
done

# ─── 7. Aplica overlay dev ───────────────────────────────────────────────────

log "Aplicando manifestos de desenvolvimento..."
kubectl apply -k "$K8S_DIR/overlays/dev"

# ─── 8. Aguarda infra ficar pronta ───────────────────────────────────────────

log "Aguardando infra (postgres, opensearch, minio)..."
kubectl rollout status deployment/postgres   -n "$NAMESPACE" --timeout=120s
kubectl rollout status deployment/minio      -n "$NAMESPACE" --timeout=120s
# OpenSearch inicializa JVM + índices, pode demorar >2min mesmo com imagem local
kubectl rollout status deployment/opensearch -n "$NAMESPACE" --timeout=300s

log "Aguardando serviços de aplicação..."
kubectl rollout status deployment/redis        -n "$NAMESPACE" --timeout=120s
kubectl rollout status deployment/apache-tika  -n "$NAMESPACE" --timeout=300s

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
