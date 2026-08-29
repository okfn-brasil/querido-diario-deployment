#!/usr/bin/env bash
# 03-verify-postgres.sh — compara contagem de linhas entre o dump de origem
# (via docker exec no container antigo) e o banco restaurado no Revoada
# (via um pod auxiliar dentro do cluster, mesma abordagem de
# 02-restore-postgres.sh — evita depender de kubectl port-forward). Gate
# formal antes do cutover de DNS.
#
# Uso:
#   ./03-verify-postgres.sh
#
# Sai com código != 0 se qualquer tabela divergir.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

NAMESPACE="${QD_NAMESPACE:-querido-diario}"
PG_SVC="${QD_PG_SERVICE:-postgres-rw}"
HELPER_POD="${QD_RESTORE_HELPER_POD:-pg-verify-helper}"
HELPER_IMAGE="${QD_RESTORE_HELPER_IMAGE:-postgres:15}"

# container:old_db:new_db:user_env_suffix:tabelas (separadas por espaço)
CHECKS=(
    "postgres_queridodiario:queridodiariodb:queridodiario:QD:territories gazettes querido_diario_spiders territory_spider_map job_stats"
    "postgres_queridodiariobackend:queridodiariobackend:backend:BACKEND:"
    "postgres_receita:qd_receita:companies:RECEITA:"
)

command -v kubectl >/dev/null 2>&1 || err "kubectl não encontrado."

PG_USER=$(kubectl get secret postgres-credentials -n "$NAMESPACE" -o jsonpath='{.data.username}' | base64 -d)
PG_PASSWORD=$(kubectl get secret postgres-credentials -n "$NAMESPACE" -o jsonpath='{.data.password}' | base64 -d)
[ -n "$PG_USER" ] && [ -n "$PG_PASSWORD" ] || err "Não consegui ler usuário/senha do secret postgres-credentials."

cleanup() {
    kubectl delete pod "$HELPER_POD" -n "$NAMESPACE" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT

info "Subindo pod auxiliar ($HELPER_POD) dentro do cluster..."
kubectl run "$HELPER_POD" -n "$NAMESPACE" --image="$HELPER_IMAGE" --restart=Never \
    --command -- sleep 600 >/dev/null
kubectl wait --for=condition=Ready "pod/$HELPER_POD" -n "$NAMESPACE" --timeout=60s >/dev/null

FAILED=0

for entry in "${CHECKS[@]}"; do
    IFS=':' read -r container old_db new_db suffix tables <<< "$entry"
    [ -n "$tables" ] || { warn "Sem lista de tabelas-chave para '$new_db' — pulando (preencha em 01-dump-postgres.sh e aqui após inspecionar o schema)."; continue; }

    old_pass_var="OLD_PG_${suffix}_PASSWORD"
    old_user_var="OLD_PG_${suffix}_USER"
    old_user="${!old_user_var:-${OLD_PG_USER:-}}"
    old_pass="${!old_pass_var:-}"
    [ -n "$old_user" ] && [ -n "$old_pass" ] || err "Defina $old_user_var/$old_pass_var (mesmas vars de 01-dump-postgres.sh)."

    echo ""
    info "Conferindo '$old_db' -> '$new_db'"
    for t in $tables; do
        old_count=$(docker exec -e PGPASSWORD="$old_pass" "$container" \
            psql -U "$old_user" -d "$old_db" -tAc "SELECT count(*) FROM $t;" 2>/dev/null | tr -d '[:space:]')
        new_count=$(kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- env PGPASSWORD="$PG_PASSWORD" \
            psql -h "$PG_SVC" -U "$PG_USER" -d "$new_db" \
            -tAc "SELECT count(*) FROM $t;" 2>/dev/null | tr -d '[:space:]')

        if [ "$old_count" = "$new_count" ]; then
            log "  $t: $old_count == $new_count OK"
        else
            warn "  $t: origem=$old_count destino=$new_count DIVERGENTE"
            FAILED=1
        fi
    done
done

echo ""
if [ "$FAILED" -eq 0 ]; then
    log "Todas as contagens conferem. OK para prosseguir com o cutover."
else
    err "Divergências encontradas — NÃO prossiga com o cutover até investigar."
fi
