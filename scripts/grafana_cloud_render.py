#!/usr/bin/env python3
"""grafana_cloud_render.py — Renderiza o chart grafana/k8s-monitoring em YAML
estático, para que o Grafana Cloud seja aplicado via `kubectl apply -k` junto
com o resto de produção. Gera dois arquivos em k8s/monitoring/grafana-cloud/:

  - cluster-scoped.yaml: CRD, ClusterRoles/Bindings e webhooks. Exige permissão
    de cluster; é aplicado uma vez pelo admin (`kubectl apply -f`) e NÃO entra
    no kustomization.
  - manifests.yaml: o restante (namespaced), aplicado por `make k8s-apply-prod`.

Usa `helm template --include-crds` e descarta os Jobs de hook do Helm
(add-finalizer / remove-alloy-and-finalizer), que só fazem sentido com
`helm install/uninstall`. Rode de novo ao mudar values.yaml ou a versão do chart.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pycommon as pc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "k8s" / "monitoring" / "grafana-cloud"
CHART_VERSION = os.environ.get("GRAFANA_CLOUD_CHART_VERSION", "4.5.3")
NAMESPACE = "querido-diario"


def is_hook(doc: str) -> bool:
    return bool(re.search(r"^\s*[\"']?helm\.sh/hook[\"']?:", doc, re.MULTILINE))


CLUSTER_SCOPED_KINDS = {
    "CustomResourceDefinition",
    "ClusterRole",
    "ClusterRoleBinding",
    "MutatingWebhookConfiguration",
    "ValidatingWebhookConfiguration",
}


def kind_of(doc: str) -> str:
    m = re.search(r"^kind:\s*(\S+)", doc, re.MULTILINE)
    return m.group(1) if m else ""


def write(name: str, docs: list[str]) -> None:
    header = (
        "# GERADO por scripts/grafana_cloud_render.py (`make grafana-cloud-render`)\n"
        f"# a partir de grafana/k8s-monitoring {CHART_VERSION} + values.yaml. Não editar à mão.\n"
    )
    (OUT_DIR / name).write_text(header + "\n---\n".join([""] + docs) + "\n")


def main() -> None:
    pc.run(["helm", "repo", "add", "grafana", "https://grafana.github.io/helm-charts"])
    pc.run(["helm", "repo", "update", "grafana"])
    rendered = pc.capture(
        [
            "helm", "template", "grafana-cloud", "grafana/k8s-monitoring",
            "--version", CHART_VERSION, "--namespace", NAMESPACE,
            "--values", str(OUT_DIR / "values.yaml"), "--include-crds",
        ]
    )
    if not rendered:
        pc.err("helm template não retornou saída")
        sys.exit(1)

    docs = [d.strip("\n") for d in re.split(r"^---\s*$", rendered, flags=re.MULTILINE)]
    kept = [d for d in docs if re.search(r"^kind:", d, re.MULTILINE) and not is_hook(d)]
    cluster = [d for d in kept if kind_of(d) in CLUSTER_SCOPED_KINDS]
    namespaced = [d for d in kept if kind_of(d) not in CLUSTER_SCOPED_KINDS]
    write("cluster-scoped.yaml", cluster)
    write("manifests.yaml", namespaced)
    pc.info(
        f"{len(cluster)} recursos de cluster, {len(namespaced)} namespaced "
        f"({len(docs) - len(kept)} descartados)"
    )

if __name__ == "__main__":
    main()
