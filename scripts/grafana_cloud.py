#!/usr/bin/env python3
"""grafana_cloud.py — Grafana Cloud (chart grafana/k8s-monitoring) via `helm template | kubectl apply`.

Não existe release Helm: o chart é só renderizado e os manifestos são aplicados
(o `helm install` roda `lookup` de Nodes/Namespace, que a ServiceAccount de
deploy, restrita ao namespace, não pode fazer; ver ADR-009).

Subcomandos:
  check    renderiza o chart e falha se algum recurso exigir escopo de cluster
           (a ServiceAccount de deploy não pode criá-los).
  render   imprime o YAML renderizado (`helm template --include-crds`).
  diff     `helm template | kubectl diff` (exit 1 do kubectl = há diferenças, não é erro).
  install  check + secret grafana-cloud-credentials + `helm template | kubectl apply`
           (sem prune: objetos que o chart deixar de renderizar não são removidos).
  status   `kubectl get` dos objetos do deploy (linhas com `grafana-cloud`).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pycommon as pc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VALUES = ROOT / "k8s" / "monitoring" / "grafana-cloud" / "values.yaml"
DEFAULT_CHART_VERSION = "4.5.3"  # fallback p/ uso direto; o Makefile sempre exporta a variável


def chart_version_from_env(env) -> str:
    return env.get("GRAFANA_CLOUD_CHART_VERSION") or DEFAULT_CHART_VERSION


CHART_VERSION = chart_version_from_env(os.environ)
RELEASE = "grafana-cloud"
NAMESPACE = "querido-diario"
CHART = "grafana/k8s-monitoring"
SECRET = "grafana-cloud-credentials"

CLUSTER_SCOPED_KINDS = frozenset(
    {
        "CustomResourceDefinition",
        "ClusterRole",
        "ClusterRoleBinding",
        "MutatingWebhookConfiguration",
        "ValidatingWebhookConfiguration",
        "Namespace",
        "PriorityClass",
        "StorageClass",
    }
)


def _metadata_name(doc: str) -> str | None:
    """`metadata.name`: `name:` no nível de indentação direto de `metadata:`."""
    m = re.search(r"^metadata:[ \t]*\n", doc, re.MULTILINE)
    if not m:
        return None
    indent = None
    for line in doc[m.end():].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cur = line[: len(line) - len(line.lstrip())]
        if indent is None:
            if not cur:
                return None
            indent = cur
        if cur == indent:
            nm = re.match(r"name:\s*[\"']?([^\s\"']+)", line.lstrip())
            if nm:
                return nm.group(1)
        elif not cur.startswith(indent):
            return None
    return None


def cluster_scoped_resources(manifest_yaml: str) -> list[str]:
    """Lista `Kind/name` dos documentos de escopo de cluster no YAML."""
    found: list[str] = []
    for doc in re.split(r"^---\s*$", manifest_yaml, flags=re.MULTILINE):
        km = re.search(r"^kind:\s*[\"']?(\S+?)[\"']?\s*$", doc, re.MULTILINE)
        if not km or km.group(1) not in CLUSTER_SCOPED_KINDS:
            continue
        found.append(f"{km.group(1)}/{_metadata_name(doc) or '?'}")
    return found


class HelmError(RuntimeError):
    pass


def _captured(cmd: list[str]) -> subprocess.CompletedProcess:
    """Roda um comando capturando a saída; falha com mensagem clara e o stderr."""
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise HelmError(f"comando não encontrado: {cmd[0]} ({e})") from e
    except subprocess.CalledProcessError as e:
        raise HelmError(f"falhou: {' '.join(cmd[:3])} (exit {e.returncode})\n{e.stderr or ''}".rstrip()) from e


def _template_args(chart_version: str, values: Path) -> list[str]:
    return [
        "helm", "template", RELEASE, CHART, "--version", chart_version,
        "--namespace", NAMESPACE, "--values", str(values), "--include-crds",
    ]


def render(chart_version: str, values: Path) -> str:
    # stdout reservado ao YAML (render é usado em pipe): a saída do helm repo é descartada.
    _captured(["helm", "repo", "add", "grafana", "https://grafana.github.io/helm-charts"])
    _captured(["helm", "repo", "update", "grafana"])
    return _captured(_template_args(chart_version, values)).stdout


def credentials_secret_exists() -> bool:
    return pc.run_ok(["kubectl", "get", "secret", SECRET, "-n", NAMESPACE])


def check() -> int:
    found = cluster_scoped_resources(render(CHART_VERSION, VALUES))
    if found:
        print("[erro]  o deploy exigiria escopo de cluster:", file=sys.stderr)
        for r in found:
            print(f"  {r}", file=sys.stderr)
        return 1
    pc.info("sem recursos de escopo de cluster")
    return 0


def _kubectl_with_stdin(args: list[str], manifest: str) -> int:
    """Roda kubectl com o manifesto no stdin; binário ausente vira HelmError."""
    try:
        return subprocess.run(["kubectl", *args], input=manifest, text=True).returncode
    except FileNotFoundError as e:
        raise HelmError(f"comando não encontrado: kubectl ({e})") from e


def diff() -> int:
    manifest = render(CHART_VERSION, VALUES)
    # kubectl diff: 0 = sem diferenças, 1 = há diferenças (não é falha), >1 = erro.
    rc = _kubectl_with_stdin(["diff", "-n", NAMESPACE, "-f", "-"], manifest)
    return 0 if rc in (0, 1) else rc


def install() -> int:
    rc = check()
    if rc:
        return rc
    if not credentials_secret_exists():
        print(
            f"Crie o secret antes (valores reais, nunca versionar):\n"
            f"kubectl create secret generic {SECRET} -n {NAMESPACE} \\\n"
            "  --from-literal=username='<ID-DA-INSTANCIA-FLEET-MANAGEMENT>' \\\n"
            "  --from-literal=password='<TOKEN-GRAFANA-CLOUD>'",
            file=sys.stderr,
        )
        pc.err(f"secret {SECRET} não existe no namespace {NAMESPACE}")  # sai com 1
        return 1
    return _kubectl_with_stdin(["apply", "-n", NAMESPACE, "-f", "-"], render(CHART_VERSION, VALUES))


def status() -> int:
    out = _captured(["kubectl", "get", "alloy,daemonset,deployment,service,pod", "-n", NAMESPACE]).stdout
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if i == 0 or "grafana-cloud" in line:
            print(line)
    return 0


COMMANDS = {"check": check, "diff": diff, "install": install, "status": status}


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "render":
            sys.stdout.write(render(CHART_VERSION, VALUES))
            return 0
        if cmd in COMMANDS:
            return COMMANDS[cmd]()
    except HelmError as e:
        print(f"[erro]  {e}", file=sys.stderr)
        return 1
    print("uso: grafana_cloud.py {check|render|diff|install|status}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
