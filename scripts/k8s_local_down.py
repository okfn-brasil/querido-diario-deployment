#!/usr/bin/env python3
"""k8s_local_down.py — Destroi o cluster kind local do Querido Diário.

Substitui o antigo k8s/local/teardown.sh (bash).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pycommon as pc  # noqa: E402

CLUSTER_NAME = "querido-diario-dev"


def main() -> None:
    if not pc.which("kind"):
        pc.warn("kind não encontrado. Nada a fazer.")
        return

    existing = pc.capture(["kind", "get", "clusters"]) or ""
    if CLUSTER_NAME not in existing.splitlines():
        pc.warn(f"Cluster '{CLUSTER_NAME}' não existe. Nada a fazer.")
        return

    pc.log(f"Destruindo cluster '{CLUSTER_NAME}'...")
    pc.run(["kind", "delete", "cluster", "--name", CLUSTER_NAME])

    pc.log("Cluster removido. Dados locais (PVCs) foram destruídos junto com o cluster.")
    hosts_path = r"C:\Windows\System32\drivers\etc\hosts" if pc.IS_WINDOWS else "/etc/hosts"
    pc.warn(f"Para remover as entradas do hosts file, edite {hosts_path} manualmente")
    pc.warn("e remova as linhas com queridodiario.local")


if __name__ == "__main__":
    main()
