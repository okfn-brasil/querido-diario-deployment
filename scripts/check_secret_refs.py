#!/usr/bin/env python3
"""check_secret_refs.py — Valida que toda chave de Secret/ConfigMap
referenciada nos manifestos (secretKeyRef/configMapKeyRef) é de fato
provida em produção (.github/workflows/deploy.yml) e em dev
(k8s/overlays/dev/**), sem precisar de acesso a nenhum cluster.

Existe porque QD_DATA_DB_HOST/POSTGRES_COMPANIES_HOST eram referenciadas
pelos manifestos mas nunca setadas pelo deploy.yml — produção ficou dias
em CreateContainerConfigError até isso ser encontrado manualmente.

Uso:
    pip install pyyaml   # única dependência externa deste script — os
                          # outros scripts/*.py são stdlib-only, mas parsing
                          # de YAML robusto sem PyYAML não é viável
    python3 scripts/check_secret_refs.py
Saída: 0 se tudo consistente, 1 e lista de problemas caso contrário.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
K8S_BASE = REPO_ROOT / "k8s" / "base"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"

# Manifestos base onde procurar secretKeyRef/configMapKeyRef.
MANIFEST_GLOBS = ["*/deployment.yaml", "*/cronjob.yaml"]

# name do Secret/ConfigMap -> arquivos que devem conter TODAS as chaves
# referenciadas (fonte de verdade por ambiente).
SECRET_SOURCES = {
    "app-secret": {
        "template": K8S_BASE / "secret-app.yaml",
        "dev": REPO_ROOT / "k8s" / "overlays" / "dev" / "patch-secret-dev.yaml",
    },
    "postgres-credentials": {
        "template": K8S_BASE / "postgres" / "credentials-secret.yaml",
        "dev": REPO_ROOT / "k8s" / "overlays" / "dev" / "infra" / "postgres-credentials-dev.yaml",
    },
}

CONFIGMAP_SOURCES = {
    "app-config": K8S_BASE / "configmap-app.yaml",
}


def find_refs(data, path="") -> list[tuple[str, str, str, str]]:
    """Percorre a árvore YAML e retorna (ref_kind, name, key, path) pra
    cada secretKeyRef/configMapKeyRef encontrado."""
    refs = []
    if isinstance(data, dict):
        for ref_kind in ("secretKeyRef", "configMapKeyRef"):
            if ref_kind in data and isinstance(data[ref_kind], dict):
                name = data[ref_kind].get("name")
                key = data[ref_kind].get("key")
                if name and key:
                    refs.append((ref_kind, name, key, path))
        for k, v in data.items():
            refs.extend(find_refs(v, f"{path}.{k}" if path else k))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            refs.extend(find_refs(item, f"{path}[{i}]"))
    return refs


def collect_manifest_refs() -> list[tuple[str, str, str, str]]:
    refs = []
    for pattern in MANIFEST_GLOBS:
        for manifest in K8S_BASE.glob(pattern):
            for doc in yaml.safe_load_all(manifest.read_text(encoding="utf-8")):
                if doc:
                    refs.extend(find_refs(doc, str(manifest.relative_to(REPO_ROOT))))
    return refs


def keys_from_secret_yaml(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        if not doc or doc.get("kind") != "Secret":
            continue
        keys |= set((doc.get("stringData") or {}).keys())
        keys |= set((doc.get("data") or {}).keys())
    return keys


def keys_from_configmap_yaml(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
        if not doc or doc.get("kind") != "ConfigMap":
            continue
        keys |= set((doc.get("data") or {}).keys())
    return keys


def keys_from_deploy_workflow(secret_name: str) -> set[str] | None:
    """Extrai as chaves de --from-literal=KEY=... do bloco
    `kubectl create secret generic <secret_name>` em deploy.yml.
    Retorna None se o workflow não existir ou não criar esse secret."""
    if not DEPLOY_WORKFLOW.exists():
        return None
    text = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    block_re = re.compile(
        rf"kubectl create secret generic {re.escape(secret_name)}\b(.*?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )
    match = block_re.search(text)
    if not match:
        return None
    return set(re.findall(r"--from-literal=([A-Za-z0-9_]+)=", match.group(1)))


def main() -> int:
    manifest_refs = collect_manifest_refs()
    problems: list[str] = []

    referenced_secret_names = {name for kind, name, _, _ in manifest_refs if kind == "secretKeyRef"}
    referenced_configmap_names = {name for kind, name, _, _ in manifest_refs if kind == "configMapKeyRef"}

    for secret_name in sorted(referenced_secret_names):
        sources = SECRET_SOURCES.get(secret_name)
        refs_for_secret = [(k, p) for kind, n, k, p in manifest_refs if kind == "secretKeyRef" and n == secret_name]

        if sources is None:
            problems.append(
                f"Secret '{secret_name}' é referenciado mas não está mapeado em "
                f"SECRET_SOURCES deste script — adicione um mapeamento pra validá-lo."
            )
            continue

        template_keys = keys_from_secret_yaml(sources["template"])
        dev_keys = keys_from_secret_yaml(sources["dev"])
        deploy_keys = keys_from_deploy_workflow(secret_name)

        for key, ref_path in refs_for_secret:
            if key not in template_keys:
                problems.append(
                    f"{ref_path}: secretKeyRef '{secret_name}.{key}' não está em "
                    f"{sources['template'].relative_to(REPO_ROOT)} (template desatualizado)."
                )
            if key not in dev_keys:
                problems.append(
                    f"{ref_path}: secretKeyRef '{secret_name}.{key}' não está em "
                    f"{sources['dev'].relative_to(REPO_ROOT)} (overlay dev vai quebrar)."
                )
            if deploy_keys is not None and key not in deploy_keys:
                problems.append(
                    f"{ref_path}: secretKeyRef '{secret_name}.{key}' não é setada por "
                    f"'kubectl create secret generic {secret_name}' em "
                    f"{DEPLOY_WORKFLOW.relative_to(REPO_ROOT)} (produção vai quebrar)."
                )

    for configmap_name in sorted(referenced_configmap_names):
        source = CONFIGMAP_SOURCES.get(configmap_name)
        refs_for_cm = [(k, p) for kind, n, k, p in manifest_refs if kind == "configMapKeyRef" and n == configmap_name]

        if source is None:
            problems.append(
                f"ConfigMap '{configmap_name}' é referenciado mas não está mapeado em "
                f"CONFIGMAP_SOURCES deste script — adicione um mapeamento pra validá-lo."
            )
            continue

        available = keys_from_configmap_yaml(source)
        for key, ref_path in refs_for_cm:
            if key not in available:
                problems.append(
                    f"{ref_path}: configMapKeyRef '{configmap_name}.{key}' não está em "
                    f"{source.relative_to(REPO_ROOT)}."
                )

    if problems:
        print(f"Encontrados {len(problems)} problema(s):\n")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"OK — {len(manifest_refs)} referências de secretKeyRef/configMapKeyRef conferem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
