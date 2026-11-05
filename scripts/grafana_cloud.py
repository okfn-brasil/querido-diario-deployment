#!/usr/bin/env python3
"""grafana_cloud.py — Release Helm do Grafana Cloud (chart grafana/k8s-monitoring).

Subcomandos:
  check   renderiza o chart e falha se algum recurso exigir escopo de cluster
          (a ServiceAccount de deploy não pode criá-los).
  render  imprime o YAML renderizado (`helm template --include-crds`).
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
CHART_VERSION = os.environ.get("GRAFANA_CLOUD_CHART_VERSION", "4.5.3")
RELEASE = "grafana-cloud"
NAMESPACE = "querido-diario"

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


def cluster_scoped_resources(manifest_yaml: str) -> list[str]:
    """Lista `Kind/name` dos documentos de escopo de cluster no YAML."""
    found: list[str] = []
    for doc in re.split(r"^---\s*$", manifest_yaml, flags=re.MULTILINE):
        km = re.search(r"^kind:\s*[\"']?(\S+?)[\"']?\s*$", doc, re.MULTILINE)
        if not km or km.group(1) not in CLUSTER_SCOPED_KINDS:
            continue
        nm = re.search(r"^metadata:\s*\n(?:[ \t]+\S.*\n)*?[ \t]+name:\s*[\"']?([^\s\"']+)", doc, re.MULTILINE)
        found.append(f"{km.group(1)}/{nm.group(1) if nm else '?'}")
    return found


def render(chart_version: str, values: Path) -> str:
    # stdout reservado ao YAML (render é usado em pipe): saída do helm repo vai para stderr.
    pc.run(["helm", "repo", "add", "grafana", "https://grafana.github.io/helm-charts"], stdout=sys.stderr)
    pc.run(["helm", "repo", "update", "grafana"], stdout=sys.stderr)
    out = subprocess.run(
        [
            "helm", "template", RELEASE, "grafana/k8s-monitoring",
            "--version", chart_version, "--namespace", NAMESPACE,
            "--values", str(values), "--include-crds",
        ],
        check=True, capture_output=True, text=True,
    )
    return out.stdout


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "render":
        sys.stdout.write(render(CHART_VERSION, VALUES))
        return 0
    if cmd == "check":
        found = cluster_scoped_resources(render(CHART_VERSION, VALUES))
        if found:
            print("[erro]  o release exigiria escopo de cluster:", file=sys.stderr)
            for r in found:
                print(f"  {r}", file=sys.stderr)
            return 1
        pc.info("sem recursos de escopo de cluster")
        return 0
    print("uso: grafana_cloud.py {check|render}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
