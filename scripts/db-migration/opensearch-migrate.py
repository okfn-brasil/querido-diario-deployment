#!/usr/bin/env python3
"""Migra o índice OpenSearch do ambiente antigo para o Revoada.

Faz scan+bulk client-side (em vez de remote-reindex no servidor), porque a
StatefulSet nova do OpenSearch não tem `reindex.remote.whitelist` configurado
(k8s/overlays/production/opensearch/statefulset.yaml só define env vars, sem
opensearch.yml customizado) e o plugin de segurança está habilitado no
destino mas provavelmente não na origem — auth diferente nos dois lados.

Pré-requisitos:
    pip install opensearch-py
    kubectl port-forward svc/opensearch 9200:9200 -n querido-diario &

Variáveis de ambiente:
    OLD_OPENSEARCH_HOST      (ex: https://search.queridodiario.ok.org.br ou http://localhost:9200)
    OLD_OPENSEARCH_USER      (opcional, se a origem não tiver auth deixe vazio)
    OLD_OPENSEARCH_PASSWORD  (opcional)
    OLD_OPENSEARCH_INDEX     (default: queridodiario)
    NEW_OPENSEARCH_HOST      (default: https://localhost:9200 — via port-forward)
    NEW_OPENSEARCH_USER      (default: admin)
    NEW_OPENSEARCH_PASSWORD  (obrigatório — pegue do secret app-secret, ver README.md)
    NEW_OPENSEARCH_INDEX     (default: queridodiario)

Uso:
    python3 opensearch-migrate.py                  # migração completa
    python3 opensearch-migrate.py --dry-run         # só conta documentos, não escreve
    python3 opensearch-migrate.py --resume-from 50000  # retoma pulando os N primeiros docs
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk, scan

CHECKPOINT_FILE = os.path.join(os.path.dirname(__file__), ".opensearch-migrate-checkpoint")


def env(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        sys.exit(f"Erro: variável de ambiente {name} é obrigatória.")
    return value or ""


def make_client(host: str, user: str, password: str, verify_certs: bool) -> OpenSearch:
    kwargs: dict = {"hosts": [host], "timeout": 60}
    if user:
        kwargs["http_auth"] = (user, password)
    if host.startswith("https"):
        kwargs["verify_certs"] = verify_certs
        kwargs["ssl_show_warn"] = False
    return OpenSearch(**kwargs)


def load_checkpoint() -> int:
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return int(f.read().strip() or 0)
    return 0


def save_checkpoint(n: int) -> None:
    with open(CHECKPOINT_FILE, "w") as f:
        f.write(str(n))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="só conta documentos na origem/destino, não escreve nada")
    parser.add_argument("--resume-from", type=int, default=None, help="pula os N primeiros documentos do scan (retomar após interrupção)")
    parser.add_argument("--chunk-size", type=int, default=500, help="tamanho do lote no bulk insert (default: 500)")
    args = parser.parse_args()

    old_host = env("OLD_OPENSEARCH_HOST", required=True)
    old_user = env("OLD_OPENSEARCH_USER")
    old_pass = env("OLD_OPENSEARCH_PASSWORD")
    old_index = env("OLD_OPENSEARCH_INDEX", "queridodiario")

    new_host = env("NEW_OPENSEARCH_HOST", "https://localhost:9200")
    new_user = env("NEW_OPENSEARCH_USER", "admin")
    new_pass = env("NEW_OPENSEARCH_PASSWORD", required=not args.dry_run)
    new_index = env("NEW_OPENSEARCH_INDEX", "queridodiario")

    old_client = make_client(old_host, old_user, old_pass, verify_certs=True)
    new_client = make_client(new_host, new_user, new_pass, verify_certs=False)

    old_count = old_client.count(index=old_index)["count"]
    print(f"[info] Índice origem '{old_index}' em {old_host}: {old_count} documentos")

    if not args.dry_run and not new_client.indices.exists(index=new_index):
        print(f"[warn] Índice destino '{new_index}' não existe em {new_host} — será criado com mapping default no primeiro bulk.")

    if args.dry_run:
        if new_client.indices.exists(index=new_index):
            new_count = new_client.count(index=new_index)["count"]
            print(f"[info] Índice destino '{new_index}' em {new_host}: {new_count} documentos")
        print("[info] dry-run: nada foi escrito.")
        return

    resume_from = args.resume_from if args.resume_from is not None else load_checkpoint()
    if resume_from:
        print(f"[info] Retomando a partir do documento #{resume_from}")

    def generate_actions():
        # scroll="30m": o default do scan() (~5m) expira antes de terminar
        # de pular os primeiros N documentos ao retomar de um
        # --resume-from grande — scan() não faz seek, ele itera e descarta
        # localmente, então reprocessar centenas de milhares de docs pode
        # facilmente passar do TTL padrão do scroll context na origem
        # (aconteceu na prática: "No search context found for id ...").
        for i, hit in enumerate(scan(old_client, index=old_index, query={"query": {"match_all": {}}}, scroll="30m")):
            if i < resume_from:
                continue
            yield {
                "_index": new_index,
                "_id": hit["_id"],
                "_source": hit["_source"],
            }

    start = time.time()
    migrated = 0
    errors = 0
    last_checkpoint = resume_from

    try:
        for ok, item in bulk(new_client, generate_actions(), chunk_size=args.chunk_size, raise_on_error=False, stats_only=False):
            migrated += 1
            if not ok:
                errors += 1
                print(f"[warn] Falha ao indexar: {item}")
            if migrated % 5000 == 0:
                last_checkpoint = resume_from + migrated
                save_checkpoint(last_checkpoint)
                elapsed = time.time() - start
                print(f"[info] {last_checkpoint}/{old_count} migrados ({elapsed:.0f}s, {errors} erros)")
    except KeyboardInterrupt:
        save_checkpoint(resume_from + migrated)
        print(f"\n[warn] Interrompido. Checkpoint salvo em {resume_from + migrated}. "
              f"Rode de novo com --resume-from {resume_from + migrated} (ou deixe sem flag, o checkpoint é lido automaticamente).")
        sys.exit(1)
    except Exception as exc:
        # Qualquer outra falha (ex: conexão caiu no meio de uma migração
        # longa) também salva o checkpoint antes de propagar — sem isso,
        # só Ctrl+C manual preservava o progresso, e uma queda de rede
        # real perderia tudo desde o último checkpoint automático (a cada
        # 5000 docs).
        save_checkpoint(resume_from + migrated)
        print(f"\n[erro] Falhou: {exc}")
        print(f"[warn] Checkpoint salvo em {resume_from + migrated}. Rode de novo (mesmo comando) para retomar.")
        sys.exit(1)

    save_checkpoint(resume_from + migrated)
    new_count = new_client.count(index=new_index)["count"]
    print(f"\n[info] Migração concluída: {migrated} documentos processados, {errors} erros.")
    print(f"[info] Contagem final — origem: {old_count} | destino: {new_count}")
    if new_count != old_count:
        print("[warn] Contagens diferentes! Verifique duplicatas, deleções concorrentes na origem, ou erros acima.")
        sys.exit(1)
    else:
        print("[info] Contagens batem. OK para prosseguir.")
        os.remove(CHECKPOINT_FILE) if os.path.exists(CHECKPOINT_FILE) else None


if __name__ == "__main__":
    main()
