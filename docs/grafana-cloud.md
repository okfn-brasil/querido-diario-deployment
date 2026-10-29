# Grafana Cloud (monitoramento em produção)

Monitoramento do cluster Revoada via [Grafana Cloud](https://grafana.com/products/cloud/),
usando o chart Helm `grafana/k8s-monitoring` no namespace `querido-diario`.
O Alloy recebe a configuração remotamente pelo Fleet Management.

## Arquivos

| Arquivo | Função |
|---|---|
| `k8s/monitoring/grafana-cloud/values.yaml` | Valores do chart (cluster `revoada-qd`, presets do Alloy, serviços de telemetria) |
| `k8s/monitoring/grafana-cloud/manifests.yaml` | **Gerado** (`helm template --include-crds`), recursos namespaced — não editar à mão |
| `k8s/monitoring/grafana-cloud/cluster-scoped.yaml` | **Gerado**: CRD, ClusterRoles/Bindings e webhooks. Aplicado uma vez pelo admin; fora do kustomization |
| `k8s/monitoring/grafana-cloud/kustomization.yaml` | Referenciado pelo overlay `production` |
| `k8s/overlays/production/grafana-cloud-credentials.example.yaml` | Template do Secret exigido (não aplicado pelo kustomize) |
| `scripts/grafana_cloud_render.py` | Gera o `manifests.yaml` (chart fixado em `GRAFANA_CLOUD_CHART_VERSION`) |

## Pré-requisito: Secret

Criado manualmente (nunca versionar valores):

```bash
kubectl create secret generic grafana-cloud-credentials -n querido-diario \
  --from-literal=username='<ID-DA-INSTANCIA-FLEET-MANAGEMENT>' \
  --from-literal=password='<TOKEN-GRAFANA-CLOUD>'
```

- `username`: ID da instância do **Fleet Management** (não o usuário de
  Prometheus/Loki).
- `password`: token de Access Policy (`glc_...`) com o escopo
  `fleet-management:read`. O Alloy também expõe esse valor como
  `GCLOUD_RW_API_KEY`, que os pipelines do Fleet Management usam para escrever
  nos destinos — então inclua os escopos de escrita desses destinos
  (`metrics:write`, `logs:write`, `traces:write`, `profiles:write`). Sem eles o
  Alloy registra, mas o envio falha com 401/403.
- Token ou instância inválidos aparecem como
  `unauthenticated: authentication error: invalid token` nos logs do Alloy
  (`CrashLoopBackOff`). Uma instância do Grafana Cloud "desligada" também causa
  esse erro.

## Aplicação

Em duas etapas, porque o ServiceAccount de deploy (`openknowledge`) não tem
permissão de escopo de cluster:

1. **Admin do Revoada** (uma vez, e a cada mudança de versão do chart), com
   permissão de cluster:

   ```bash
   kubectl apply -f k8s/monitoring/grafana-cloud/cluster-scoped.yaml
   ```

   Cria 1 CRD (`alloys.collectors.grafana.com`), 5 ClusterRoles, 5
   ClusterRoleBindings e 2 webhooks (SDK injector). Deve vir **antes** da etapa 2,
   pois o CR `Alloy` depende da CRD.

   O admin também precisa dar ao ServiceAccount de deploy permissão
   (`get/list/watch/create/update/patch/delete`) em `alloys.collectors.grafana.com`
   no namespace `querido-diario` (ClusterRole + binding, como nos demais
   serviços); sem isso o apply do CR `Alloy` falha com `Forbidden`.

2. **Deploy normal** (namespaced), junto com o resto de produção:

   ```bash
   make k8s-diff-prod
   make k8s-apply-prod
   ```

Webhooks do SDK injector (ver `cluster-scoped.yaml`): o de pods é
`failurePolicy: Ignore`; o de ConfigMaps é `Fail` e restrito ao namespace
`querido-diario` — se o controller ficar fora do ar, **criar/alterar ConfigMaps
no namespace falha**.

**Armadilha no 1º install (deadlock):** o webhook de ConfigMaps já existe (aplicado
pelo admin) antes do Service dele. O 1º apply falha ao criar os ConfigMaps
`grafana-cloud-alloy` e `grafana-cloud-k8s-injection-controller-sdk-config`, e
sem eles o controller e os pods do Alloy ficam em `ContainerCreating` — o
controller nunca sobe para atender o webhook. Solução: o admin coloca
`failurePolicy: Ignore` no webhook
`grafana-cloud-k8s-injection-controller-validating-webhook` (patch em
`/webhooks/0/failurePolicy`), reaplique `k8s/monitoring/grafana-cloud` e peça para
restaurar `Fail` quando o controller estiver `1/1`.

Para mudar valores ou a versão do chart, edite `values.yaml` (ou
`GRAFANA_CLOUD_CHART_VERSION` no Makefile), rode `make grafana-cloud-render` e
commite `manifests.yaml` e `cluster-scoped.yaml` atualizados (o segundo precisa ser reaplicado pelo admin).

Diferenças em relação ao `helm upgrade --install`: o release não existe no Helm
(sem `helm uninstall`/rollback — remova com `kubectl delete -k`) e os Jobs de
hook (add-finalizer / remove-alloy-and-finalizer) são descartados. Para
desinstalar, apague a CR `Alloy` antes do Deployment do operador (o admin remove
os recursos de `cluster-scoped.yaml`).

## O que é implantado

- Alloy (DaemonSet, clusterizado, presets `large`/`root`/`host-*`/`otel-receiver`) + Service `otel-receiver`
- kube-state-metrics
- Beyla (k8s cache, 1 réplica) e SDK injector (auto-instrumentação)
- node-exporter e OpenCost desativados. O node-exporter fica desligado em
  produção (`deploy: false` no `values.yaml`): no Revoada o DaemonSet ficava
  `Pending` (porta do host ocupada em 1 nó e NodeAffinity não satisfeita nos
  outros 5). Mantenha `deploy: true` em execuções locais.

## Atenção

- Beyla, SDK injector e presets `root`/`host-*` exigem privilégios elevados nos
  nós. Confirmado em 2026-10-29: o PodSecurity do namespace aceita o DaemonSet do
  Alloy com esses presets e os nós têm BTF habilitado (necessário para eBPF).
- O SDK injector pode alterar pods de workloads do namespace; acompanhe os
  rollouts após o install.

## Ruído conhecido nos logs do Alloy

- `discovery.docker ... failed to connect to the docker API`: um pipeline do
  Fleet Management usa `discovery.docker`, mas os nós só têm containerd. Remova ou
  desligue o componente no pipeline (interface do Fleet Management).
- `could not find advertise address` e `Got ping for unexpected node`: o
  clustering do Alloy não achou interface de rede e cai para `127.0.0.1`; o
  cluster entre os pods fica mal formado e o preset `clustered` pode duplicar
  scrape de alvos. Ainda não investigado.
