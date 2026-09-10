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
- **Produção:** 3 instâncias (primary + 2 replicas), 250Gi storage (`ceph-block-hdd`)

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

- Upgrade de versão do PostgreSQL requer procedimento via CloudNativePG (rolling upgrade).
- StorageClass em produção deve ter I/O adequado; NFS é problemático para PostgreSQL (locks, fsync). Em produção usamos `ceph-block-hdd` (Revoada/CCSL).

## Atualização — Backup (2026-09-10)

O `spec.backup.barmanObjectStore` do `Cluster` aponta para o Ceph Object Store
do Revoada (`objectstore.ceph.revoada.ime.usp.br`, bucket `okbr-qd-postgres-bkp`),
configurado apenas em `k8s/overlays/production-local/` (gitignored — valores
reais de infra nunca vão pro git).

**Descoberta:** esse endpoint é servido pelo Traefik compartilhado do
cluster, sem rota/certificado próprio — por isso responde com o certificado
*default* autoassinado do Traefik, gerado em memória (troca a cada restart
do Traefik) e com um SAN que é um hostname interno aleatório, não
`objectstore.ceph.revoada.ime.usp.br`.

- **WAL archiving contínuo:** funciona. Contornamos com um secret
  `postgres-backup-ca` (referenciado via `endpointCA`) mantido atualizado por
  um `CronJob` (`postgres-backup-ca-refresh`, a cada 2h) que rebusca o
  certificado atual do endpoint e só atualiza o secret quando ele muda.
- **Backup completo (base backup):** **ainda não funciona.** O
  `barman-cloud-backup` faz validação estrita de hostname do certificado
  (diferente do WAL archiving, que só gera warning) — como o SAN do
  certificado do Traefik nunca vai bater com o hostname real, isso não é
  contornável do lado do cliente. **Sem um backup base, o WAL archiving
  sozinho não permite restore (PITR)** — ou seja, o backup ainda não é
  utilizável na prática.
- **Pendente:** pedido aberto ao admin do CCSL para configurar uma rota
  própria no Traefik (com certificado com SAN correto) para esse host, ou
  indicar um endpoint que não passe pelo Traefik compartilhado. Ver
  `k8s/overlays/production-local/DEPLOY.md` (Fase 2/3.3) e
  `k8s/overlays/production-local/postgres-backup-ca-refresh.yaml`.
- Drift conhecido corrigido: o storage do `Cluster` havia sido expandido
  manualmente em produção (100Gi → 250Gi) sem atualizar o overlay; o overlay
  já reflete o valor real.
