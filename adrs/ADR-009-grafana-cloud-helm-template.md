# ADR-009: Grafana Cloud via `helm template | kubectl apply` (sem release Helm)

**Data:** 2026-11-05
**Status:** Decidido

## Contexto

O Grafana Cloud em produção usa o chart `grafana/k8s-monitoring` (4.5.3). A
intenção inicial era um release Helm (`helm upgrade --install --atomic`)
operado pelo CI. O ServiceAccount de deploy (`openknowledge`) só tem permissão
no namespace `querido-diario`.

O `helm install` real executa chamadas `lookup` do chart, que `helm template`
não executa:

- `templates/_platform_validations.tpl:15` lista todos os Nodes;
- `templates/collectors/_collector_notes.tpl:53` lê um Namespace.

Na primeira execução no CI, o install falhou com
`nodes is forbidden ... cannot list resource "nodes" ... at the cluster scope`.
O `helm template` funciona e renderiza exatamente 6 objetos namespaced
(ServiceAccount, ConfigMap, 2 Services, Deployment do kube-state-metrics e CR
`Alloy`).

## Decisão

O CI e o `make grafana-cloud-install` rodam
`helm template | kubectl apply -n querido-diario -f -`:

- chart fixado (`GRAFANA_CLOUD_CHART_VERSION`, 4.5.3) e Helm fixado no CI;
- valores versionados em `k8s/monitoring/grafana-cloud/values.yaml`;
- nada gerado é commitado;
- antes de aplicar, `check` falha se o render contiver recursos de escopo de
  cluster e o script exige o Secret `grafana-cloud-credentials`.

## Consequências

- Não há release Helm: sem `helm list`, `helm rollback` nem `--atomic`
  (aceito). `helm list` mostra no máximo o release interno `grafana-cloud-alloy`,
  gerenciado pelo alloy-operator.
- Rollback: reverter o commit e redeployar (o CI reaplica os valores anteriores).
- `kubectl apply` não faz prune: objetos que uma nova versão do chart deixar de
  renderizar ficam órfãos e devem ser apagados à mão. O
  `rolebinding/grafana-cloud-alloy-manager` (do admin) nunca deve ser apagado.
- Atualização: editar `values.yaml` ou a versão do chart, abrir PR; `make
  grafana-cloud-diff` mostra o que mudará.
- Detalhes operacionais em `docs/grafana-cloud.md`.

## Alternativas consideradas

| Alternativa | Descartada por |
|---|---|
| `helm upgrade --install --atomic` | Exige que o ServiceAccount de deploy tenha `list nodes` e `get namespaces` no escopo de cluster (RBAC concedido pelo admin), por causa dos `lookup` do chart. Se o admin conceder, o `install` pode voltar a usar `helm upgrade --install --atomic` |
| YAML estático gerado e commitado | Já usado antes; gerava arquivos grandes e derivados no git, difíceis de revisar e de atualizar |
