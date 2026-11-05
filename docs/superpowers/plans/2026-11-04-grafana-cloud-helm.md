# Grafana Cloud via Helm + monitoramento local — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar o YAML estático do Grafana Cloud por um release Helm real operado por Makefile e CI, e criar um alvo à parte de monitoramento local no kind.

**Architecture:** Um módulo Python (`scripts/grafana_cloud.py`, stdlib) concentra render, checagem de escopo de cluster e comandos `helm`. O Makefile e o `deploy.yml` o chamam. O monitoramento local reutiliza o chart `grafana/k8s-monitoring` com `values-local.yaml` apontando para Prometheus, Loki e Grafana locais.

**Tech Stack:** Helm, kubectl, Python 3.9+ (stdlib, `unittest`), GNU Make, GitHub Actions, kind.

**Spec:** `docs/superpowers/specs/2026-11-04-grafana-cloud-helm-design.md`

## Global Constraints

- Namespace: `querido-diario`. Chart: `grafana/k8s-monitoring`, versão fixa `4.5.3` (`GRAFANA_CLOUD_CHART_VERSION` no Makefile).
- **Nome do release: `grafana-cloud`** (o mesmo do `helm template` atual). Isso desvia do nome `k8s-monitoring` citado no spec: mudar o nome renomearia o DaemonSet, o Alloy CR e os IDs dos coletores no Fleet Management (`grafana-cloud-revoada-qd-querido-diario-alloy-<nó>`).
- `cluster.name: revoada-qd`. `telemetryServices.sdkInjector.deploy: false`.
- O `helm upgrade` do CI **nunca** pode exigir escopo de cluster (ServiceAccount `openknowledge` só tem namespace). Operator, CRD e ClusterRoles do operator e do KSM já existem e ficam com o admin.
- O CI nunca cria nem altera o Secret `grafana-cloud-credentials`; só verifica que existe.
- Nada de IP, hostname interno ou token no git. Scripts Python só com stdlib, compatíveis com Linux/macOS/Windows (usar `pycommon`).
- Monitoramento local: alvo separado `make k8s-local-monitoring-up`; **não** entra no `k8s-local-up`.
- Prod: sem mudança de values para logs nesta etapa.

## Review Focus

1. `helm upgrade` interrompido deixa o release em `pending-upgrade`: `--atomic` + `--timeout` e um alvo de rollback.
2. Secret `grafana-cloud-credentials` ausente: falhar cedo com mensagem clara, antes do `helm`.
3. Repositório Helm indisponível no CI: falhar com erro nítido, sem aplicar nada parcial.
4. Subir `GRAFANA_CLOUD_CHART_VERSION` sem revisar a versão do operator: o `check` precisa acusar recursos de cluster novos.
5. Máquina local sem memória para o stack: `k8s-local-monitoring-up` avisa e é idempotente.

---

### Task 1: Spike + `check` — o release não pode exigir escopo de cluster

**Files:**
- Create: `scripts/grafana_cloud.py`
- Create: `scripts/tests/test_grafana_cloud.py`
- Modify: `k8s/monitoring/grafana-cloud/values.yaml`

**Interfaces:**
- Produces: `CLUSTER_SCOPED_KINDS: frozenset[str]`; `cluster_scoped_resources(manifest_yaml: str) -> list[str]` (itens `"Kind/name"`); `render(chart_version: str, values: Path) -> str` (`helm template --include-crds`, release `grafana-cloud`, namespace `querido-diario`); CLI `python3 scripts/grafana_cloud.py check` (exit 1 se houver recurso de cluster).

- [ ] **Step 1: Write the failing test** em `scripts/tests/test_grafana_cloud.py` (`unittest`):
  - `test_detects_clusterrole`: YAML com `ClusterRole/x` → `["ClusterRole/x"]`.
  - `test_ignores_namespaced`: `Deployment`, `Role` → `[]`.
  - `test_detects_crd_and_webhooks`: `CustomResourceDefinition`, `MutatingWebhookConfiguration`, `ValidatingWebhookConfiguration`, `ClusterRoleBinding` → todos listados.
  - `test_multi_document_and_empty_docs`: documentos vazios e `---` repetidos não quebram.
- [ ] **Step 2: Run** `python3 -I -m unittest scripts/tests/test_grafana_cloud.py -v`. Expected: FAIL (módulo inexistente).
- [ ] **Step 3: Implement** `CLUSTER_SCOPED_KINDS` (CRD, ClusterRole, ClusterRoleBinding, Mutating/ValidatingWebhookConfiguration, Namespace, PriorityClass, StorageClass), `cluster_scoped_resources` (parse por split de `---` e regex em `kind:`/`metadata.name`, sem PyYAML) e `render`. Repo add/update `grafana` antes do template.
- [ ] **Step 4: Run** o teste. Expected: PASS.
- [ ] **Step 5: Spike real.** Rodar `python3 scripts/grafana_cloud.py check`. Hoje deve listar o operator, KSM e injector. Ajustar `values.yaml` até a saída ser vazia: `alloy-operator.deploy: false`, `telemetryServices.sdkInjector.deploy: false`, e o valor do sub-chart `kube-state-metrics` que desliga a criação do ClusterRole mantendo o `serviceAccount` `grafana-cloud-kube-state-metrics` (consultar `values.yaml` do chart; o binding do admin aponta para esse SA). Expected: `check` imprime "sem recursos de escopo de cluster" e sai com 0.
- [ ] **Step 6: Validar contra o cluster** (sem aplicar): `python3 scripts/grafana_cloud.py render | kubectl apply --dry-run=server -n querido-diario -f -`. Expected: sem `Forbidden`. Se o Deployment do operator ficar órfão (por `deploy: false`), registrar a decisão em `docs/grafana-cloud.md` (Task 5): deixar o objeto atual como está, sem gerenciamento Helm, ou adotá-lo — o builder escolhe e anota.
- [ ] **Step 7: Commit** `feat: valida que o release Helm do Grafana Cloud não exige escopo de cluster`.

---

### Task 2: Comandos `helm` + alvos de Makefile

**Files:**
- Modify: `scripts/grafana_cloud.py`, `scripts/tests/test_grafana_cloud.py`, `Makefile`

**Interfaces:**
- Consumes: `render`, `check` (Task 1).
- Produces: `helm_args(action: str, chart_version: str, values: Path) -> list[str]` para `action` em `install|diff`; `credentials_secret_exists() -> bool`; CLI `install|diff|status|rollback`; alvos `grafana-cloud-check`, `grafana-cloud-diff`, `grafana-cloud-install`, `grafana-cloud-status`, `grafana-cloud-rollback`.

- [ ] **Step 1: Write the failing test:** `helm_args("install", "4.5.3", Path("v.yaml"))` contém, em ordem, `upgrade --install grafana-cloud grafana/k8s-monitoring --version 4.5.3 -n querido-diario -f v.yaml --atomic --timeout 10m`; `helm_args("diff", ...)` usa `template … | kubectl diff` (retorna o `render` + `["kubectl","diff","-n","querido-diario","-f","-"]`); ação desconhecida levanta `ValueError`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** `install` roda `check`, depois `credentials_secret_exists()` (via `pc.run_ok(["kubectl","get","secret","grafana-cloud-credentials","-n","querido-diario"])`; se falso, `pc.err` com o comando de criação de `docs/grafana-cloud.md` e saída 1), depois `helm upgrade`. `rollback` = `helm rollback grafana-cloud 0 -n querido-diario`. `status` = `helm status` + `helm list`.
- [ ] **Step 4: Makefile:** substituir `grafana-cloud-render` pelos alvos acima (cada um com `##` de help, em `.PHONY`).
- [ ] **Step 5: Run** testes e `make grafana-cloud-check`. Expected: PASS / exit 0.
- [ ] **Step 6: Commit** `feat: alvos make para instalar, diffar e reverter o Grafana Cloud via Helm`.

---

### Task 3: CI — validação e deploy

**Files:**
- Modify: `.github/workflows/checks.yml`, `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: CLI de Task 2.

- [ ] **Step 1: `checks.yml`:** novo job `grafana-cloud` com `azure/setup-helm@v4`, `python3 -I -m unittest discover scripts/tests` e `python3 scripts/grafana_cloud.py check`. Expected no PR: verde; quebra se alguém reintroduzir recurso de cluster.
- [ ] **Step 2: `deploy.yml`:** depois de "Aplica overlay de produção" e antes de "Aguarda rollout": `azure/setup-helm@v4`, passo "Diff Grafana Cloud" (`|| true`) e passo "Instala/atualiza Grafana Cloud" (`python3 scripts/grafana_cloud.py install`). Sem tocar no Secret de credenciais.
- [ ] **Step 3: Validar sintaxe:** `python3 -c "import yaml;[yaml.safe_load(open(f)) for f in ('.github/workflows/checks.yml','.github/workflows/deploy.yml')]"`. Expected: sem erro.
- [ ] **Step 4: Commit** `ci: valida e instala o release Helm do Grafana Cloud`.

---

### Task 4: Monitoramento local (kind)

**Files:**
- Create: `k8s/local/monitoring/values-local.yaml`, `k8s/local/monitoring/dashboards/*.json` (ConfigMaps gerados), `scripts/k8s_local_monitoring.py`
- Modify: `Makefile`, `scripts/tests/test_grafana_cloud.py` (ou novo `test_k8s_local_monitoring.py`)

**Interfaces:**
- Produces: `python3 scripts/k8s_local_monitoring.py up|down|status|grafana`; alvos `k8s-local-monitoring-up`, `k8s-local-monitoring-down`, `k8s-local-monitoring-status`, `k8s-local-monitoring-grafana`; constante `MONITORING_NAMESPACE = "monitoring"`.

- [ ] **Step 1: Write the failing test:** `values-local.yaml` tem `podLogsViaLoki.enabled: true` restrito ao namespace `querido-diario`, `node-exporter.deploy: true`, `cluster.name: local`, destinos `prometheus` e `loki` apontando para serviços do namespace `monitoring`, e **não** contém `remoteConfig`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `values-local.yaml` (Alloy gerado pelo chart, sem Fleet), `up` (idempotente: `pc.check_docker`, exigir cluster kind `querido-diario-dev` existente, `helm upgrade --install` de `prometheus-community/prometheus`, `grafana/loki` (modo SingleBinary), `grafana/grafana` com dashboards provisionados via sidecar, depois o `k8s-monitoring` com `values-local.yaml`; avisar se memória disponível < 4 GiB), `down` (desinstala releases e namespace), `status` (`kubectl get pods -n monitoring`), `grafana` (port-forward `3000`). Dashboards: ConfigMaps com label do sidecar para "Kubernetes / Pods" e "Logs do querido-diario".
- [ ] **Step 4: Run** testes → PASS; `make k8s-local-monitoring-up` num kind existente. Expected: pods do namespace `monitoring` `Running`.
- [ ] **Step 5: Smoke:** `make k8s-local-monitoring-grafana`; no Explore, `{namespace="querido-diario", container="data-processing"}` devolve linhas, e o dashboard de pods mostra o namespace.
- [ ] **Step 6: Commit** `feat: monitoramento local (Prometheus, Loki, Grafana, Alloy) como alvo separado`.

---

### Task 5: Cutover em produção, limpeza e documentação

**Files:**
- Delete: `scripts/grafana_cloud_render.py`, `k8s/monitoring/grafana-cloud/manifests.yaml`, `cluster-scoped.yaml`, `kustomization.yaml`
- Modify: `k8s/overlays/production/kustomization.yaml:14-17` (remover o recurso `../../monitoring/grafana-cloud`), `docs/grafana-cloud.md`, `k8s/README.md:240-251`, `CLAUDE.md`

**Interfaces:**
- Consumes: Tasks 1–4. Passos 1 e 4 afetam produção: **pedir confirmação ao mantenedor antes de cada um.**

- [ ] **Step 1: Pré-requisito do admin (e-mail):** confirmar que a CRD e os ClusterRoles do operator e do KSM seguem existindo e remover os webhooks e ClusterRoles do SDK injector. Registrar o texto do e-mail em `docs/grafana-cloud.md`.
- [ ] **Step 2: Remover** do repo os arquivos listados e a referência no overlay. Run: `kubectl kustomize k8s/overlays/production | grep -ci grafana`. Expected: `0`.
- [ ] **Step 3: Documentar** em `docs/grafana-cloud.md`: fluxo `make grafana-cloud-*`, CI, o que sobra para o admin, diferença Fleet vs. local, procedimento de cutover e rollback; ajustar `k8s/README.md` e `CLAUDE.md` (alvos, estrutura de arquivos, monitoramento local).
- [ ] **Step 4: Cutover (produção, com confirmação):** antes do merge, remover os recursos namespaced do release antigo (`git show HEAD:k8s/monitoring/grafana-cloud/manifests.yaml | kubectl delete -n querido-diario -f -`, preservando o Secret `grafana-cloud-credentials`), porque `kubectl apply -k` sem `--prune` não os apaga e o Helm recusaria adotar objetos existentes. Depois o deploy do CI faz o `helm upgrade --install`. Expected: `helm list -n querido-diario` mostra `grafana-cloud` `deployed`; DaemonSet do Alloy `Running` em todos os nós; coletores voltam ao Fleet Management; dados voltam ao Grafana Cloud.
- [ ] **Step 5: Commit** `refactor: Grafana Cloud passa a ser um release Helm; remove o render estático`.

---

## Self-review (resumo)

- Cobertura do spec: release Helm via make e CI (T1–T3); admin só mantém cluster-scope (T1, T5); SDK injector desligado e KSM mantido (T1); migração remover/reinstalar (T5); monitoramento local em alvo separado (T4); docs (T5).
- Fora do plano, por decisão do spec: alterar logs em prod; alertas; Fleet.
- Ponto a validar no spike (T1): o nome exato do valor que desliga o ClusterRole do KSM e o destino do Deployment do operator quando `alloy-operator.deploy: false`.
