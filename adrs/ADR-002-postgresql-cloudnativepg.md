# ADR-002: PostgreSQL com CloudNativePG

**Data:** 2026-05-09
**Status:** Decidido

## Contexto

O cluster Kubernetes precisava de uma estratégia para PostgreSQL. Redis já
rodava como `Deployment` + PVC, confirmando que workloads stateful básicos
funcionam. A dúvida era entre rodar PostgreSQL no cluster ou manter externo, e
se usar operator ou StatefulSet simples.

Três bancos são necessários: `queridodiario` (API/data-processing), `backend`
(Django), `companies` (dados de receita federal).

## Decisão

Usar o **[CloudNativePG operator](https://cloudnative-pg.io/)** para gerenciar
PostgreSQL dentro do cluster:

- **Dev (kind):** 1 instância, 1Gi storage
- **Produção:** 3 instâncias (primary + 2 replicas), 100Gi storage, StorageClass SSD

Os três bancos são criados automaticamente no primeiro boot via `postInitSQL` no
manifest do `Cluster`.

Manifestos em `k8s/base/postgres/`.

## Alternativas consideradas

| Alternativa | Descartada por |
|---|---|
| `StatefulSet` simples | Sem HA, sem backup nativo, sem failover automático |
| PostgreSQL externo (VM/RDS) | Mais simples porém adiciona dependência externa; CloudNativePG no cluster já resolve |
| Zalando Postgres Operator | CloudNativePG tem comunidade mais ativa e melhor integração com k8s nativo |

## Consequências

- **Pendente:** backup do PostgreSQL via WAL archiving (`ScheduledBackup` CRD) — necessário antes de usar em produção com dados reais.
- Upgrade de versão do PostgreSQL requer procedimento via CloudNativePG (rolling upgrade).
- StorageClass em produção deve ter I/O de SSD; NFS é problemático para PostgreSQL (locks, fsync).
