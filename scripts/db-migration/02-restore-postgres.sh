#!/usr/bin/env bash
# 02-restore-postgres.sh — restaura os dumps gerados por 01-dump-postgres.sh
# nos bancos do cluster CNPG (Revoada).
#
# O pg_restore roda DE DENTRO do cluster, num pod temporário que conecta
# direto em postgres-rw via DNS interno — não via kubectl port-forward.
# port-forward não é confiável pra transferências longas/grandes: uma
# instabilidade de rede na VPN/CNI derruba a stream inteira sem retry
# automático (já aconteceu num restore real: "connection reset by peer"
# no meio da transferência, deixando um banco com restore parcial). Só a
# cópia inicial do dump (kubectl cp) precisa sobreviver — uma
# transferência de arquivo simples e reexecutável, bem mais robusta que
# uma conexão Postgres ao vivo com --jobs=4 através de um túnel.
#
# Pré-requisitos:
#   - kubectl configurado (KUBECONFIG apontando pro Revoada) e WireGuard ativo
#   - dumps já gerados em ./dumps/<old_db>-latest.dump (por 01-dump-postgres.sh)
#
# Uso:
#   ./02-restore-postgres.sh              # restaura os 3 bancos
#   DRY_RUN=true ./02-restore-postgres.sh # mostra os comandos sem executar
#
# Por padrão o script recusa restaurar sobre um banco que já tenha tabelas
# (evita sobrescrever silenciosamente). Use --force pra pular essa checagem
# (ex.: re-rodando após um restore parcial que você sabe que precisa ser
# limpo manualmente antes — DROP SCHEMA public CASCADE; CREATE SCHEMA
# public; no banco afetado. --force não limpa nada sozinho).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

FORCE=false
[ "${1:-}" = "--force" ] && FORCE=true

NAMESPACE="${QD_NAMESPACE:-querido-diario}"
PG_SVC="${QD_PG_SERVICE:-postgres-rw}"
HELPER_POD="${QD_RESTORE_HELPER_POD:-pg-restore-helper}"
HELPER_IMAGE="${QD_RESTORE_HELPER_IMAGE:-postgres:15}"

command -v kubectl >/dev/null 2>&1 || err "kubectl não encontrado."

# old_db:new_db
DATABASES=(
    "queridodiariodb:queridodiario"
    "queridodiariobackend:backend"
    "qd_receita:companies"
)

info "Lendo credenciais do secret postgres-credentials (owner do bootstrap CNPG)..."
PG_USER=$(kubectl get secret postgres-credentials -n "$NAMESPACE" -o jsonpath='{.data.username}' | base64 -d)
PG_PASSWORD=$(kubectl get secret postgres-credentials -n "$NAMESPACE" -o jsonpath='{.data.password}' | base64 -d)
[ -n "$PG_USER" ] && [ -n "$PG_PASSWORD" ] || err "Não consegui ler usuário/senha do secret postgres-credentials."

cleanup() {
    info "Removendo pod auxiliar ($HELPER_POD)..."
    kubectl delete pod "$HELPER_POD" -n "$NAMESPACE" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT

info "Subindo pod auxiliar ($HELPER_POD, imagem $HELPER_IMAGE) dentro do cluster..."
kubectl run "$HELPER_POD" -n "$NAMESPACE" --image="$HELPER_IMAGE" --restart=Never \
    --command -- sleep 3600 >/dev/null

info "Aguardando pod auxiliar ficar pronto..."
kubectl wait --for=condition=Ready "pod/$HELPER_POD" -n "$NAMESPACE" --timeout=60s >/dev/null

for entry in "${DATABASES[@]}"; do
    IFS=':' read -r old_db new_db <<< "$entry"
    dump_file="$DUMPS_DIR/${old_db}-latest.dump"
    [ -f "$dump_file" ] || err "Dump não encontrado: $dump_file (rode 01-dump-postgres.sh antes)."

    if [ "$FORCE" != "true" ]; then
        existing=$(kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- env PGPASSWORD="$PG_PASSWORD" \
            psql -h "$PG_SVC" -U "$PG_USER" -d "$new_db" \
            -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "?")
        if [ "$existing" != "0" ]; then
            err "Banco '$new_db' já tem $existing tabela(s) — abortando para não sobrescrever. Limpe manualmente (DROP SCHEMA public CASCADE; CREATE SCHEMA public;) ou use --force se tiver certeza."
        fi
    fi

    info "Copiando $dump_file -> pod auxiliar:/tmp/${old_db}.dump"
    run "kubectl cp do dump de $new_db" \
        kubectl cp "$dump_file" "$NAMESPACE/$HELPER_POD:/tmp/${old_db}.dump"

    info "Restaurando /tmp/${old_db}.dump -> banco '$new_db' (conexão interna ao cluster, sem port-forward)"
    run "pg_restore em $new_db" \
        kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- env PGPASSWORD="$PG_PASSWORD" \
        pg_restore --no-owner --role="$PG_USER" \
        -h "$PG_SVC" -U "$PG_USER" -d "$new_db" \
        --jobs=4 --verbose "/tmp/${old_db}.dump"
    log "OK: $new_db restaurado."
done

log "Restore concluído. Rode 03-verify-postgres.sh para conferir as contagens."
