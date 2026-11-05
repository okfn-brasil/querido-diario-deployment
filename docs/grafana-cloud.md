# Grafana Cloud (monitoramento em produção)

Monitoramento do cluster Revoada via [Grafana Cloud](https://grafana.com/products/cloud/),
usando o chart `grafana/k8s-monitoring` (versão fixada em
`GRAFANA_CLOUD_CHART_VERSION`, no Makefile) no namespace `querido-diario`.
O Alloy recebe a configuração remotamente pelo Fleet Management.

O chart é **renderizado por `helm template` e aplicado com `kubectl apply`**
(ADR-009). **Não existe release Helm** `grafana-cloud`: `helm list` mostra, no
máximo, o release interno `grafana-cloud-alloy`, criado pelo alloy-operator.
O prefixo `grafana-cloud` (nome usado no `helm template`) preserva os nomes do
CR Alloy e do DaemonSet e, com eles, os ids dos coletores no Fleet Management.

## Arquivos

| Arquivo | Função |
|---|---|
| `k8s/monitoring/grafana-cloud/values.yaml` | Valores do chart (cluster `revoada-qd`, presets do Alloy, serviços de telemetria); passado como `--values` ao `helm template` |
| `scripts/grafana_cloud.py` | `check`, `render`, `diff`, `install`, `status` (chart fixado em `GRAFANA_CLOUD_CHART_VERSION`) |
| `scripts/tests/test_grafana_cloud.py` | Testes do script (`python3 -I -m unittest discover -s scripts/tests -v`) |
| `k8s/overlays/production/grafana-cloud-credentials.example.yaml` | Template do Secret exigido (não é aplicado por nada) |
| `k8s/local/monitoring/` | Valores e dashboards do monitoramento **local** (kind) — ver "Monitoramento local" |

O overlay `production` do Kustomize **não** contém mais nada do Grafana Cloud.

## Comandos (`make grafana-cloud-*`)

| Comando | O que faz |
|---|---|
| `make grafana-cloud-check` | Renderiza o chart (`helm template`) e falha se algum recurso exigir escopo de cluster (CRD, ClusterRole, webhook...) |
| `make grafana-cloud-diff` | `helm template \| kubectl diff` contra o cluster (somente leitura) |
| `make grafana-cloud-install` | `check`, verifica que o Secret `grafana-cloud-credentials` existe e roda `helm template \| kubectl apply -n querido-diario -f -` |
| `make grafana-cloud-status` | `kubectl get` dos objetos do deploy (linhas com `grafana-cloud`); não há `helm status` |

Todos operam no contexto atual do `kubectl`/`helm`: confira com
`kubectl config current-context` antes de `install`.

Para mudar valores ou a versão do chart, edite `values.yaml` (ou
`GRAFANA_CLOUD_CHART_VERSION` no Makefile) e abra PR: o CI valida e, no merge,
aplica. O DaemonSet do Alloy pertence ao CR `Alloy` (o alloy-operator cria um
release Helm interno `grafana-cloud-alloy`, chart `alloy`): altere-o pelo
`values.yaml`, nunca com `kubectl edit`.

## CI

- `checks.yml` (job `grafana-cloud`): roda `python3 scripts/grafana_cloud.py check`
  — falha se uma mudança de values/chart passar a exigir escopo de cluster.
- `deploy.yml` (a cada push em `main`, `environment: production`, via VPN):
  depois do `kubectl apply -k` e antes do rollout, roda `grafana_cloud.py diff`
  e `grafana_cloud.py install` (passo "Aplica Grafana Cloud"). O workflow **nunca** cria nem altera o Secret
  `grafana-cloud-credentials`; se ele não existir, o passo falha com mensagem
  clara.

## Responsabilidades: CI x admin do Revoada

O ServiceAccount de deploy (`openknowledge`) só tem permissão no namespace
`querido-diario`. Por isso o chart é renderizado com tudo que exige escopo de cluster
desligado:

| Valor (`values.yaml`) | Efeito |
|---|---|
| `alloy-operator.deploy: false` | O render não inclui o operator (Deployment, CRD, ClusterRoles) |
| `telemetryServices.sdkInjector.deploy: false` | Sem SDK injector, webhooks e ClusterRoles dele |
| `telemetryServices.kube-state-metrics.rbac.create: false` | Não cria ClusterRole/Binding do KSM; o ServiceAccount continua sendo criado |

O que fica com o admin (já instalado; só precisa **permanecer**):

- CRD `alloys.collectors.grafana.com`;
- ClusterRoles/Bindings do alloy-operator;
- ClusterRole/Binding `grafana-cloud-kube-state-metrics`;
- permissão do `openknowledge` em `alloys.collectors.grafana.com` no namespace
  (`rolebinding/grafana-cloud-alloy-manager`; **nunca apagar**).

O que o admin pode **remover depois**, sem pressa (limpeza opcional): os webhooks e o ClusterRole/Binding do SDK injector. Não é
pré-requisito: o webhook de ConfigMaps do injector está com
`failurePolicy: Ignore` (o admin trocou por causa do deadlock do 1º install e
nunca voltou para `Fail`), então ele não bloqueia nada mesmo sem backend.

O operator (`0.8.0`, embutido no chart 4.5.3) já está no cluster. Ao subir a
versão do chart, confira a versão do operator embutida e avise o admin se mudar.

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

## Por que não `helm install`

O `helm upgrade --install` real roda chamadas `lookup` do chart (chart
`grafana/k8s-monitoring` 4.5.3):

- `templates/_platform_validations.tpl:15` lista todos os Nodes;
- `templates/collectors/_collector_notes.tpl:53` lê um Namespace.

O ServiceAccount de deploy (`openknowledge`) só tem permissão no namespace e o
install falhou no CI com `nodes is forbidden ... cannot list resource "nodes" ...
at the cluster scope`. O `helm template` **não executa `lookup`**, então
funciona e renderiza exatamente 6 objetos namespaced (ServiceAccount, ConfigMap,
2 Services, Deployment do kube-state-metrics e CR `Alloy`).

**Alternativa:** se um admin conceder ao `openknowledge`, em escopo de cluster,
`list nodes` e `get namespaces`, o `install` pode voltar a ser
`helm upgrade --install --atomic` (com release Helm, `helm rollback` e `list`).

## Rollback

Não há `helm rollback`. Reverta o commit no git e redeploye: o CI reaplica os
valores anteriores (`kubectl apply`).

O `kubectl apply` não faz prune: objetos que uma nova versão do chart deixar de
renderizar **não são removidos**; apague-os à mão
(`kubectl delete -n querido-diario <tipo>/<nome>`, conferindo antes o contexto
do `kubectl`). **Nunca** apague o `rolebinding/grafana-cloud-alloy-manager`
(criado pelo admin; dá ao `openknowledge` acesso ao CR `Alloy`) nem o Secret
`grafana-cloud-credentials`.

## Histórico da migração

O Grafana Cloud passou de YAML estático (`kubectl apply -k`) para um release
Helm planejado e, por fim, para `helm template | kubectl apply`. Os objetos do
YAML antigo e os restos do SDK injector foram removidos à mão antes do cutover
(para evitar colisões de posse com o Helm); a lição foi a dos `lookup` descrita
acima, que só apareceu no `helm install` real do CI. O runbook detalhado do
cutover (ordem do merge, congelamento de `main`, e-mail ao admin, sonda do
webhook) está no histórico do git:
`git show e5cd18a:docs/grafana-cloud.md`.

## Nome do cluster

O cluster se chama **`revoada-qd`** no Grafana Cloud (`cluster.name` do
`values.yaml`): vira o atributo `cluster` do coletor no Fleet Management, a
variável `CLUSTER_NAME` do Alloy e parte do `id` de cada coletor
(`grafana-cloud-revoada-qd-querido-diario-alloy-<nó>`). Ao escrever *matchers* de
pipelines no Fleet Management, use esse valor exato (ex.: `cluster!="revoada-qd"`
ou `cluster!~"revoada.*"`); `revoada` sozinho não casa.

## O que é implantado

O deploy (`helm template`, chart 4.5.3) cria só recursos namespaced:

- Alloy: CR `Alloy` (o operator existente cria o DaemonSet, clusterizado, presets
  `large`/`root`/`host-*`/`otel-receiver`) + Service `otel-receiver`
- kube-state-metrics (só o namespace `querido-diario`; `rbac.create: false`: usa o
  ClusterRole que o admin mantém)
- O alloy-operator **não** é implantado pelo chart (`alloy-operator.deploy: false`):
  o Deployment `grafana-cloud-alloy-operator` já existe e o admin mantém CRD e
  ClusterRoles
- SDK injector, Beyla, node-exporter e OpenCost desativados. O SDK injector
  traria webhooks e ClusterRoles (escopo de cluster) e não há auto-instrumentação
  em uso; o node-exporter fica desligado em produção (no Revoada o DaemonSet
  ficava `Pending`: porta do host ocupada em 1 nó e NodeAffinity não satisfeita
  nos outros 5). Mantenha `deploy: true` em execuções locais.

## Monitoramento local (kind) e diferença para produção

`make k8s-local-monitoring-up|down|status|grafana` (alvo separado: **não** sobe
com `make k8s-local-up`) instala no kind (`kind-querido-diario-dev`, namespace
`monitoring`) Prometheus, Loki, Grafana (charts open source) e o Alloy via o
mesmo chart `grafana/k8s-monitoring`, com `k8s/local/monitoring/values-local.yaml`
e dashboards versionados em `k8s/local/monitoring/dashboards/` (Kubernetes/Pods e
logs do namespace `querido-diario`). Usa ~2 GiB de memória extras.

Diferença inevitável: em produção a configuração do Alloy vem do **Fleet
Management** (`remoteConfig`) e a coleta de logs depende dos pipelines de lá. No
local não há Fleet: o chart gera a configuração (`podLogsViaLoki` restrito ao
namespace `querido-diario`, métricas do cluster, `node-exporter` ligado). Logo,
dashboards e consultas do local validam a coleta, mas não os pipelines do Fleet.

Teste manual completo (smoke ao vivo):

```bash
make k8s-local-up                       # cluster kind querido-diario-dev
make k8s-local-monitoring-up            # ~10 min; avisa se houver < 4 GiB livres
make k8s-local-monitoring-status        # todos os pods de monitoring Running
make k8s-local-data-processing          # gera logs, se precisar
make k8s-local-monitoring-grafana       # http://localhost:3000 (admin/admin)
```

No Explore (Loki), `{namespace="querido-diario", container="data-processing"}`
deve retornar linhas; o dashboard "Kubernetes / Pods" (namespace
`querido-diario`) deve mostrar CPU/memória. Remover: `make k8s-local-monitoring-down`
(as CRDs do Alloy podem permanecer no kind após o `down`; é inofensivo).

## Atenção

- Os presets `root`/`host-*` exigem privilégios elevados nos nós. Confirmado em
  2026-10-29: o PodSecurity do namespace aceita o DaemonSet do Alloy com esses
  presets e os nós têm BTF habilitado.

## Ruído conhecido nos logs do Alloy

- `discovery.docker ... failed to connect to the docker API`: um pipeline do
  Fleet Management usa `discovery.docker`, mas os nós só têm containerd. Remova ou
  desligue o componente no pipeline (interface do Fleet Management).
- `could not find advertise address` e `Got ping for unexpected node`: o
  clustering do Alloy não achou interface de rede e cai para `127.0.0.1`; o
  cluster entre os pods fica mal formado e o preset `clustered` pode duplicar
  scrape de alvos. Ainda não investigado.
