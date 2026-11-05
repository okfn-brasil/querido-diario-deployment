# Design — Grafana Cloud via Helm (release real) + monitoramento local

Data: 2026-11-04 · Status: rascunho para aprovação

## Intenção e porquê

Hoje o Grafana Cloud em produção (cluster Revoada) é aplicado como YAML
estático: `scripts/grafana_cloud_render.py` roda `helm template` do chart
`grafana/k8s-monitoring` (4.5.3) e gera `manifests.yaml` (aplicado por
`kubectl apply -k`) e `cluster-scoped.yaml` (aplicado uma vez pelo admin).
Não existe release Helm, então não há `helm upgrade`, `rollback` nem
`helm list` para esse componente, e cada orientação do Grafana Cloud (ex.:
habilitar coleta de logs de pod) precisa ser traduzida à mão.

Decisão do mantenedor: seguir as orientações oficiais do Grafana Cloud e passar
a usar um **release Helm de verdade** (`helm upgrade --install`), operado pelo
Makefile e pelo CI. Além disso, quer **replicar localmente (kind)** o
monitoramento com ferramentas open source, para ver dashboards, métricas e logs
de pod.

## Objetivos

1. `helm upgrade --install k8s-monitoring grafana/k8s-monitoring` no namespace
   `querido-diario`, com versão do chart fixada, a partir de `values.yaml`
   versionado — via `make` e via CI (`deploy.yml`).
2. Tudo o que o ServiceAccount `openknowledge` consegue fazer no namespace
   é automatizado; o que exige escopo de cluster continua com o admin do
   Revoada, por e-mail, e fica reduzido ao mínimo e documentado.
3. Alvo separado `make k8s-local-monitoring-up` (e `-down`/`-status`) que sobe,
   no kind, Prometheus + Loki + Grafana + Alloy (via o mesmo chart, com
   `values-local.yaml`), com dashboards versionados e métricas e logs de pod
   visíveis.
4. Documentação atualizada (`docs/grafana-cloud.md`, `CLAUDE.md`, `Makefile
   help`).

## Não-objetivos

- Não mexer na instrumentação das aplicações.
- Não migrar o Fleet Management nem os pipelines configurados nele.
- O monitoramento local **não** sobe junto com `make k8s-local-up`.
- Sem alertas e sem HA.

## Anti-objetivos (seria fracasso mesmo "funcionando")

- Commitar IPs, hostnames, endpoints internos ou credenciais (regras do
  CLAUDE.md): tokens ficam no Secret `grafana-cloud-credentials`, criado à mão
  ou por secret do GitHub, nunca no `values.yaml`.
- Um `helm upgrade` no CI que falhe com `Forbidden` por tentar criar recursos
  de cluster.
- Estourar o limite de séries (15.000) ou o volume de logs do tenant do
  Grafana Cloud.

## Decisões do mantenedor

- **Divisão de responsabilidades (opção 1):** o admin instala uma vez, por
  e-mail, os recursos de escopo de cluster; o CI faz `helm upgrade` do
  `k8s-monitoring` com esses componentes desligados.
- **Local:** alvo separado, não incluído no `k8s-local-up`.
- **Escopo local:** dashboards, métricas e logs de pod.
- Prod coleta logs só do namespace `querido-diario` (volume do Loki).

## Fatos verificados (chart 4.5.3)

- O sub-chart `alloy-operator` (0.8.0) é desligável com
  `alloy-operator.deploy: false`.
- O `cluster-scoped.yaml` atual contém, além do operator: ClusterRole/Binding do
  `kube-state-metrics` e do `k8s-injection-controller`, mais os 2 webhooks do
  SDK injector. **Desligar só o operator não basta**: um `helm upgrade` com o
  chart completo ainda tentaria criar esses ClusterRoles.
- Neste chart a feature de logs de pod se chama **`podLogsViaLoki`** (com
  `podLogsViaOpenTelemetry` e `podLogsViaKubernetesApi` como alternativas), não
  `podLogs`/`alloy-logs` como na resposta do assistente do Grafana (outra
  versão do chart).
- Hoje o Alloy recebe a configuração remota do Fleet Management
  (`remoteConfig`) e o preset `filesystem-log-reader` está ativo; logs em prod
  podem depender de pipeline no Fleet e não de `podLogsViaLoki` no values.

## Desenho

### Produção

- `k8s/monitoring/grafana-cloud/values.yaml` continua sendo a fonte; passa a ser
  usado como `-f`. Remover `manifests.yaml`, `cluster-scoped.yaml`,
  `kustomization.yaml` do diretório e a referência a ele em
  `overlays/production`.
- Remover `scripts/grafana_cloud_render.py` e o alvo `grafana-cloud-render`.
- Novos alvos de Makefile: `grafana-cloud-diff` (helm-diff ou
  `helm template | kubectl diff`), `grafana-cloud-install` (`helm upgrade
  --install --atomic`), `grafana-cloud-status`, `grafana-cloud-rollback`.
  `GRAFANA_CLOUD_CHART_VERSION` continua no Makefile.
- CI: novo passo em `deploy.yml`, depois do `kubectl apply -k` e antes do
  rollout, instalando `helm` (se ausente) e rodando o `helm upgrade --install`.
  Usa a VPN, o kubeconfig e o `environment: production` já existentes.
- Para os recursos de cluster: o `values.yaml` desliga o que exige escopo de
  cluster (operator; injector; ClusterRole do kube-state-metrics, se possível)
  e o admin instala o equivalente uma vez. A forma exata de instalar (chart
  `grafana/alloy-operator` direto ou YAML renderizado por um script reduzido) é
  decisão do builder, desde que o `helm upgrade` do CI nunca exija permissão de
  cluster.
- **Minha decisão (a confirmar):** desligar o **SDK injector**
  (`telemetryServices.sdkInjector.deploy: false`). Beyla já está desligado, não
  há auto-instrumentação em uso, e é ele que traz os webhooks, a armadilha de
  deadlock do 1º install e dois ClusterRoles.
- Logs em prod: manter o modelo atual (Fleet Management). Se for preciso
  habilitar por values, usar `podLogsViaLoki` restrito ao namespace
  `querido-diario`; o builder verifica se `remoteConfig` é compatível.
- Migração: o release `k8s-monitoring` ainda não existe. A 1ª instalação precisa
  adotar ou substituir os recursos já criados por `kubectl apply` (mesmos nomes).
  O builder define o procedimento (remover antes e reinstalar, ou adotar com
  as anotações `meta.helm.sh/*`) e o janela com possível perda de métricas.

### Local (kind)

- `k8s/local/monitoring/values-local.yaml` + alvos `k8s-local-monitoring-up`,
  `-down`, `-status`, `-grafana` (port-forward do Grafana).
- Stack: Prometheus + Loki + Grafana (charts open source) no namespace
  `monitoring`, e o Alloy via o mesmo chart `k8s-monitoring` com destinos
  apontando para eles. `node-exporter` com `deploy: true`.
- Diferença inevitável com prod: sem Fleet Management, então no local a
  configuração do Alloy é gerada pelo chart (`podLogsViaLoki` e métricas ligados
  por values). Documentar.
- Dashboards: ConfigMaps provisionados no Grafana local, versionados no repo —
  os padrões de Kubernetes/pods e um dashboard de logs do namespace
  `querido-diario`.
- Idempotente, sem dependências externas além das já instaladas pelos scripts
  (`pycommon.py`, `ensure_helm`); Linux/macOS/Windows como o resto dos alvos.

## Esclarecimentos (revisão do design)

Respondidos pelo projeto (verificado com `kubectl auth can-i` em 2026-11-04):
- O ServiceAccount `openknowledge` **pode criar** no namespace
  `querido-diario`: Secrets (logo, os Secrets de release do Helm), ServiceAccounts,
  Roles, RoleBindings, DaemonSets, Deployments e `alloys.collectors.grafana.com`.
  Não pode: nada de escopo de cluster (CRDs, ClusterRoles, webhooks, nodes,
  `events` cluster-wide).
- O `values.yaml` de produção está limpo: o único endpoint é a URL pública do
  Fleet Management; nenhum IP ou hostname interno. Pode ser versionado como `-f`.

Decisões minhas (marcadas como minhas):
- **Operator:** o admin instala a versão que o chart 4.5.3 embute (`0.8.0`) e
  `alloy-operator.deploy: false` fica sincronizado com isso; subir a versão do
  chart exige checar a do operator e avisar o admin.
- **Credenciais:** o CI **nunca** cria nem altera o Secret
  `grafana-cloud-credentials`; ele é criado uma vez à mão. O passo do CI só
  verifica que existe e falha com mensagem clara se não existir.
- **Logs em prod:** nenhuma mudança de values para logs nesta etapa; o builder só
  verifica se `remoteConfig` (Fleet) é compatível com `podLogsViaLoki` e documenta
  o resultado.
- **Operator/ClusterRole do KSM:** o admin cria na instalação única junto com o
  operator, e o release Helm roda com eles desligados.

## Decisões confirmadas pelo mantenedor (após a revisão)

- **SDK injector: desligado** (`telemetryServices.sdkInjector.deploy: false`).
  Sem webhooks nem ClusterRoles do injector. Os que já existem no cluster
  ficam órfãos: o admin remove (pedido único por e-mail).
- **Migração: remover e reinstalar**, aceitando uma lacuna curta de métricas e
  logs (minutos). O builder define o procedimento e o texto de aviso.
- **KSM: mantém o acesso de cluster.** Verificado em 2026-11-04: o ClusterRole
  e o binding `grafana-cloud-kube-state-metrics` já existem e funcionam (o KSM
  lista `nodes` e `namespaces` e expõe `kube_node_*`). O admin só precisa
  **mantê-los**; o release Helm roda com a criação de ClusterRole do KSM
  desligada. O builder confirma qual valor do chart faz isso sem perder o
  acesso de cluster.

- **Operator já instalado** (verificado em 2026-11-04): Deployment
  `grafana-cloud-alloy-operator` (chart `alloy-operator-0.8.0`, imagem 1.13.0)
  no namespace `querido-diario`, CRD e Alloy CR `grafana-cloud-alloy` existentes
  — hoje aplicados por `kubectl apply`. Nada novo a instalar pelo admin.
  Como o Deployment do operator é namespaced, mas o chart com
  `alloy-operator.deploy: true` também cria os ClusterRoles dele (Forbidden no
  CI), a forma de deixar o release Helm gerenciar o Deployment e o Alloy CR
  (ClusterRoles/CRD pré-existentes, adoção dos objetos) fica com o builder.
  **Primeira tarefa do plano: spike** com `helm template` + `kubectl auth can-i`
  / `--dry-run=server` para validar que o `helm upgrade` do CI não exige
  escopo de cluster.

Resumo do que sobra para o admin (e-mail, uma vez): **manter** a CRD e os
ClusterRoles do operator e do KSM e **remover** os webhooks/ClusterRoles do SDK
injector. O `openknowledge` já tem permissão em `alloys.collectors.grafana.com`.

## Deixado ao builder

- Como instalar o conjunto de recursos de cluster (ver acima) e o texto do
  e-mail ao admin.
- Escolha entre `helm-diff` plugin ou `helm template | kubectl diff`.
- Versões dos charts de Prometheus/Loki/Grafana locais.
- Estrutura dos scripts (seguir `scripts/k8s_local_up.py`).
- Testes/validação: `helm template` e `helm lint` no CI (`checks.yml`) para os
  dois `values`.

## Fora do escopo desta etapa

Alertas, retenção, dashboards customizados de negócio, migração do Fleet
Management.
