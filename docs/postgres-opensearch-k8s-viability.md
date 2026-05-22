# ADR-001: PostgreSQL e OpenSearch no Kubernetes

**Data:** 2026-05-09  
**Status:** Decidido e implementado

## Contexto

O cluster Kubernetes precisava de uma estratégia para PostgreSQL e OpenSearch. Redis já rodava como `Deployment` + PVC com sucesso, confirmando que workloads stateful básicos funcionam no cluster. A principal dúvida era sobre topologia (single-node vs. multi-node) e complexidade operacional.

## Decisão

### PostgreSQL → CloudNativePG operator

**Adotado.** O cluster usa [CloudNativePG](https://cloudnative-pg.io/) para gerenciar PostgreSQL:

- **Dev (kind):** 1 instância, 1Gi storage
- **Produção:** 3 instâncias (primary + 2 replicas), 100Gi storage, StorageClass SSD

Os três bancos (`queridodiario`, `backend`, `companies`) são criados automaticamente no primeiro boot via `postInitSQL` no `Cluster` manifest.

Manifestos em `k8s/base/postgres/`.

### OpenSearch → externo em produção, Deployment simples em dev

**Mantido externo em produção.** OpenSearch exige `vm.max_map_count = 262144` no host e 2–4 GB de RAM por nó, o que torna custoso rodar com HA dentro do cluster. Em produção, um serviço OpenSearch gerenciado externo é mais adequado.

**Em desenvolvimento (kind):** roda como `Deployment` simples com `DISABLE_SECURITY_PLUGIN=true` e sem persistência — suficiente para testes locais.

Manifesto em `k8s/overlays/dev/infra/opensearch.yaml`.

## Alternativas consideradas

| Alternativa | Descartada por |
|---|---|
| PostgreSQL como `StatefulSet` simples | Sem HA, backup manual — CloudNativePG resolve ambos nativamente |
| OpenSearch Operator em produção | Overhead operacional alto; serviço externo gerenciado é mais simples |
| PostgreSQL externo (como OpenSearch) | CloudNativePG no cluster é mais simples de operar e já provisionado |

## Consequências

- Backup do PostgreSQL: CloudNativePG suporta WAL archiving e backup via `ScheduledBackup` — ainda não configurado; item pendente antes de ir para produção com dados reais.
- OpenSearch em prod: depende de serviço externo (ex: AWS OpenSearch Service, Bonsai). Configurado via secret `app-secret` na chave `QUERIDO_DIARIO_OPENSEARCH_HOST`.
