# Viabilidade: PostgreSQL e OpenSearch no Kubernetes

> Análise gerada em 2026-05-09. Retomar quando a topologia do cluster for definida.

## TL;DR

Técnicamente viável, mas o custo-benefício depende da topologia do cluster (single vs. multi-node).

---

## Contexto atual

- Redis já roda no K8s com `Deployment` + `PVC` (`ReadWriteOnce`, 1Gi) — prova que workloads stateful básicos funcionam no cluster.
- PostgreSQL e OpenSearch estão explicitamente fora do escopo K8s atual (`k8s/README.md`), provisionados externamente via `docker-compose.dbs.yml`.
- 3 instâncias de PostgreSQL: `qd` (API), `backend` (Django), `receita`.

---

## PostgreSQL no K8s

**Viabilidade: Alta** — com as cautelas certas.

### Opções de implementação

| Abordagem | Complexidade | Adequado para |
|---|---|---|
| `StatefulSet` simples (padrão Redis atual) | Baixa | Single-node, sem HA |
| [CloudNativePG](https://cloudnative-pg.io/) operator | Média | Multi-node, failover, backup nativo |

### Riscos

- **Storage**: PVC precisa de `StorageClass` com I/O de SSD. NFS é problemático para Postgres (locks, fsync).
- **Backup**: No Docker Compose, backup é manual via volume ou `pg_dump`. No K8s, precisa de `CronJob` explícito — ou CloudNativePG resolve nativamente com WAL archiving.
- **Single-node**: Risco de perda de dados equivalente ao Docker Compose no mesmo host — não piora, mas não melhora.

---

## OpenSearch no K8s

**Viabilidade: Média** — mais exigente de recursos e configuração.

### Requisitos obrigatórios

1. **`vm.max_map_count = 262144`** no nó do host — configurar via `/etc/sysctl.conf` ou `initContainer` com `privileged: true`. Sem isso, OpenSearch não sobe.
2. **Memória**: Mínimo ~2–4 GB por nó para uso real. O cluster precisa ter folga.
3. **JVM heap**: Configurar via env `OPENSEARCH_JAVA_OPTS: "-Xms1g -Xmx1g"`.

### Opções de implementação

| Abordagem | Complexidade | Adequado para |
|---|---|---|
| `StatefulSet` simples | Baixa | Single-node, sem HA |
| [OpenSearch Operator](https://github.com/opensearch-project/opensearch-k8s-operator) | Média-alta | Multi-node, HA, rolling upgrades |

---

## Decisão pendente: topologia do cluster

| Topologia | Recomendação |
|---|---|
| **Single-node** | Manter no Docker Compose separado. Migrar para K8s traz overhead sem ganho de resiliência. |
| **Multi-node (≥ 2 nós)** | Migrar faz sentido — scheduling, restart automático, replicação (com operator). |

---

## Próximos passos (quando retomar)

1. Confirmar topologia do cluster (single vs. multi-node).
2. Verificar `StorageClass` disponível e se há backend SSD.
3. Decidir: `StatefulSet` simples ou operator (CloudNativePG / OpenSearch Operator).
4. Criar manifestos K8s para os bancos escolhidos.
5. Planejar estratégia de backup antes de migrar.
