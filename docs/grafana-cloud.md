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

2. **Deploy normal** (namespaced), junto com o resto de produção:

   ```bash
   make k8s-diff-prod
   make k8s-apply-prod
   ```

Webhooks do SDK injector (ver `cluster-scoped.yaml`): o de pods é
`failurePolicy: Ignore`; o de ConfigMaps é `Fail` e restrito ao namespace
`querido-diario` — se o controller ficar fora do ar, **criar/alterar ConfigMaps
no namespace falha**.

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
- node-exporter, kube-state-metrics
- Beyla (k8s cache, 1 réplica) e SDK injector (auto-instrumentação)
- OpenCost desativado

## Atenção

- Beyla, SDK injector e presets `root`/`host-*` exigem privilégios elevados nos
  nós; confirmar com a administração do Revoada (PodSecurity) antes do 1º install.
- O SDK injector pode alterar pods de workloads do namespace; acompanhe os
  rollouts após o install.
