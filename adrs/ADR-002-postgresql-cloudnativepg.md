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

**Histórico:** o endpoint era servido pelo Traefik compartilhado do cluster,
sem rota/certificado próprio, e respondia com o certificado *default*
autoassinado e efêmero do Traefik (SAN aleatório). Isso bloqueava o
`barman-cloud-backup` (validação estrita de hostname) e o WAL archiving só
funcionava com um `CronJob` (`postgres-backup-ca-refresh`) que rebuscava o
certificado a cada 2h.

**Resolução (2026-09-19):** o CCSL forneceu uma CA própria do Revoada,
estável (válida até 2036), e o endpoint passou a apresentar um certificado
assinado por ela. Ela é o secret `postgres-backup-ca` (chave `ca.crt`,
referenciado via `endpointCA`), criado pelo passo "Cria/atualiza secret
postgres-backup-ca" do `deploy.yml` a partir do secret do GitHub
`POSTGRES_BACKUP_CA_CRT`. O CronJob de refresh foi removido.

- **WAL archiving e backup completo:** funcionando. Um `Backup` manual
  terminou em `completed`, então há base backup + WAL e o restore (PITR) é
  utilizável.
- **Gotcha:** o CNPG copia o `endpointCA` para
  `/controller/certificates/backup-barman-ca.crt` **só quando o pod sobe** e
  não recarrega quando o secret muda. Ao trocar a CA é preciso um restart em
  rolling do cluster
  (`kubectl annotate cluster postgres kubectl.kubernetes.io/restartedAt=<data>`),
  senão o arquivamento continua falhando com `CERTIFICATE_VERIFY_FAILED`
  (o WAL fica acumulando no primary). Isso já causou ~5 dias de arquivamento
  parado (14–19/09), com 983 WAL pendentes drenados após o restart.
- Drift conhecido corrigido: o storage do `Cluster` havia sido expandido
  manualmente em produção (100Gi → 250Gi) sem atualizar o overlay; o overlay
  já reflete o valor real.
