# ADR-008: OpenSearch single-node dentro do cluster k8s em produção

**Data:** 2026-07-09
**Status:** Decidido
**Supera:** [ADR-003](./ADR-003-opensearch-externo-em-producao.md)

## Contexto

O ADR-003 optou por rodar o OpenSearch de produção numa VM separada via Docker
Compose, para evitar overhead operacional e requisitos de host (`vm.max_map_count`)
num cluster k8s gerenciado.

O ambiente de produção real (Revoada, CCSL/IME-USP) é um cluster K3s próprio da
equipe, não um serviço gerenciado por terceiros — os nodes não têm as restrições
que motivaram o ADR-003, e manter uma VM separada só para o OpenSearch adiciona
superfície operacional (patch, backup, rede) sem necessidade, para um serviço que
já vai rodar **single-node** (sem HA) de qualquer forma.

## Decisão

OpenSearch de produção passa a rodar como `StatefulSet` de 1 réplica no
namespace `querido-diario`, em `k8s/overlays/production/opensearch/statefulset.yaml`:

- **StatefulSet** (não Deployment): identidade estável e `volumeClaimTemplates`,
  mesmo com 1 réplica — facilita evoluir para multi-node no futuro sem reescrever
  o manifesto.
- **StorageClass:** `ceph-block-hdd` (padrão do cluster, já usado pelo Postgres).
  A replicação do Ceph (tipicamente 3x) cobre a falta de HA a nível de aplicação.
  Reavaliar para `ceph-block-nvme` se a latência de indexação/busca virar gargalo
  em produção.
- **Segurança:** plugin de segurança do OpenSearch **habilitado** (diferente do
  overlay de dev, que roda com `plugins.security.disabled=true`). Usuário `admin`
  com senha vinda do secret `app-secret` (chave `QUERIDO_DIARIO_OPENSEARCH_PASSWORD`),
  reaproveitando o valor já usado pela API/backend para autenticar no OpenSearch —
  evita manter a senha duplicada em dois secrets.
- **`vm.max_map_count`:** garantido via `initContainer` com `securityContext.privileged: true`
  rodando `sysctl -w vm.max_map_count=262144` no host, a cada início do pod.
- **Imagem:** `opensearchproject/opensearch:2.19.1` em produção e dev (versão
  única entre os dois ambientes). Note-se que `OPENSEARCH_INITIAL_ADMIN_PASSWORD`
  só é respeitado a partir da 2.12 — versões anteriores caem silenciosamente no
  usuário/senha demo `admin/admin`.
- **Sem exposição externa:** apenas `Service` ClusterIP, sem `IngressRoute` — acesso
  só de dentro do namespace.

### Dependência: `vm.max_map_count` e Pod Security Admission

O uso de `privileged: true` no initContainer depende do namespace `querido-diario`
permitir containers privilegiados. Caso o CCSL negue isso por política de cluster,
o fallback é configurar `vm.max_map_count=262144` diretamente nos nodes do Revoada
(`/etc/sysctl.conf` + `sysctl -p`) e remover o initContainer do manifesto.

## Alternativas consideradas

| Alternativa | Descartada por |
|---|---|
| Manter VM externa (ADR-003) | Overhead operacional desnecessário num cluster próprio da equipe sem as restrições que motivaram a decisão original |
| Deployment em vez de StatefulSet | Funciona, mas PVC `ReadWriteOnce` pode travar reagendamento em node diferente; StatefulSet é mais correto semanticamente e sem custo extra |
| OpenSearch Operator | Complexidade desnecessária para um único nó (mesmo racional do ADR-003) |
| `local-path` StorageClass | Melhor performance, mas perde a replicação do Ceph — falha de disco do node perderia o índice por completo, exigindo reprocessamento total via `data-processing` |
| `ceph-filesystem` (RWX) | RWX não traz benefício (não há múltiplos writers) e CephFS tem overhead de metadados pior para os muitos arquivos pequenos dos segmentos Lucene |

## Consequências

- Esta decisão foi tomada antes da VM do ADR-003 chegar a ser provisionada —
  `docker-compose.opensearch.yml` foi removido do repositório sem nunca ter
  rodado em produção.
- O overlay de dev também foi unificado para usar `StatefulSet` (mesma forma
  do manifesto de produção), em vez do `Deployment` usado até então — mantém
  plugin de segurança desabilitado e recursos menores, mas a estrutura do
  recurso (StatefulSet + volumeClaimTemplates) é igual à de produção.
- Backup do índice passa a ser responsabilidade do cluster k8s (snapshot do PVC
  Ceph e/ou snapshot API do próprio OpenSearch).
- Atualização de versão do OpenSearch passa a seguir o mesmo fluxo dos demais
  serviços (bump de tag de imagem no manifesto).
- `QUERIDO_DIARIO_OPENSEARCH_HOST` no secret de produção aponta para o serviço
  interno: `https://opensearch.querido-diario.svc.cluster.local:9200`.
