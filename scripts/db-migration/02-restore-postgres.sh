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
# sleep generoso (6h): é o processo principal do pod — se expirar antes do
# pg_restore terminar, o pod (e o restore em background dentro dele) morre
# junto, mesmo com setsid.
kubectl run "$HELPER_POD" -n "$NAMESPACE" --image="$HELPER_IMAGE" --restart=Never \
    --command -- sleep 21600 >/dev/null

info "Aguardando pod auxiliar ficar pronto..."
kubectl wait --for=condition=Ready "pod/$HELPER_POD" -n "$NAMESPACE" --timeout=60s >/dev/null

for entry in "${DATABASES[@]}"; do
    IFS=':' read -r old_db new_db <<< "$entry"
    # ${old_db}-latest.dump é um symlink (criado por 01-dump-postgres.sh)
    # pro dump com timestamp — resolver antes do kubectl cp, senão ele
    # copia o link em si (poucos bytes, o texto do caminho apontado) e
    # não o conteúdo real do dump.
    dump_file="$(readlink -f "$DUMPS_DIR/${old_db}-latest.dump")"
    [ -f "$dump_file" ] || err "Dump não encontrado: $DUMPS_DIR/${old_db}-latest.dump (rode 01-dump-postgres.sh antes)."

    if [ "$FORCE" != "true" ]; then
        existing=$(kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- env PGPASSWORD="$PG_PASSWORD" \
            psql -h "$PG_SVC" -U "$PG_USER" -d "$new_db" \
            -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "?")
        if [ "$existing" != "0" ]; then
            err "Banco '$new_db' já tem $existing tabela(s) — abortando para não sobrescrever. Limpe manualmente (DROP SCHEMA public CASCADE; CREATE SCHEMA public;) ou use --force se tiver certeza."
        fi
    fi

    info "Copiando $dump_file -> pod auxiliar:/tmp/${old_db}.dump"
    # --retries: kubectl (1.23+) reexecuta a cópia automaticamente se a
    # conexão cair no meio (mesma classe de instabilidade de rede que já
    # derrubou um restore via port-forward antes).
    run "kubectl cp do dump de $new_db" \
        kubectl cp --retries=5 "$dump_file" "$NAMESPACE/$HELPER_POD:/tmp/${old_db}.dump"

    if [ "$DRY_RUN" != "true" ]; then
        expected_size=$(stat -c%s "$dump_file" 2>/dev/null || stat -f%z "$dump_file")
        transferred_size=$(kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- stat -c%s "/tmp/${old_db}.dump" 2>/dev/null || echo "0")
        [ "$transferred_size" = "$expected_size" ] || err "kubectl cp não transferiu o arquivo por completo: local=${expected_size} bytes, pod=${transferred_size} bytes. Rede instável durante a cópia — rode de novo (kubectl cp não é resumível; se falhar de novo, considere investigar a VPN/CNI ou copiar com 'kubectl cp --retries')."
        log "kubectl cp OK: $expected_size bytes transferidos."
    fi

    info "Restaurando /tmp/${old_db}.dump -> banco '$new_db' (em background dentro do pod)"
    if [ "$DRY_RUN" = "true" ]; then
        info "[dry-run] pg_restore em $new_db (background, dentro do pod)"
    else
        # pg_restore roda em background DENTRO do pod, desanexado de vez da
        # stream do kubectl exec que o dispara — um restore grande pode
        # levar minutos/horas, e prender isso a uma única conexão exec ao
        # vivo é frágil (já aconteceu: a stream deu timeout bem no fim,
        # "read tcp ...: i/o timeout", e o trap de limpeza matou o pod
        # logo depois, cortando o restore no meio das constraints).
        # setsid + </dev/null + redirecionar stdout/stderr pra arquivo é
        # necessário — só "cmd &" NÃO desanexa: o processo mantém os file
        # descriptors herdados da própria stream do exec, e o exec fica
        # bloqueado até o processo em background terminar (testado e
        # confirmado manualmente contra este cluster antes deste script
        # existir). Escreve o script num arquivo primeiro (em vez de
        # aninhar sh -c dentro de sh -c) pra não depender de escaping
        # frágil de aspas/$ através de duas camadas de shell.
        kubectl exec -i "$HELPER_POD" -n "$NAMESPACE" -- sh -c "cat > /tmp/${old_db}.restore.sh" <<SCRIPT
export PGPASSWORD='$PG_PASSWORD'
pg_restore --no-owner --role='$PG_USER' -h '$PG_SVC' -U '$PG_USER' -d '$new_db' --jobs=4 --verbose '/tmp/${old_db}.dump'
echo \$? > '/tmp/${old_db}.restore.exit'
SCRIPT

        kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- sh -c "
            rm -f '/tmp/${old_db}.restore.exit'
            setsid sh '/tmp/${old_db}.restore.sh' < /dev/null > '/tmp/${old_db}.restore.log' 2>&1 &
        "

        info "Aguardando pg_restore terminar (pode levar bastante tempo pra bancos grandes)..."
        while ! kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- test -f "/tmp/${old_db}.restore.exit" 2>/dev/null; do
            sleep 15
        done

        exit_code=$(kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- cat "/tmp/${old_db}.restore.exit")
        if [ "$exit_code" != "0" ]; then
            warn "pg_restore falhou (exit $exit_code) pra $new_db — últimas linhas do log:"
            kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- tail -50 "/tmp/${old_db}.restore.log" || true
            err "Restore de $new_db falhou — ver log acima. Banco pode estar em estado parcial, limpe (DROP SCHEMA public CASCADE; CREATE SCHEMA public;) antes de tentar de novo."
        fi
    fi
    log "OK: $new_db restaurado."
done

log "Restore concluído. Rode 03-verify-postgres.sh para conferir as contagens."
