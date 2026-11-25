# Overlays `revoada-tcc` e `revoada-tcc-queue`

Pilha do pipeline de extração no namespace de testes `querido-diario-tcc` do
Revoada, para a campanha R do protocolo de avaliação do TCC
(`querido-diario-estados`, `docs/avaliacao/protocolo.md`). Não toca no
namespace `querido-diario` (produção).

| Overlay | Modo | Extração |
|---|---|---|
| `revoada-tcc` | A (baseline) | CronJob `data-processing` + Tika compartilhado |
| `revoada-tcc-queue` | B e C | componente `queue-pipeline`: `redis-queue` + `extraction-worker` (Tika sidecar) escalado pelo KEDA |

Os dois partem do overlay `dev`, com os mesmos limites de Postgres, OpenSearch,
Garage, Redis e Tika (512Mi de *request* e 1500Mi de *limit*), para que a
diferença em relação à campanha K seja só o hardware, o N e o teto. O que muda:

- só o pipeline sobe: frontend, API, backend, Celery, o Redis do backend, a
  Garage Web UI e as IngressRoutes do dev ficam de fora;
- Postgres (CNPG), OpenSearch e Garage em `ceph-block-hdd`; o `redis-queue` em
  `local-path` (dados pequenos);
- os PDFs ficam num Garage dentro do namespace, como no kind, e não num bucket
  do Ceph S3. Assim o storage é o mesmo da campanha K e o `load_simulator.py`
  continua usando o `svc/garage`;
- imagens fixadas por digest em `imagens/`, as mesmas nos três modos: o
  data-processing usa `:tcc-fila` também no modo A;
- o componente `revoada-monitoring` traz o Pushgateway e o RBAC do
  `prometheus-k8s`; no `revoada-tcc-queue` entram também os PodMonitors do
  `extraction-worker` e do `redis-queue`;
- `data-processing` e `themes-from-queue` suspensos. O `enqueue-extraction`
  continua a cada 5 min, como no kind;
- o teto do `ScaledObject` fica em `../revoada-tcc-queue/patch-teto.yaml`, a
  ser ajustado pelo D5.

O OpenSearch roda sem o plugin de segurança e o Garage com o `rpc_secret` e o
token de admin do dev. Só há dados sintéticos, mas qualquer pod do cluster
alcança esses serviços: não carregue dados reais neste namespace.

## Pré-requisitos

- VPN: `sudo wg-quick up revoada`
- contexto `revoada-testes`, que só enxerga o `querido-diario-tcc`. **Todo
  comando leva `--context revoada-testes`**: o contexto atual costuma ser o do kind
- no namespace: os rolebindings `cnpg-manager` e o acesso a KEDA e
  `PodMonitor`/`ServiceMonitor` (já liberados)

```bash
CTX="--context revoada-testes"; NS=querido-diario-tcc
```

## Subir

```bash
# 1. Segredos, fora do repositório (idempotente)
k8s/overlays/revoada-tcc/criar-segredos.sh

# 2. Modo A
kubectl apply -k k8s/overlays/revoada-tcc $CTX
kubectl wait --for=condition=Ready cluster/postgres -n $NS $CTX --timeout=10m
kubectl rollout status statefulset/opensearch -n $NS $CTX --timeout=10m
kubectl get pods -n $NS $CTX
```

### Territórios e índices

As tabelas `territories`, `gazettes` e as dos raspadores são criadas pelo
`scrapy qd-sync-spiders` do repositório `querido-diario` (branch
`main-estados`, que já traz o `3299999`, Governo do Estado do Espírito Santo):

```bash
USER=$(kubectl get secret app-secret -n $NS $CTX -o jsonpath='{.data.QD_DATA_DB_USER}' | base64 -d)
PASS=$(kubectl get secret app-secret -n $NS $CTX -o jsonpath='{.data.QD_DATA_DB_PASSWORD}' | base64 -d)
kubectl port-forward svc/postgres-rw 5433:5432 -n $NS $CTX &
(cd ../querido-diario/querido_diario_raspadores && \
  QUERIDODIARIO_DATABASE_URL="postgresql://$USER:$PASS@localhost:5433/queridodiario" \
  uv run --project . scrapy qd-sync-spiders)
kill %1
```

Os índices do OpenSearch são criados pelo primeiro passo do pipeline
(`tasks/create_index.py`). Com o banco ainda sem diários, um Job do
`data-processing` só cria os índices e termina:

```bash
kubectl create job --from=cronjob/data-processing indices -n $NS $CTX
kubectl exec opensearch-0 -n $NS $CTX -- curl -s localhost:9200/_cat/indices
```

## Trocar de modo

A → B/C:

```bash
kubectl apply -k k8s/overlays/revoada-tcc-queue $CTX
```

O Tika compartilhado vai a 0 réplicas e o KEDA mantém o `extraction-worker` em
0 até haver fila. No modo B, o `run_experiment.sh` (E-2) fixa
`minReplicaCount=maxReplicaCount=1` no `ScaledObject`.

B/C → A (o `ScaledObject` primeiro, para o KEDA não recriar workers):

```bash
kubectl delete scaledobject,deployment,service,cronjob,job,pvc,podmonitor \
  -l app.kubernetes.io/part-of=queue-pipeline -n $NS $CTX --ignore-not-found
kubectl apply -k k8s/overlays/revoada-tcc $CTX
```

### KEDA no Revoada

O KEDA do Revoada observa todos os namespaces, mas só os objetos com o label
`keda=enabled` (`ScaledObject`, `ScaledJob`, HPA e `TriggerAuthentication`).
O `revoada-tcc-queue` acrescenta esse label ao `ScaledObject`. Sem ele, o
`ScaledObject` fica sem `status` e sem HPA, e os workers não saem de 0. Um
`ScaledObject` novo precisa do mesmo label. Para conferir:

```bash
kubectl get scaledobject,hpa -n $NS $CTX   # READY=True e um HPA keda-hpa-extraction-worker
```

### Nós

Só a `hipo2` e a `hipo3` aceitam pods (Xeon Gold 5418Y, 48 núcleos com HT,
512 GB de RAM). Os outros nós têm o taint `control-plane:NoSchedule`. Os
volumes ficam no Ceph, menos o do `redis-queue` (`local-path`), que prende o
pod ao nó em que foi criado. A `hipo2` também roda outras cargas do cluster:
registre `kubectl top nodes $CTX` no início de cada execução, como pede o
protocolo.

## Rodar uma carga

Do repositório `querido-diario-estados`:

```bash
# Modo A
uv run simulador/load_simulator.py --profile burst --total 20 \
  --port-forward --context revoada-testes --namespace $NS
kubectl create job --from=cronjob/data-processing dp-$(date +%s) -n $NS $CTX

# Modo C
uv run simulador/load_simulator.py --profile burst --total 20 \
  --port-forward --context revoada-testes --namespace $NS
kubectl create job --from=cronjob/enqueue-extraction enq-$(date +%s) -n $NS $CTX
kubectl get scaledobject,deployment/extraction-worker -n $NS $CTX -w

# Diário corrompido para a DLQ (qd:extraction:dead). O simulador só aceita
# corrompidos entre 25% e 75% da carga, então N >= 4
uv run simulador/load_simulator.py --profile burst --total 4 --corrupt 1 --duration 10s \
  --port-forward --context revoada-testes --namespace $NS
kubectl exec deploy/redis-queue -c redis -n $NS $CTX -- redis-cli lrange qd:extraction:dead 0 -1

# Limpeza dos diários sintéticos
uv run simulador/load_simulator.py --cleanup \
  --port-forward --context revoada-testes --namespace $NS
```

As métricas saem pelo pod `simulador/k8s/export-metrics-pod.yaml`, que consulta
o `prometheus-k8s.monitoring.svc:9090` de dentro do namespace (ver o
comentário no próprio arquivo).

## Derrubar tudo

```bash
kubectl delete scaledobject,deployment,service,cronjob,job,pvc,podmonitor \
  -l app.kubernetes.io/part-of=queue-pipeline -n $NS $CTX --ignore-not-found
kubectl delete -k k8s/overlays/revoada-tcc $CTX
# O StatefulSet não apaga os volumes dele
kubectl delete pvc opensearch-data-opensearch-0 -n $NS $CTX
kubectl delete secret app-secret postgres-credentials -n $NS $CTX
```

O `delete -k` também remove o Pushgateway e o RBAC do `prometheus-k8s`
(componente `revoada-monitoring`); eles voltam com o próximo `apply -k`.
