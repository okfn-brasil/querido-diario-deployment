#!/usr/bin/env python3
"""k8s_local_monitoring.py — Monitoramento local (kind): Prometheus, Loki,
Grafana e coletores Alloy (chart grafana/k8s-monitoring) no namespace
`monitoring`. É um alvo separado do `k8s-local-up` (consome memória extra).

Subcomandos:
  up       instala/atualiza (idempotente) os quatro releases Helm + dashboards
  down     desinstala os releases e remove o namespace `monitoring`
  status   pods e releases do namespace `monitoring`
  grafana  port-forward do Grafana em http://localhost:3000

SEGURANÇA: todo comando kubectl/helm é fixado no contexto do kind local
(`--context` / `--kube-context`), nunca no contexto corrente — assim o script
não consegue tocar em outro cluster (ex: produção). Se o contexto não existir,
aborta antes de qualquer ação.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pycommon as pc  # noqa: E402

CLUSTER_NAME = "querido-diario-dev"
KUBE_CONTEXT = f"kind-{CLUSTER_NAME}"
MONITORING_NAMESPACE = "monitoring"

# Versões dos charts (verificadas com `helm search repo --versions`).
PROMETHEUS_VERSION = "29.40.3"   # prometheus-community/prometheus
LOKI_VERSION = "7.5.0"           # grafana/loki
GRAFANA_VERSION = "10.5.15"      # grafana/grafana
# Mesma variável do Makefile (e do release de produção); fallback p/ uso direto.
K8S_MONITORING_VERSION = os.environ.get("GRAFANA_CLOUD_CHART_VERSION") or "4.5.3"

MIN_MEMORY_GIB = 4.0
GRAFANA_PORT = 3000

REPO_ROOT = pc.REPO_ROOT
MON_DIR = REPO_ROOT / "k8s" / "local" / "monitoring"
DASHBOARDS_DIR = MON_DIR / "dashboards"

HELM_REPOS = {
    "prometheus-community": "https://prometheus-community.github.io/helm-charts",
    "grafana": "https://grafana.github.io/helm-charts",
}

# (release, chart, versão, arquivo de valores) — nesta ordem.
RELEASES = [
    ("prometheus", "prometheus-community/prometheus", PROMETHEUS_VERSION, MON_DIR / "prometheus-values.yaml"),
    ("loki", "grafana/loki", LOKI_VERSION, MON_DIR / "loki-values.yaml"),
    ("grafana", "grafana/grafana", GRAFANA_VERSION, MON_DIR / "grafana-values.yaml"),
    ("k8s-monitoring", "grafana/k8s-monitoring", K8S_MONITORING_VERSION, MON_DIR / "values-local.yaml"),
]


# ─── Comandos fixados no contexto ──────────────────────────────────────────

def kubectl_cmd(*args: str) -> list[str]:
    return ["kubectl", "--context", KUBE_CONTEXT, *args]


def helm_cmd(*args: str) -> list[str]:
    return ["helm", "--kube-context", KUBE_CONTEXT, *args]


def _run(cmd: list[str], check: bool = True, input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, input=input, text=True)


def context_exists() -> bool:
    """`kubectl config get-contexts` só lê o kubeconfig local (não fala com cluster)."""
    try:
        res = subprocess.run(
            ["kubectl", "config", "get-contexts", "-o", "name"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False
    return KUBE_CONTEXT in (res.stdout or "").split()


def ensure_context() -> None:
    if not context_exists():
        pc.err(
            f"contexto kubectl '{KUBE_CONTEXT}' não existe. Suba o cluster local antes "
            "(make k8s-local-up). Este script só age nesse contexto, nunca no contexto atual."
        )


# ─── Memória ───────────────────────────────────────────────────────────────

def available_memory_gib() -> float | None:
    """Memória do host Linux (MemAvailable) ou, nos demais SOs, da VM do Docker."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / (1024 * 1024)
    except (OSError, ValueError, IndexError):
        pass
    out = pc.capture(["docker", "info", "--format", "{{.MemTotal}}"])
    try:
        return int(out) / 1024 ** 3 if out else None
    except ValueError:
        return None


def warn_if_low_memory() -> None:
    mem = available_memory_gib()
    if mem is not None and mem < MIN_MEMORY_GIB:
        pc.warn(
            f"Memória disponível baixa ({mem:.1f} GiB < {MIN_MEMORY_GIB:.0f} GiB): o "
            "monitoramento local (Prometheus, Loki, Grafana, Alloy) pode deixar a máquina lenta."
        )


# ─── Dashboards ────────────────────────────────────────────────────────────

def dashboard_configmap(path: Path) -> str:
    """ConfigMap com o label do sidecar do Grafana. O JSON entra como string
    YAML entre aspas (json.dumps gera um escalar YAML válido)."""
    name = "dashboard-" + path.stem
    body = json.dumps(path.read_text(encoding="utf-8"))
    return (
        "apiVersion: v1\n"
        "kind: ConfigMap\n"
        "metadata:\n"
        f"  name: {name}\n"
        f"  namespace: {MONITORING_NAMESPACE}\n"
        "  labels:\n"
        '    grafana_dashboard: "1"\n'
        "data:\n"
        f"  {path.name}: {body}\n"
    )


def apply_dashboards() -> None:
    files = sorted(DASHBOARDS_DIR.glob("*.json"))
    if not files:
        pc.err(f"nenhum dashboard encontrado em {DASHBOARDS_DIR}")
    manifest = "---\n".join(dashboard_configmap(f) for f in files)
    pc.log(f"Aplicando {len(files)} dashboards (ConfigMaps)...")
    _run(kubectl_cmd("apply", "-f", "-"), input=manifest)


# ─── Subcomandos ───────────────────────────────────────────────────────────

def up() -> int:
    for _, _, _, values in RELEASES:
        if not values.exists():
            pc.err(f"Arquivo de valores não encontrado: {values}")
    pc.check_docker()
    pc.ensure_kubectl()
    pc.ensure_helm()
    ensure_context()
    warn_if_low_memory()

    pc.log("Configurando repositórios helm...")
    for name, url in HELM_REPOS.items():
        _run(helm_cmd("repo", "add", name, url, "--force-update"))
    _run(helm_cmd("repo", "update"), check=False)

    # O namespace nasce no primeiro release; os dashboards precisam dele.
    for release, chart, version, values in RELEASES:
        if release == "grafana":
            _run(kubectl_cmd("create", "namespace", MONITORING_NAMESPACE), check=False)
            apply_dashboards()
        pc.log(f"Instalando/atualizando {release} ({chart} {version})...")
        _run(helm_cmd(
            "upgrade", "--install", release, chart,
            "--version", version, "--namespace", MONITORING_NAMESPACE, "--create-namespace",
            "--values", str(values), "--wait", "--timeout", "10m",
        ))

    print()
    pc.log("Monitoramento local pronto.")
    print("  make k8s-local-monitoring-status    # pods do namespace monitoring")
    print("  make k8s-local-monitoring-grafana   # http://localhost:3000 (admin / admin)")
    print("  Explore > Loki: {namespace=\"querido-diario\", container=\"data-processing\"}")
    print()
    return 0


def down() -> int:
    pc.check_docker()
    ensure_context()
    for release, *_ in reversed(RELEASES):
        pc.log(f"Desinstalando {release}...")
        _run(helm_cmd("uninstall", release, "--namespace", MONITORING_NAMESPACE), check=False)
    pc.log(f"Removendo namespace {MONITORING_NAMESPACE}...")
    _run(kubectl_cmd("delete", "namespace", MONITORING_NAMESPACE, "--ignore-not-found"))
    return 0


def status() -> int:
    ensure_context()
    _run(kubectl_cmd("get", "pods", "-n", MONITORING_NAMESPACE, "-o", "wide"), check=False)
    _run(helm_cmd("list", "--namespace", MONITORING_NAMESPACE), check=False)
    return 0


def grafana() -> int:
    ensure_context()
    if pc.port_in_use(GRAFANA_PORT) is True:
        pc.err(f"porta {GRAFANA_PORT} já está em uso.")
    pc.log(f"Grafana em http://localhost:{GRAFANA_PORT} (usuário admin / senha admin). Ctrl+C para sair.")
    try:
        _run(kubectl_cmd("port-forward", "svc/grafana", f"{GRAFANA_PORT}:80", "-n", MONITORING_NAMESPACE))
    except KeyboardInterrupt:
        pass
    return 0


COMMANDS = {"up": up, "down": down, "status": status, "grafana": grafana}


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd not in COMMANDS:
        print("uso: k8s_local_monitoring.py {up|down|status|grafana}", file=sys.stderr)
        return 2
    return COMMANDS[cmd]()


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        pc.err("Interrompido pelo usuário.")
    except subprocess.CalledProcessError as e:
        pc.err(f"Comando falhou ({' '.join(map(str, e.cmd))}): código {e.returncode}")
