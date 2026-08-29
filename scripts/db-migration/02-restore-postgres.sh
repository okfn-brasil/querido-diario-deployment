#!/usr/bin/env bash
# 02-restore-postgres.sh — restaura os dumps gerados por 01-dump-postgres.sh
# nos bancos do cluster CNPG (Revoada), via kubectl port-forward.
#
# Pré-requisitos:
#   - kubectl configurado (KUBECONFIG apontando pro Revoada) e WireGuard ativo
#   - cliente `postgresql-client` instalado (pg_restore, psql)
#   - dumps já gerados em ./dumps/<old_db>-latest.dump (por 01-dump-postgres.sh)
#
# Uso:
#   ./02-restore-postgres.sh              # restaura os 3 bancos
#   DRY_RUN=true ./02-restore-postgres.sh # mostra os comandos sem executar
#
# Por padrão o script recusa restaurar sobre um banco que já tenha tabelas
# (evita sobrescrever silenciosamente). Use --force para pular essa checagem
# (ex.: re-rodando após um restore parcial que você sabe que precisa ser limpo
# manualmente antes).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

FORCE=false
[ "${1:-}" = "--force" ] && FORCE=true

NAMESPACE="${QD_NAMESPACE:-querido-diario}"
PG_SVC="${QD_PG_SERVICE:-postgres-rw}"
LOCAL_PORT="${QD_PG_LOCAL_PORT:-5433}"   # porta != 5432 pra não colidir com um postgres local

command -v kubectl >/dev/null 2>&1 || err "kubectl não encontrado."
command -v pg_restore >/dev/null 2>&1 || err "pg_restore não encontrado (apt install postgresql-client)."

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
export PGPASSWORD="$PG_PASSWORD"

info "Abrindo port-forward $PG_SVC -> localhost:$LOCAL_PORT ..."
kubectl port-forward "svc/$PG_SVC" "$LOCAL_PORT:5432" -n "$NAMESPACE" >/tmp/qd-pg-port-forward.log 2>&1 &
PF_PID=$!
trap 'kill $PF_PID 2>/dev/null || true' EXIT

# Espera o port-forward ficar pronto
for _ in $(seq 1 20); do
    psql -h localhost -p "$LOCAL_PORT" -U "$PG_USER" -d postgres -tAc 'SELECT 1;' >/dev/null 2>&1 && break
    sleep 1
done
psql -h localhost -p "$LOCAL_PORT" -U "$PG_USER" -d postgres -tAc 'SELECT 1;' >/dev/null 2>&1 \
    || err "Não foi possível conectar via port-forward após 20s. Veja /tmp/qd-pg-port-forward.log"
log "Conectado ao Postgres do Revoada."

for entry in "${DATABASES[@]}"; do
    IFS=':' read -r old_db new_db <<< "$entry"
    dump_file="$DUMPS_DIR/${old_db}-latest.dump"
    [ -f "$dump_file" ] || err "Dump não encontrado: $dump_file (rode 01-dump-postgres.sh antes)."

    if [ "$FORCE" != "true" ]; then
        existing=$(psql -h localhost -p "$LOCAL_PORT" -U "$PG_USER" -d "$new_db" \
            -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "?")
        if [ "$existing" != "0" ]; then
            err "Banco '$new_db' já tem $existing tabela(s) — abortando para não sobrescrever. Use --force se tiver certeza."
        fi
    fi

    info "Restaurando $dump_file -> banco '$new_db'"
    run "pg_restore em $new_db" \
        pg_restore --no-owner --role="$PG_USER" \
        -h localhost -p "$LOCAL_PORT" -U "$PG_USER" -d "$new_db" \
        --jobs=4 --verbose "$dump_file"
    log "OK: $new_db restaurado."
done

log "Restore concluído. Rode 03-verify-postgres.sh para conferir as contagens."
