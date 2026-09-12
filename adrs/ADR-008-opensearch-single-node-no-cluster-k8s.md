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

## Atualização — Migração de storage e resources (2026-09-11/12)

Em produção, o PVC de dados havia divergido do `volumeClaimTemplates` do
manifesto por conta de uma migração manual anterior (ver histórico do
`statefulset.yaml`): o `StatefulSet` ao vivo referenciava um PVC
(`opensearch-data-v2`) direto via `volumes:`, porque `volumeClaimTemplates` é
imutável num `StatefulSet` já existente. Isso quebrava todo `kubectl apply -k`
do overlay de produção nesse recurso (erro `Forbidden: updates to statefulset
spec...`), embora sem impedir os outros recursos de aplicarem.

Reconciliado via snapshot/restore:

1. Provisionado um PVC dedicado (`opensearch-snapshot-repo`, 300Gi,
   **`ceph-block-nvme`**, não `ceph-block-hdd` — snapshot/restore é I/O-bound e
   SSD reduz bastante o tempo) como repositório `fs` do OpenSearch
   (`path.repo` no `opensearch.yml`).
2. Snapshot completo do índice (~275G, 23 shards) — **~2h** em HDD (dado de
   origem) mesmo escrevendo em SSD (o gargalo foi a leitura do
   `opensearch-data-v2`, que ficou em `ceph-block-hdd`).
3. `StatefulSet` deletado (não afeta PVCs) e recriado usando o
   `volumeClaimTemplates` do manifesto — provisionou um PVC novo e vazio
   (`opensearch-data-opensearch-0`, nome no padrão
   `<template>-<statefulset>-<ordinal>`).
4. Restore **só do índice `queridodiario`** (`include_global_state: false`,
   `indices: "queridodiario"`) — os índices internos
   (`.opendistro_security`, `security-auditlog-*`, `top_queries-*`, etc.)
   foram deixados de fora de propósito, pra não sobrescrever a config de
   segurança recém-inicializada no cluster novo. Restore do shard único
   (`pri: 1, rep: 0`) é sequencial, não paralelo como o snapshot — levou mais
   tempo que o esperado mesmo em SSD.
5. Verificado: `274.8gb`/`991584 docs`, idêntico ao volume antigo antes de
   apagar `opensearch-data-v2`.

Também aumentados os recursos do container (`2 CPU/16Gi` → `4 CPU/24Gi`
limits, `500m/12Gi` → `1 CPU/16Gi` requests) — mais memória disponível pro
page cache do SO ajuda em cargas I/O-bound como snapshot/restore, além do
uso normal de indexação/busca.

### Gotcha: `DISABLE_INSTALL_DEMO_CONFIG=true` + volume de dados vazio = senha demo

Num `StatefulSet` com `plugins.security.allow_default_init_securityindex: true`
mas `DISABLE_INSTALL_DEMO_CONFIG=true` (nosso caso, ver comentário em
`certs.yaml`), um **volume de dados vazio** faz o índice
`.opendistro_security` ser auto-inicializado com o usuário `admin` na senha
**demo padrão** (`admin`/`admin`) — não com `OPENSEARCH_INITIAL_ADMIN_PASSWORD`,
porque é o `install_demo_configuration.sh` (desabilitado) quem normalmente
aplica essa substituição. Isso só aparece na prática quando o volume de
dados é recriado do zero (como nesta migração) — um cluster que já vem
rodando há tempo nunca reproduz o problema, porque o índice de segurança já
existe e não é reinicializado.

**Sintoma:** `AuthenticationException(401)` nos serviços que leem a senha do
secret (`api`, `backend`, etc.), mas `curl -u admin:admin` autentica.

**Fix:** a API REST bloqueia mudar a senha do usuário `admin` porque ele é
`reserved` (`{"status":"FORBIDDEN","message":"Resource 'admin' is reserved."}`).
É preciso usar a ferramenta `securityadmin.sh` (em
`/usr/share/opensearch/plugins/opensearch-security/tools/`), autenticada por
certificado cliente (mTLS) casando com `plugins.security.authcz.admin_dn` —
no nosso caso, o mesmo certificado de servidor (`opensearch-server-tls`)
serve como certificado de admin, já que o `admin_dn` configurado é o mesmo
`CN` do certificado do servidor. Passos:

1. A chave do secret `opensearch-server-tls` vem em PKCS#1
   (`BEGIN RSA PRIVATE KEY`) — `securityadmin.sh` (Java) só aceita PKCS#8
   (`BEGIN PRIVATE KEY`). Converter com
   `openssl pkcs8 -topk8 -nocrypt -in tls.key -out key-pkcs8.pem` (a imagem
   do OpenSearch não tem `openssl`; usar um pod efêmero à parte pra isso).
2. Em versões recentes do OpenSearch (2.x), `securityadmin.sh` conecta via
   **porta REST (9200)**, não mais a porta de transporte (9300) — e via
   `localhost`, não o Service (que só expõe 9200; e tráfego pod-a-pod na
   9300 parece bloqueado por política de rede no Revoada de qualquer forma).
3. Gerar o hash da senha: `hash.sh -p "$SENHA"` (usar a env var já montada
   no pod a partir do secret, nunca a senha em texto puro num argumento
   solto).
4. Montar um `internal_users.yml` só com o(s) usuário(s) desejado(s)
   (`_meta.type: internalusers`) e aplicar com
   `securityadmin.sh -f internal_users.yml -t internalusers -icl -nhnv -cacert ... -cert ... -key ... -h localhost -p 9200`
   — isso **substitui inteiramente** a lista de internal users pelo
   conteúdo do arquivo (não faz merge), então serve também pra remover
   usuários demo não usados (aproveitado aqui: `logstash`, `kibanaserver`,
   `kibanaro`, `readall`, `snapshotrestore`, `anomalyadmin` removidos, só
   `admin` ficou).
