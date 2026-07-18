#!/usr/bin/env python3
"""help.py — Imprime a ajuda do Makefile.

Substitui o antigo bloco `grep | awk | sort` (não disponível em cmd/PowerShell
nativos do Windows).
"""
from __future__ import annotations

SECTIONS = [
    ("Inicio rapido", [
        ("Kubernetes (local)", "make k8s-local-up"),
        ("Kubernetes (prod)", "make k8s-apply-prod"),
    ]),
    ("Kubernetes local (kind)", [
        ("make k8s-local-up", "cria cluster kind + sobe ambiente dev"),
        ("make k8s-local-down", "destroi o cluster kind"),
        ("make k8s-local-status", "status dos pods"),
        ("make k8s-local-hosts", "adiciona entradas ao hosts file"),
        ("make k8s-local-garage-ui", "port-forward Garage UI -> localhost:3909"),
        ("make k8s-local-data-processing", "executa data-processing manualmente"),
    ]),
    ("Kubernetes (kustomize)", [
        ("make k8s-build-dev", "dry-run overlay dev"),
        ("make k8s-build-prod", "dry-run overlay producao"),
        ("make k8s-apply-dev", "aplica overlay dev no cluster atual"),
        ("make k8s-apply-prod", "aplica overlay producao no cluster atual"),
        ("make k8s-diff-dev", "diff entre cluster e overlay dev"),
        ("make k8s-diff-prod", "diff entre cluster e overlay producao"),
    ]),
    ("Raspadores (execução local)", [
        ("make spider-setup", "cria venv e instala deps (uma vez)"),
        ("make spider-list", "lista todos os spiders"),
        ("make run-spider SPIDER=<nome>", ""),
        ("make run-spider SPIDER=<nome> START=YYYY-MM-DD END=YYYY-MM-DD", ""),
    ]),
    ("Build local (com cache remoto)", [
        ("make build-api", "API"),
        ("make build-backend", "Backend/Celery"),
        ("make build-data-processing-base", "base do Data Processing (deps Python)"),
        ("make build-data-processing", "Data Processing"),
        ("make build-tika", "Apache Tika"),
        ("make build-frontend", "Frontend"),
        ("make build-all", "todas as imagens acima"),
    ]),
]

VARS = [
    ("QD_DIR=<path>", "padrao: ../querido-diario"),
    ("API_DIR=<path>", "padrao: ../querido-diario-api"),
    ("BACKEND_DIR=<path>", "padrao: ../querido-diario-backend/app"),
    ("DATA_PROCESSING_DIR=<path>", "padrao: ../querido-diario-data-processing"),
    ("FRONTEND_DIR=<path>", "padrao: ../querido-diario-frontend"),
    ("SPIDER=<nome>", "nome do spider a executar"),
    ("START=YYYY-MM-DD", "data de inicio do raspador (opcional)"),
    ("END=YYYY-MM-DD", "data de fim do raspador (opcional)"),
    ("PYTHON=<binario>", "interpretador usado pelos scripts (padrao: python3)"),
]


def main() -> None:
    print("Comandos disponíveis: make <target>")
    for title, items in SECTIONS:
        print()
        print(f"{title}:")
        for name, desc in items:
            if desc:
                print(f"  {name:<45} {desc}")
            else:
                print(f"  {name}")
    print()
    print("Variaveis:")
    for name, desc in VARS:
        print(f"  {name:<30} {desc}")


if __name__ == "__main__":
    main()
