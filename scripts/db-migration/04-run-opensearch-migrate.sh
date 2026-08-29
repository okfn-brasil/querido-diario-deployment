#!/usr/bin/env bash
# 04-run-opensearch-migrate.sh — roda opensearch-migrate.py de dentro do
# cluster, num pod temporário, em vez de na VPS com kubectl port-forward.
#
# Motivo: opensearch-migrate.py originalmente exigia
# `kubectl port-forward svc/opensearch 9200:9200` pra escrever no destino
# — o mesmo mecanismo que já causou um restore parcial do Postgres
# (conexão caindo no meio de uma transferência longa). O índice OpenSearch
# é potencialmente muito maior que os dumps do Postgres, então o mesmo
# risco existe em escala maior.
#
# Rodando de dentro do cluster, a escrita no destino (svc/opensearch) é
# 100% interna (DNS do cluster, sem túnel). A única perna de rede que
# resta é cluster -> OpenSearch antiga (na VPS) — confirmada
# manualmente antes de usar este script: liberar o IP de saída do
# cluster (`kubectl run --image=curlimages/curl -- curl -s
# https://api.ipify.org`) no firewall/security group da origem.
#
# O checkpoint de opensearch-migrate.py (retomada automática, idempotente
# por _id) fica num PVC pequeno (1Gi) que sobrevive mesmo se o pod
# precisar ser recriado — o script em si roda desanexado da stream do
# kubectl exec (mesmo padrão validado em 02-restore-postgres.sh), então
# uma queda do polling não afeta a migração em andamento.
#
# Pré-requisitos:
#   - kubectl configurado (KUBECONFIG apontando pro Revoada)
#   - Conectividade cluster -> OLD_OPENSEARCH_HOST já confirmada
#
# Variáveis de ambiente:
#   OLD_OPENSEARCH_HOST      obrigatória (ex: http://search.queridodiario.ok.org.br:9200)
#   OLD_OPENSEARCH_USER/PASSWORD   opcionais, se a origem não tiver auth
#   OLD_OPENSEARCH_INDEX     default: queridodiario
#   NEW_OPENSEARCH_INDEX     default: queridodiario
#   NEW_OPENSEARCH_HOST      default: https://opensearch.<namespace>.svc.cluster.local:9200
#   DRY_RUN=true             só conta documentos, não escreve
#   QD_OS_MIGRATE_RESUME_FROM=N   força retomar a partir do documento N
#
# Uso:
#   OLD_OPENSEARCH_HOST=http://search.queridodiario.ok.org.br:9200 \
#     ./04-run-opensearch-migrate.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

NAMESPACE="${QD_NAMESPACE:-querido-diario}"
HELPER_POD="${QD_OS_MIGRATE_HELPER_POD:-os-migrate-helper}"
HELPER_IMAGE="${QD_OS_MIGRATE_HELPER_IMAGE:-python:3.12-slim}"
PVC_NAME="${QD_OS_MIGRATE_PVC:-os-migrate-checkpoint}"
STORAGE_CLASS="${QD_OS_MIGRATE_STORAGE_CLASS:-ceph-block-hdd}"

OLD_OPENSEARCH_HOST="${OLD_OPENSEARCH_HOST:?Defina OLD_OPENSEARCH_HOST (ex: http://search.queridodiario.ok.org.br:9200)}"
OLD_OPENSEARCH_USER="${OLD_OPENSEARCH_USER:-}"
OLD_OPENSEARCH_PASSWORD="${OLD_OPENSEARCH_PASSWORD:-}"
OLD_OPENSEARCH_INDEX="${OLD_OPENSEARCH_INDEX:-queridodiario}"
NEW_OPENSEARCH_INDEX="${NEW_OPENSEARCH_INDEX:-queridodiario}"
NEW_OPENSEARCH_HOST="${NEW_OPENSEARCH_HOST:-https://opensearch.$NAMESPACE.svc.cluster.local:9200}"

command -v kubectl >/dev/null 2>&1 || err "kubectl não encontrado."

info "Lendo NEW_OPENSEARCH_PASSWORD do secret app-secret..."
NEW_OPENSEARCH_PASSWORD=$(kubectl get secret app-secret -n "$NAMESPACE" -o jsonpath='{.data.QUERIDO_DIARIO_OPENSEARCH_PASSWORD}' | base64 -d)
[ -n "$NEW_OPENSEARCH_PASSWORD" ] || err "Não consegui ler QUERIDO_DIARIO_OPENSEARCH_PASSWORD do secret app-secret."

if ! kubectl get pvc "$PVC_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    info "Criando PVC $PVC_NAME (1Gi) pra persistir o checkpoint entre execuções..."
    kubectl apply -f - >/dev/null <<PVCYAML
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: $PVC_NAME
  namespace: $NAMESPACE
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: $STORAGE_CLASS
  resources:
    requests:
      storage: 1Gi
PVCYAML
fi

cleanup() {
    info "Removendo pod auxiliar ($HELPER_POD) — o PVC de checkpoint ($PVC_NAME) é preservado."
    kubectl delete pod "$HELPER_POD" -n "$NAMESPACE" --ignore-not-found --wait=false >/dev/null 2>&1 || true
}
trap cleanup EXIT

info "Subindo pod auxiliar ($HELPER_POD, imagem $HELPER_IMAGE) dentro do cluster..."
kubectl delete pod "$HELPER_POD" -n "$NAMESPACE" --ignore-not-found --wait=true >/dev/null 2>&1 || true
kubectl apply -f - >/dev/null <<PODYAML
apiVersion: v1
kind: Pod
metadata:
  name: $HELPER_POD
  namespace: $NAMESPACE
spec:
  restartPolicy: Never
  containers:
    - name: migrate
      image: $HELPER_IMAGE
      # sleep generoso: é o processo principal do pod — se expirar antes
      # da migração terminar, o pod (e a migração em background dentro
      # dele) morre junto, mesmo com setsid. 48h de margem pro índice
      # completo (bem maior que os dumps do Postgres).
      command: ["sleep", "172800"]
      volumeMounts:
        - name: checkpoint
          mountPath: /checkpoint
  volumes:
    - name: checkpoint
      persistentVolumeClaim:
        claimName: $PVC_NAME
PODYAML

info "Aguardando pod auxiliar ficar pronto..."
kubectl wait --for=condition=Ready "pod/$HELPER_POD" -n "$NAMESPACE" --timeout=60s >/dev/null

info "Copiando opensearch-migrate.py -> pod auxiliar:/checkpoint/ (checkpoint fica no mesmo diretório, no PVC persistente)"
# Passos de setup (cp, pip install) sempre rodam de verdade — não usam
# run()/DRY_RUN daqui: DRY_RUN neste script controla só a flag --dry-run
# do opensearch-migrate.py (que só conta documentos), não os passos de
# preparo do pod, que são seguros e precisam rodar mesmo assim pra
# validar o mecanismo.
kubectl cp --retries=5 "$SCRIPT_DIR/opensearch-migrate.py" "$NAMESPACE/$HELPER_POD:/checkpoint/opensearch-migrate.py"

info "Instalando opensearch-py no pod auxiliar..."
kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- pip install --quiet opensearch-py

DRY_RUN_FLAG=""
[ "${DRY_RUN:-false}" = "true" ] && DRY_RUN_FLAG="--dry-run"
RESUME_FLAG=""
[ -n "${QD_OS_MIGRATE_RESUME_FROM:-}" ] && RESUME_FLAG="--resume-from ${QD_OS_MIGRATE_RESUME_FROM}"

info "Disparando opensearch-migrate.py (em background dentro do pod)${DRY_RUN_FLAG:+ [--dry-run]}"

# Mesmo padrão de 02-restore-postgres.sh: setsid + stdin/stdout/stderr
# redirecionados pra arquivo, verdadeiramente desanexado da stream do
# kubectl exec que dispara. O script escreve o próprio exit code num
# arquivo; o shell local só faz polling curto e reexecutável.
kubectl exec -i "$HELPER_POD" -n "$NAMESPACE" -- sh -c "cat > /checkpoint/run.sh" <<SCRIPT
cd /checkpoint
export OLD_OPENSEARCH_HOST='$OLD_OPENSEARCH_HOST'
export OLD_OPENSEARCH_USER='$OLD_OPENSEARCH_USER'
export OLD_OPENSEARCH_PASSWORD='$OLD_OPENSEARCH_PASSWORD'
export OLD_OPENSEARCH_INDEX='$OLD_OPENSEARCH_INDEX'
export NEW_OPENSEARCH_HOST='$NEW_OPENSEARCH_HOST'
export NEW_OPENSEARCH_USER='admin'
export NEW_OPENSEARCH_PASSWORD='$NEW_OPENSEARCH_PASSWORD'
export NEW_OPENSEARCH_INDEX='$NEW_OPENSEARCH_INDEX'
python3 opensearch-migrate.py $DRY_RUN_FLAG $RESUME_FLAG
echo \$? > /checkpoint/migrate.exit
SCRIPT

kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- sh -c "
    rm -f /checkpoint/migrate.exit
    setsid sh /checkpoint/run.sh < /dev/null > /checkpoint/migrate.log 2>&1 &
"

info "Migração disparada. Acompanhar progresso a qualquer momento com:"
echo "    kubectl exec $HELPER_POD -n $NAMESPACE -- tail -f /checkpoint/migrate.log"
echo ""
info "Aguardando terminar (pode levar bastante tempo — interromper este script com Ctrl+C NÃO para a migração, ela continua rodando desanexada no pod; rode de novo pra voltar a acompanhar)..."

while ! kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- test -f /checkpoint/migrate.exit 2>/dev/null; do
    sleep 30
done

exit_code=$(kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- cat /checkpoint/migrate.exit)
kubectl exec "$HELPER_POD" -n "$NAMESPACE" -- tail -30 /checkpoint/migrate.log || true

if [ "$exit_code" != "0" ]; then
    err "Migração falhou (exit $exit_code) — ver log acima. O checkpoint foi salvo (ver script), rode este script de novo (mesmo comando) pra retomar automaticamente."
fi

log "Migração concluída. Contagens conferidas pelo próprio opensearch-migrate.py (ver log acima)."
