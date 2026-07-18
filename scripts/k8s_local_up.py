#!/usr/bin/env python3
"""k8s_local_up.py — Configura o cluster kind local para desenvolvimento do
Querido Diário. Idempotente: pode ser executado múltiplas vezes sem erros.

Substitui o antigo k8s/local/setup.sh (bash) por uma versão que roda igual
em Linux, macOS e Windows, sem depender de bash/grep/awk/ss/netstat.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pycommon as pc  # noqa: E402

CLUSTER_NAME = "querido-diario-dev"
NAMESPACE = "querido-diario"

REPO_ROOT = pc.REPO_ROOT
K8S_DIR = REPO_ROOT / "k8s"
LOCAL_DIR = K8S_DIR / "local"
KIND_CONFIG = LOCAL_DIR / "kind-config.yaml"
TRAEFIK_VALUES = LOCAL_DIR / "traefik-values.yaml"
DEV_OVERLAY = K8S_DIR / "overlays" / "dev"

KIND_MIN_VERSION = "0.20.0"
KIND_INSTALL_VERSION = "0.24.0"
CNPG_VERSION = "1.24.0"
CNPG_RELEASE = "1.24"

DEV_INFRA_IMAGES = [
    "ghcr.io/cloudnative-pg/postgresql:15",
    "ghcr.io/cloudnative-pg/cloudnative-pg:1.24.0",
    "opensearchproject/opensearch:2.19.1",
    "dxflrs/garage:v2.3.0",
    "khairul169/garage-webui:latest",
    "curlimages/curl:latest",
    "busybox",
]

HOSTS = [
    "queridodiario.local",
    "api.queridodiario.local",
    "backend-api.queridodiario.local",
]


# ─── 0. Preflight: valida o setup local antes de tocar em qualquer cluster ──

def preflight() -> None:
    pc.log("Verificando setup local...")

    for required in (KIND_CONFIG, TRAEFIK_VALUES):
        if not required.exists():
            pc.err(f"Arquivo esperado não encontrado: {required}")

    if not DEV_OVERLAY.exists():
        pc.err(f"Overlay de dev não encontrado: {DEV_OVERLAY}")

    pc.check_docker()

    port_status = pc.port_in_use(80)
    if port_status is True:
        pc.warn("Porta 80 já parece estar em uso. O Traefik do kind usa hostPort 80.")
        pc.warn("Se tiver nginx/apache/outro serviço nela, pare-o antes de continuar.")
    elif port_status is None:
        pc.info("Não foi possível verificar a porta 80 sem privilégios elevados — pulando checagem.")

    pc.info("Setup local ok.")


def validate_dev_overlay_builds(kubectl: str) -> None:
    """Roda `kubectl kustomize` no overlay dev antes de criar o cluster, para
    falhar cedo (YAML quebrado, patch inválido, etc.) em vez de no meio da
    criação do cluster."""
    pc.log("Validando que o overlay dev builda corretamente (kubectl kustomize)...")
    result = pc.run(
        [kubectl, "kustomize", str(DEV_OVERLAY)],
        stdout=pc.subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        pc.err(
            "`kubectl kustomize k8s/overlays/dev` falhou — corrija os manifestos "
            "antes de criar o cluster (veja o erro acima)."
        )
    pc.info("Overlay dev ok.")


# ─── 1. Dependências ────────────────────────────────────────────────────────

def ensure_dependencies() -> None:
    pc.log("Verificando dependências...")
    pc.ensure_kubectl()
    pc.ensure_kind(KIND_MIN_VERSION, KIND_INSTALL_VERSION)
    pc.ensure_helm()


# ─── 4. Cluster kind ────────────────────────────────────────────────────────

def _expected_node_image() -> str:
    text = KIND_CONFIG.read_text(encoding="utf-8")
    m = re.search(r"^\s*image:\s*(\S+)", text, re.MULTILINE)
    if not m:
        pc.err(f"Não encontrei 'image:' em {KIND_CONFIG}")
    return m.group(1)


def _cluster_node_ok(expected_image: str) -> bool:
    expected_ver_m = re.search(r"v(\d+\.\d+)", expected_image)
    if not expected_ver_m:
        return False
    expected_ver = expected_ver_m.group(1)

    current_ver = pc.capture(
        ["kubectl", "version", "-o", "json"]
    )
    if not current_ver:
        return False
    try:
        import json

        data = json.loads(current_ver)
        server_ver = data.get("serverVersion", {})
        major, minor = server_ver.get("major", ""), server_ver.get("minor", "")
        minor = re.sub(r"\D", "", minor)
        current = f"{major}.{minor}"
    except Exception:
        return False
    return current == expected_ver


def ensure_cluster() -> None:
    expected_image = _expected_node_image()
    existing_clusters = pc.capture(["kind", "get", "clusters"]) or ""
    exists = CLUSTER_NAME in existing_clusters.splitlines()

    if exists:
        pc.run(["kubectl", "config", "use-context", f"kind-{CLUSTER_NAME}"], check=False)
        if _cluster_node_ok(expected_image):
            pc.info(f"Cluster '{CLUSTER_NAME}' já existe com a versão correta, pulando criação.")
            return
        pc.warn(f"Cluster existe mas não está na versão esperada ({expected_image}).")
        pc.warn("Recriando cluster (dados locais serão perdidos)...")
        pc.run(["kind", "delete", "cluster", "--name", CLUSTER_NAME])

    pc.log(f"Criando cluster kind '{CLUSTER_NAME}' com {expected_image}...")
    pc.run(["kind", "create", "cluster", "--name", CLUSTER_NAME, "--config", str(KIND_CONFIG)])

    pc.log(f"Selecionando contexto kubectl: kind-{CLUSTER_NAME}")
    pc.run(["kubectl", "config", "use-context", f"kind-{CLUSTER_NAME}"])


# ─── 5. Traefik via helm ────────────────────────────────────────────────────

def install_traefik() -> None:
    pc.log("Configurando repositório helm do Traefik...")
    pc.run(["helm", "repo", "add", "traefik", "https://traefik.github.io/charts"], check=False)
    if not pc.run_ok(["helm", "repo", "update", "traefik"]):
        pc.warn("helm repo update falhou, usando cache local.")

    status = pc.capture(["helm", "status", "traefik", "-n", "traefik"]) or ""
    if "STATUS: failed" in status:
        pc.warn("Release traefik em estado 'failed'. Removendo para reinstalar...")
        pc.run(["helm", "uninstall", "traefik", "-n", "traefik"], check=False)
        pc.run(["kubectl", "delete", "namespace", "traefik", "--ignore-not-found"], check=False)
        time.sleep(3)

    pc.log("Instalando/atualizando Traefik (pode levar até 5min no primeiro pull)...")
    _preload_traefik_image()

    pc.run(
        [
            "helm", "upgrade", "--install", "traefik", "traefik/traefik",
            "--namespace", "traefik",
            "--create-namespace",
            "--values", str(TRAEFIK_VALUES),
        ]
    )

    pc.log("Aguardando Traefik ficar pronto...")
    pc.run(["kubectl", "rollout", "status", "daemonset/traefik", "-n", "traefik", "--timeout=300s"])
    pc.info("Traefik pronto.")


def _preload_traefik_image() -> None:
    """Pré-carrega a imagem do Traefik no nó kind pra evitar timeout no --wait.
    Best-effort: qualquer falha aqui não deve interromper o setup."""
    try:
        chart_meta = pc.capture(["helm", "show", "chart", "traefik/traefik"])
        values = pc.capture(["helm", "show", "values", "traefik/traefik"])
        if not chart_meta or not values:
            return

        tag_m = re.search(r"^appVersion:\s*(\S+)", chart_meta, re.MULTILINE)
        tag = tag_m.group(1).strip("'\"") if tag_m else ""

        img_block = re.search(r"^image:\s*\n((?:^\s+.+\n?)+)", values, re.MULTILINE)
        registry = repo = ""
        if img_block:
            block = img_block.group(1)
            reg_m = re.search(r"registry:\s*(\S+)", block)
            repo_m = re.search(r"repository:\s*(\S+)", block)
            registry = (reg_m.group(1).strip("'\"") if reg_m else "")
            repo = (repo_m.group(1).strip("'\"") if repo_m else "")

        if not tag or tag.startswith("#") or not repo or repo.startswith("#"):
            return

        full_image = f"{registry}/{repo}:{tag}" if registry and not registry.startswith("#") else f"{repo}:{tag}"
        _preload_image(full_image)
    except Exception as e:  # best-effort
        pc.info(f"Pré-carga da imagem do Traefik pulada ({e}).")


def _preload_image(image: str) -> None:
    """Baixa `image` no host (se necessário) e carrega no nó kind (best-effort)."""
    node = f"{CLUSTER_NAME}-control-plane"

    if not pc.run_ok(["docker", "image", "inspect", image]):
        pc.log(f"Baixando {image}...")
        if not pc.run_ok(["docker", "pull", image]):
            pc.warn(f"Pull de {image} falhou, continuando.")
            return

    img_id = pc.capture(["docker", "image", "inspect", image, "--format", "{{.Id}}"]) or ""
    img_id = img_id.split(":")[-1][:12]
    if img_id:
        node_images = pc.capture(["docker", "exec", node, "crictl", "images"]) or ""
        if img_id in node_images:
            pc.info(f"{image} já presente no nó kind.")
            return

    pc.log(f"Carregando {image} no nó kind...")
    pc.run(["kind", "load", "docker-image", image, "--name", CLUSTER_NAME], check=False)


def preload_dev_infra_images() -> None:
    pc.log("Pré-carregando imagens de infra dev no nó kind...")
    for img in DEV_INFRA_IMAGES:
        _preload_image(img)


# ─── 7. CloudNativePG operator ──────────────────────────────────────────────

def install_cnpg() -> None:
    if pc.run_ok(["kubectl", "get", "deployment", "cnpg-controller-manager", "-n", "cnpg-system"]):
        pc.info("CloudNativePG operator já instalado.")
        return

    pc.log(f"Instalando CloudNativePG v{CNPG_VERSION}...")
    url = (
        "https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/"
        f"release-{CNPG_RELEASE}/releases/cnpg-{CNPG_VERSION}.yaml"
    )
    pc.run(["kubectl", "apply", "--server-side", "-f", url])
    pc.log("Aguardando CloudNativePG controller ficar pronto...")
    pc.run(
        [
            "kubectl", "rollout", "status", "deployment/cnpg-controller-manager",
            "-n", "cnpg-system", "--timeout=120s",
        ]
    )
    pc.info("CloudNativePG pronto.")


# ─── 8-10. Overlay dev + espera infra ───────────────────────────────────────

def apply_dev_overlay() -> None:
    pc.log("Aplicando manifestos de desenvolvimento...")
    pc.run(["kubectl", "apply", "-k", str(DEV_OVERLAY)])


def wait_for_infra() -> None:
    pc.log("Aguardando PostgreSQL (CloudNativePG)...")
    pc.run(
        ["kubectl", "wait", "cluster/postgres", "-n", NAMESPACE, "--for=condition=Ready", "--timeout=300s"]
    )

    pc.log("Aguardando infra (garage, opensearch)...")
    pc.run(["kubectl", "rollout", "status", "deployment/garage", "-n", NAMESPACE, "--timeout=120s"])
    pc.run(["kubectl", "rollout", "status", "statefulset/opensearch", "-n", NAMESPACE, "--timeout=300s"])

    pc.log("Aguardando serviços de aplicação...")
    pc.run(["kubectl", "rollout", "status", "deployment/redis", "-n", NAMESPACE, "--timeout=120s"])
    pc.run(["kubectl", "rollout", "status", "deployment/apache-tika", "-n", NAMESPACE, "--timeout=300s"])


# ─── 11. hosts file ──────────────────────────────────────────────────────────

def check_hosts_file() -> None:
    hosts_path = Path(r"C:\Windows\System32\drivers\etc\hosts") if pc.IS_WINDOWS else Path("/etc/hosts")
    try:
        content = hosts_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        content = ""

    missing = [h for h in HOSTS if h not in content]
    if missing:
        pc.warn("Entradas ausentes no hosts file. Adicione com:")
        pc.warn("  make k8s-local-hosts")
        pc.warn("  ou manualmente adicione ao hosts file:")
        for h in missing:
            pc.warn(f"    127.0.0.1  {h}")
    else:
        pc.info("hosts file já configurado.")


# ─── main ────────────────────────────────────────────────────────────────────

def main() -> None:
    preflight()
    ensure_dependencies()
    validate_dev_overlay_builds("kubectl")
    ensure_cluster()
    install_traefik()
    preload_dev_infra_images()
    install_cnpg()
    apply_dev_overlay()
    wait_for_infra()
    check_hosts_file()

    print()
    pc.log("Setup concluído!")
    print()
    print("  API:       http://api.queridodiario.local")
    print("  Backend:   http://backend-api.queridodiario.local")
    print("  Garage UI: make k8s-local-garage-ui  ->  http://localhost:3909")
    print()
    print("  Outros comandos úteis:")
    print("    make k8s-local-hosts   # adiciona entradas ao hosts file")
    print("    make k8s-local-status  # status dos pods")
    print("    make k8s-local-down    # destroi o cluster")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pc.err("Interrompido pelo usuário.")
    except pc.subprocess.CalledProcessError as e:
        pc.err(f"Comando falhou ({' '.join(e.cmd)}): código {e.returncode}")
