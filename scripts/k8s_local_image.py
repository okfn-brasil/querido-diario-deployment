#!/usr/bin/env python3
"""k8s_local_image.py — Carrega uma imagem `:local` no cluster kind e aponta os
workloads informados para ela.

Uso: k8s_local_image.py <repositorio-da-imagem> <kind/nome> [<kind/nome> ...]
  ex.: k8s_local_image.py ghcr.io/okfn-brasil/querido-diario-api deployment/api

Além de trocar a tag, força `imagePullPolicy: IfNotPresent`: os workloads do
overlay dev nascem com `:latest`, o que faz o Kubernetes assumir `Always` e
tentar baixar `:local` do registry (ImagePullBackOff) em vez de usar a imagem
carregada no nó.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pycommon as pc  # noqa: E402

CLUSTER_NAME = "querido-diario-dev"
NAMESPACE = "querido-diario"
ROLLOUT_TIMEOUT = "180s"


def _pod_spec_path(kind: str) -> list[str]:
    if kind == "cronjob":
        return ["spec", "jobTemplate", "spec", "template", "spec"]
    return ["spec", "template", "spec"]


def _build_patch(workload: str, repo: str, image: str) -> dict | None:
    """Monta o patch só com os containers (e initContainers) que usam `repo`."""
    kind = workload.split("/", 1)[0].lower()
    raw = pc.capture(["kubectl", "get", workload, "-n", NAMESPACE, "-o", "json"])
    if not raw:
        pc.err(f"Não encontrei {workload} no namespace {NAMESPACE} — o cluster local está de pé?")

    pod_spec = json.loads(raw)
    path = _pod_spec_path(kind)
    for key in path:
        pod_spec = pod_spec[key]

    patch_spec: dict = {}
    for field in ("initContainers", "containers"):
        matching = [
            {"name": c["name"], "image": image, "imagePullPolicy": "IfNotPresent"}
            for c in pod_spec.get(field, [])
            if c["image"].rsplit(":", 1)[0] == repo
        ]
        if matching:
            patch_spec[field] = matching
    if not patch_spec:
        return None

    patch: dict = patch_spec
    for key in reversed(path):
        patch = {key: patch}
    return patch


def main() -> None:
    if len(sys.argv) < 3:
        pc.err("Uso: k8s_local_image.py <repositorio-da-imagem> <kind/nome> [<kind/nome> ...]")
    repo, workloads = sys.argv[1], sys.argv[2:]
    image = f"{repo}:local"

    pc.log(f"Carregando {image} no cluster kind '{CLUSTER_NAME}'...")
    pc.run(["kind", "load", "docker-image", image, "--name", CLUSTER_NAME])

    deployments = []
    for workload in workloads:
        patch = _build_patch(workload, repo, image)
        if patch is None:
            pc.warn(f"{workload} não tem container usando {repo} — pulando.")
            continue
        pc.run(["kubectl", "patch", workload, "-n", NAMESPACE, "--type=strategic", "-p", json.dumps(patch)])
        if workload.lower().startswith("deployment/"):
            deployments.append(workload)

    # Mesmo nome de tag a cada build: sem restart os pods continuam na imagem antiga.
    for deployment in deployments:
        pc.run(["kubectl", "rollout", "restart", deployment, "-n", NAMESPACE])
    for deployment in deployments:
        pc.run(["kubectl", "rollout", "status", deployment, "-n", NAMESPACE, f"--timeout={ROLLOUT_TIMEOUT}"])

    pc.info(f"{image} em uso por: {', '.join(workloads)}")


if __name__ == "__main__":
    try:
        main()
    except pc.subprocess.CalledProcessError as e:
        pc.err(f"Comando falhou ({' '.join(e.cmd)}): código {e.returncode}")
