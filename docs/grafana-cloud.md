# Grafana Cloud (monitoramento em produção)

Monitoramento do cluster Revoada via [Grafana Cloud](https://grafana.com/products/cloud/),
usando o chart Helm `grafana/k8s-monitoring` (versão fixada em
`GRAFANA_CLOUD_CHART_VERSION`, no Makefile) no namespace `querido-diario`.
O Alloy recebe a configuração remotamente pelo Fleet Management.

O Grafana Cloud é um **release Helm de verdade** (`grafana-cloud`), e não mais
YAML estático aplicado pelo Kustomize. O nome do release continua
`grafana-cloud` (e não `k8s-monitoring`) para preservar os nomes do CR Alloy e
do DaemonSet e, com eles, os ids dos coletores no Fleet Management.

## Arquivos

| Arquivo | Função |
|---|---|
| `k8s/monitoring/grafana-cloud/values.yaml` | Valores do chart (cluster `revoada-qd`, presets do Alloy, serviços de telemetria); passado como `-f` ao Helm |
| `scripts/grafana_cloud.py` | `check`, `render`, `diff`, `install`, `status`, `rollback` (chart fixado em `GRAFANA_CLOUD_CHART_VERSION`) |
| `scripts/tests/test_grafana_cloud.py` | Testes do script (`python3 -I -m unittest discover -s scripts/tests -v`) |
| `k8s/overlays/production/grafana-cloud-credentials.example.yaml` | Template do Secret exigido (não é aplicado por nada) |
| `k8s/local/monitoring/` | Valores e dashboards do monitoramento **local** (kind) — ver "Monitoramento local" |

O overlay `production` do Kustomize **não** contém mais nada do Grafana Cloud.

## Comandos (`make grafana-cloud-*`)

| Comando | O que faz |
|---|---|
| `make grafana-cloud-check` | Renderiza o chart (`helm template`) e falha se algum recurso exigir escopo de cluster (CRD, ClusterRole, webhook...) |
| `make grafana-cloud-diff` | `helm template \| kubectl diff` contra o cluster (somente leitura) |
| `make grafana-cloud-install` | `check`, verifica que o Secret `grafana-cloud-credentials` existe e roda `helm upgrade --install --atomic` |
| `make grafana-cloud-status` | `helm status` do release |
| `make grafana-cloud-rollback` | `helm rollback` para a revisão anterior |

Todos operam no contexto atual do `kubectl`/`helm`: confira com
`kubectl config current-context` antes de `install`/`rollback`.

Para mudar valores ou a versão do chart, edite `values.yaml` (ou
`GRAFANA_CLOUD_CHART_VERSION` no Makefile) e abra PR: o CI valida e, no merge,
instala. O DaemonSet do Alloy pertence ao CR `Alloy` (o alloy-operator cria um
release Helm interno `grafana-cloud-alloy`, chart `alloy`): altere-o pelo
`values.yaml`, nunca com `kubectl edit`.

## CI

- `checks.yml` (job `grafana-cloud`): roda `python3 scripts/grafana_cloud.py check`
  — falha se uma mudança de values/chart passar a exigir escopo de cluster.
- `deploy.yml` (a cada push em `main`, `environment: production`, via VPN):
  depois do `kubectl apply -k` e antes do rollout, roda `grafana_cloud.py diff`
  e `grafana_cloud.py install`. O workflow **nunca** cria nem altera o Secret
  `grafana-cloud-credentials`; se ele não existir, o install falha com mensagem
  clara.

## Responsabilidades: CI x admin do Revoada

O ServiceAccount de deploy (`openknowledge`) só tem permissão no namespace
`querido-diario`. Por isso o release roda com tudo que exige escopo de cluster
desligado:

| Valor (`values.yaml`) | Efeito |
|---|---|
| `alloy-operator.deploy: false` | O release não gerencia o operator (Deployment, CRD, ClusterRoles) |
| `telemetryServices.sdkInjector.deploy: false` | Sem SDK injector, webhooks e ClusterRoles dele |
| `telemetryServices.kube-state-metrics.rbac.create: false` | Não cria ClusterRole/Binding do KSM; o ServiceAccount continua sendo criado |

O que fica com o admin (já instalado; só precisa **permanecer**):

- CRD `alloys.collectors.grafana.com`;
- ClusterRoles/Bindings do alloy-operator;
- ClusterRole/Binding `grafana-cloud-kube-state-metrics`;
- permissão do `openknowledge` em `alloys.collectors.grafana.com` no namespace.

O que o admin **remove** (uma vez): os webhooks e ClusterRoles do SDK injector
(e-mail abaixo).

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

## Migração do YAML estático para o release Helm (cutover)

> **ATENÇÃO — ordem do merge.** O `deploy.yml` roda `helm upgrade --install` a
> cada push em `main`. Se o branch da migração for mergeado **antes** do
> cutover, o Helm encontrará os objetos criados antes pelo `kubectl apply -k`
> (ServiceAccount, ConfigMap, Services, Deployment do KSM e CR Alloy), recusará
> adotá-los ("exists and cannot be imported into the current release") e o
> `--atomic` reverterá — o deploy de **todo** o `main` fica vermelho. Siga a
> ordem abaixo.

O `kubectl apply -k` sem `--prune` não remove nada, e o Helm só adota objetos
com as anotações `meta.helm.sh/*`. A estratégia é **remover e reinstalar**,
aceitando uma lacuna curta de métricas e logs (minutos: o tempo de o operator
recriar o DaemonSet e dos coletores voltarem ao Fleet Management).

Os comandos abaixo atuam em **produção**, e o contexto padrão do `kubectl` nesta
máquina é o de produção. Confirme o contexto antes de cada passo.

### 1. E-mail ao admin do Revoada

Aguarde a confirmação antes de seguir. Texto sugerido (sem hostnames nem IPs):

> Assunto: Grafana Cloud no namespace querido-diario — ajuste de recursos de cluster
>
> Olá! Estamos migrando o Grafana Cloud (chart `grafana/k8s-monitoring`) de YAML
> estático para um release Helm operado pelo CI com o ServiceAccount
> `openknowledge`, que só tem permissão no namespace `querido-diario`. Para isso
> o release passa a não criar nenhum recurso de escopo de cluster. Pedimos, uma
> única vez:
>
> 1. **Manter** (não remover) o que já existe e que o operator e o
>    kube-state-metrics usam: a CRD `alloys.collectors.grafana.com`; os
>    ClusterRoles e ClusterRoleBindings do alloy-operator
>    (`grafana-cloud-alloy-operator*`); o ClusterRole e o ClusterRoleBinding
>    `grafana-cloud-kube-state-metrics`; e a permissão do `openknowledge` em
>    `alloys.collectors.grafana.com` no namespace.
> 2. **Remover** os restos do SDK injector, que desligamos: o
>    `MutatingWebhookConfiguration` e o `ValidatingWebhookConfiguration`
>    `grafana-cloud-k8s-injection-controller*`, e o ClusterRole e o
>    ClusterRoleBinding `grafana-cloud-k8s-injection-controller`. Pedimos que
>    isso seja feito **antes** de apagarmos o Deployment do injector (o webhook
>    de ConfigMaps tem `failurePolicy: Fail` e bloquearia ConfigMaps do
>    namespace se o controller sumisse primeiro).
>
> Nada mais é necessário. Avisem quando estiver feito, por favor.
>
> Obrigado!

Antes de enviar, confira os nomes exatos:
`kubectl get clusterrole,clusterrolebinding,mutatingwebhookconfiguration,validatingwebhookconfiguration | grep grafana-cloud`.

### 2. Remover os recursos namespaced do release antigo

Fonte da verdade: o `manifests.yaml` antigo, preservado no histórico:
`git show 7d8c49f:k8s/monitoring/grafana-cloud/manifests.yaml` (24 objetos no
total). O Secret `grafana-cloud-credentials` **não** está nele e **não** deve
ser apagado.

**Apagar (19 objetos):**

| Grupo | Objetos |
|---|---|
| Recriados pelo release Helm (6; o Helm não adota objetos existentes) | CR `Alloy/grafana-cloud-alloy`; `ConfigMap/grafana-cloud-alloy`; `ServiceAccount`, `Service` e `Deployment` `grafana-cloud-kube-state-metrics`; `Service/grafana-cloud-otel-receiver` |
| Restos do SDK injector, desligado (13) | `Deployment`, `ServiceAccount` e `Service/...-webhook` `grafana-cloud-k8s-injection-controller`; `Secret/...-serving-cert`; `ConfigMap/...-sdk-config`; 3 `Role` + 3 `RoleBinding` `grafana-cloud-k8s-injection-controller-{configmap-reader,leader-election,cert-rotator}*`; `Role` e `RoleBinding` `grafana-cloud-alloy-sdk-injector` |

**NÃO apagar (5 objetos do operator, mais o Secret):** o operator continua no
cluster, fora do Helm (`alloy-operator.deploy: false`), e ainda "pertence" ao
`kubectl apply` antigo. Isso é intencional: deixe como está. Sem ele o CR
`Alloy` não é reconciliado e o DaemonSet não volta.

- `Deployment/grafana-cloud-alloy-operator`
- `ServiceAccount/grafana-cloud-alloy-operator`
- `Service/grafana-cloud-alloy-operator`
- `Role/grafana-cloud-alloy-operator-leader-election-role`
- `RoleBinding/grafana-cloud-alloy-operator-leader-election-rolebinding`
- `Secret/grafana-cloud-credentials` e tudo de escopo de cluster (admin).

**Nunca** use `kubectl delete -f` no arquivo antigo inteiro: apagaria o operator.
Use a lista explícita abaixo (24 = 19 + 5, confira contra o arquivo antigo).

Primeiro o CR `Alloy`, com o operator `Running` (o finalizer dele remove o
DaemonSet e o release interno `grafana-cloud-alloy`):

```bash
kubectl config current-context        # confirme: é produção, de propósito
kubectl get deploy grafana-cloud-alloy-operator -n querido-diario   # 1/1

kubectl delete alloy.collectors.grafana.com/grafana-cloud-alloy -n querido-diario --dry-run=server
kubectl delete alloy.collectors.grafana.com/grafana-cloud-alloy -n querido-diario
```

Depois os demais, **sempre prévia primeiro** (`--dry-run=server`); se ela listar
só os objetos esperados, repita o mesmo comando sem a flag:

```bash
kubectl delete -n querido-diario --dry-run=server \
  configmap/grafana-cloud-alloy \
  serviceaccount/grafana-cloud-kube-state-metrics \
  service/grafana-cloud-kube-state-metrics \
  deployment.apps/grafana-cloud-kube-state-metrics \
  service/grafana-cloud-otel-receiver \
  deployment.apps/grafana-cloud-k8s-injection-controller \
  serviceaccount/grafana-cloud-k8s-injection-controller \
  service/grafana-cloud-k8s-injection-controller-webhook \
  secret/grafana-cloud-k8s-injection-controller-serving-cert \
  configmap/grafana-cloud-k8s-injection-controller-sdk-config \
  role/grafana-cloud-k8s-injection-controller-configmap-reader \
  role/grafana-cloud-k8s-injection-controller-leader-election-role \
  role/grafana-cloud-k8s-injection-controller-cert-rotator-role \
  role/grafana-cloud-alloy-sdk-injector \
  rolebinding/grafana-cloud-k8s-injection-controller-configmap-reader \
  rolebinding/grafana-cloud-k8s-injection-controller-leader-election-rolebinding \
  rolebinding/grafana-cloud-k8s-injection-controller-cert-rotator-rolebinding \
  rolebinding/grafana-cloud-alloy-sdk-injector
```

Conferência antes do merge:

```bash
kubectl get all,configmap,secret,role,rolebinding,alloy -n querido-diario | grep grafana-cloud
```

Devem restar só os 5 objetos do operator e o Secret `grafana-cloud-credentials`
(além do release interno do operator, se o DaemonSet ainda estiver sendo
removido). Se algo do release antigo restar, o `helm install` falhará.

### 3. Merge

Com a confirmação do admin e o passo 2 feitos, mergeie: o `deploy.yml` roda
`helm upgrade --install --atomic` e cria o release `grafana-cloud`. Alternativa,
antes do merge: `make grafana-cloud-diff` e `make grafana-cloud-install`.

### 4. Verificar

```bash
make grafana-cloud-status                  # release grafana-cloud: deployed
helm list -n querido-diario                # grafana-cloud deployed (e grafana-cloud-alloy, do operator)
kubectl get ds,pods -n querido-diario -o wide | grep grafana-cloud   # DaemonSet do Alloy Running em todos os nós
kubectl logs -n querido-diario ds/grafana-cloud-alloy --tail=50      # sem "invalid token"/401
```

No Grafana Cloud: os coletores
`grafana-cloud-revoada-qd-querido-diario-alloy-<nó>` voltam ao Fleet Management
e métricas/logs do cluster `revoada-qd` voltam a chegar. **Lacuna esperada:**
alguns minutos sem métricas e logs entre o passo 2 e o DaemonSet novo `Running`.

**Pontos a conferir no cutover:**

- O diff ao vivo (`make grafana-cloud-diff`) mostrou o CR `Alloy` ganhando
  `image.tag: v1.20.0` (o CR atual não fixa a tag) e `generation` 1 → 2. Como o
  CR é apagado e recriado, isso vira só uma criação; confira que o DaemonSet novo
  sobe com a imagem esperada e sem reinícios em loop.
- O KSM continua listando `nodes`/`namespaces` (o ClusterRole do admin foi
  mantido): `kube_node_info` presente no Grafana Cloud.
- O webhook de ConfigMaps do injector não existe mais (passo 1): criar/alterar
  ConfigMaps no namespace funciona normalmente.

### Rollback

- Falha no `helm upgrade --install` (CI ou make): `--atomic` já reverte; no 1º
  install, desfaz o release inteiro.
- Release instalado com problema: `make grafana-cloud-rollback` (`helm rollback`)
  ou `helm uninstall grafana-cloud -n querido-diario`.
- Voltar ao YAML estático: extraia o arquivo antigo
  (`git show 7d8c49f:k8s/monitoring/grafana-cloud/manifests.yaml > /tmp/manifests.yaml`),
  `helm uninstall grafana-cloud -n querido-diario` e aplique só os objetos que
  precisar (o admin já removeu o injector, então não reaplique os dele). Não
  apague o Secret `grafana-cloud-credentials`.

## Nome do cluster

O cluster se chama **`revoada-qd`** no Grafana Cloud (`cluster.name` do
`values.yaml`): vira o atributo `cluster` do coletor no Fleet Management, a
variável `CLUSTER_NAME` do Alloy e parte do `id` de cada coletor
(`grafana-cloud-revoada-qd-querido-diario-alloy-<nó>`). Ao escrever *matchers* de
pipelines no Fleet Management, use esse valor exato (ex.: `cluster!="revoada-qd"`
ou `cluster!~"revoada.*"`); `revoada` sozinho não casa.

## O que é implantado

O release (`helm template`, chart 4.5.3) cria só recursos namespaced:

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
