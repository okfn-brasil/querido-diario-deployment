# Plano de migração: VPS antiga → Revoada (cutover de produção)

Contexto e decisões por trás de `scripts/db-migration/`. Este documento cobre
o que aconteceu, o que já foi corrigido, e os passos que faltam — em ordem.

## Contexto

Produção no Revoada ficou ~12 dias com `api`, `backend`, `celery-beat`,
`celery-worker`, `data-processing` e `opensearch` em crashloop, nunca
efetivamente no ar. Causas raiz (todas já corrigidas no repo):

| Sintoma | Causa raiz | Commit |
|---|---|---|
| `api`/`data-processing`: `CreateContainerConfigError` | `deploy.yml` nunca setava `QD_DATA_DB_HOST`/`POSTGRES_COMPANIES_HOST` no `app-secret` | `e68d9a3` |
| `backend`/`celery-*`: crashloop, `ValueError: Invalid IPv6 URL` | `deploy.yml` montava `QD_BACKEND_DB_URL` sem URL-encoding da senha | `e68d9a3` |
| `opensearch-0`: crashloop, `AccessDeniedException` no volume | Pod sem `securityContext.fsGroup`, volume Ceph montado como root | `e72eae7` |
| (latente, não travava boot) `backend` nunca roda migrations Django | `deployment.yaml` só chama `gunicorn`, sem `migrate` (docker-compose antigo tinha `migrate && runserver`, perdido na migração pro k8s) | fix local no `k8s/base/backend/deployment.yaml` (initContainer `migrate`) |
| PVC do OpenSearch em produção era 20Gi | OpenSearch da VPS antiga tem **~400G** de dados reais — 20Gi nunca teria cabido | fix local no `k8s/overlays/production/opensearch/statefulset.yaml` (450Gi) |
| Heap do OpenSearch (1GB) insuficiente pra ~400G de índice | `OPENSEARCH_JAVA_OPTS` fixo em `-Xms1g -Xmx1g`, `resources` em 2500Mi/1500Mi | fix local: heap 8g (`-Xms8g -Xmx8g`), `resources.limits.memory: 16Gi` (heap = ~50% da memória do container, regra geral da JVM), `requests.memory: 12Gi`, cpu limit/request `2`/`500m` |
| `postgres-credentials`/`app-secret`: `role "querido_diario_db_user" does not exist` em loop desde o boot do pod (5+ dias, 1638 tentativas nos logs) | Secret com usuário/senha de antes da migração pro CNPG — o bootstrap real usa owner `admin` (`k8s/base/postgres/cluster.yaml`) | fix manual no cluster: `ALTER USER admin WITH PASSWORD ...` + `postgres-credentials`/`app-secret` recriados com `admin`; commit `62d3149`/`885d719` |
| `api`: `Failed to resolve 'os.queridodiario.org.br'` | `QUERIDO_DIARIO_OPENSEARCH_HOST` no `app-secret` apontava pra VM externa antiga (pré-ADR-008) | fix manual no `app-secret` pra `https://opensearch.querido-diario.svc.cluster.local:9200` |
| `backend`: `SystemCheckError` (CSRF_TRUSTED_ORIGINS/CORS_ALLOWED_ORIGINS) | `QD_BACKEND_ALLOWED_ORIGINS`/`QD_BACKEND_CSRF_TRUSTED_ORIGINS` = `"*"`, inválido pro Django 4+/django-cors-headers | commit `62d3149` |
| `frontend`/`backend`/`api`: domínio errado em toda a config (`.ok.org.br`) | Domínio real é `queridodiario.org.br` (bate com o certificado TLS já emitido) | commit `62d3149` |
| `backend`: `PermissionError` no `lost+found` do PVC de estáticos | PVC ext4 montado na raiz — `subPath` resolve | commit `6a72ddb` |
| `backend`: probes `DisallowedHost` | kubelet bate pelo IP do pod, fora de `ALLOWED_HOSTS` — `httpHeaders` força um Host permitido | commit `6a72ddb` |
| `api`: `CERTIFICATE_VERIFY_FAILED` contra o OpenSearch | OpenSearch usava certs demo autoassinados da imagem; `opensearch-py` usa o bundle do `certifi`, não o trust store do SO | CA própria via cert-manager + `opensearch.yml` custom + initContainer que confia a CA no `certifi` da API — commit `eb1ffb8` |
| `api`: `AuthenticationException(401)` contra o OpenSearch | `QUERIDO_DIARIO_OPENSEARCH_USER` no `app-secret` era `querido-diario-user` (role inexistente) — só `admin` existe | fix manual no `app-secret` pra `admin` |

Também existe `scripts/check_secret_refs.py` (CI) pra pegar a classe de bug
"chave referenciada num manifesto mas nunca provida no secret" antes de
chegar em produção de novo.

**Estado atual (2026-08-29): `postgres`, `backend`, `api`, `celery-beat` saudáveis.**
`celery-worker` ainda em CrashLoopBackOff/OOMKilled (concurrency=96 prefork
estourando o limite de memória do container) — bug separado, não bloqueia a
migração, ainda não resolvido.

## Estado atual (checklist)

- [x] Causas raiz identificadas e corrigidas no repo (commits acima)
- [x] Destruição seletiva no Revoada: `api`, `backend`, `celery-beat`,
      `celery-worker`, `data-processing` (CronJob+Jobs), `opensearch`
      (StatefulSet+PVC) — **removidos**
- [x] Preservados no Revoada: `postgres` (CNPG Cluster, saudável, bancos
      vazios), `redis`, `frontend`, `apache-tika`, certificado TLS
      (`queridodiario-tls`), IngressRoutes, secrets existentes (serão
      recriados pelo CI)
- [x] OpenSearch redimensionado pra ~400G reais (450Gi de storage, 16Gi de
      memória/8Gi de heap)
- [x] `postgres`, `backend`, `api` rodando saudáveis em produção (ver tabela
      de causas acima) — validado manualmente no cluster, commits locais
      ainda não enviados
- [x] TLS próprio do OpenSearch via cert-manager, API confiando na CA
- [ ] `celery-worker` em CrashLoopBackOff/OOMKilled — resolver antes do
      cutover final (não bloqueia o restore do Postgres)
- [ ] Push dos commits pendentes — **antes de dar push**, sincronizar
      `scripts/secrets.txt` (local, gitignored) com os valores corrigidos
      manualmente no cluster (`POSTGRES_USERNAME=admin`,
      `OPENSEARCH_HOST=https://opensearch.querido-diario.svc.cluster.local:9200`)
      e rodar `python3 scripts/load_secrets.py`, senão o próximo deploy do
      CI reverte os fixes manuais
- [ ] Dump/restore do Postgres (VPS antiga → Revoada) — Fase 0 do
      `scripts/db-migration/00-setup-vps.md` precisa rodar na VPS antiga
      (WireGuard, kubectl, credenciais `OLD_PG_*`), fora do alcance daqui
- [ ] Migração do índice OpenSearch (VPS antiga → Revoada)
- [ ] Deploy da aplicação (api/backend/celery/data-processing) — **depois**
      do restore, não antes (ver ordem abaixo)
- [ ] Cutover de DNS

## Ordem dos próximos passos

A ordem importa: **o restore do Postgres precisa rodar antes do primeiro
deploy da aplicação**, porque:

- O `initContainer` de `migrate` do backend cria as tabelas Django vazias no
  primeiro boot. Se isso rodar antes do restore, `02-restore-postgres.sh`
  recusa sobrescrever (checagem de "banco não-vazio") e exigiria `--force`
  — e o `pg_restore` atual não usa `--clean`, então provavelmente reclama de
  "relation already exists" tabela por tabela (barulhento, evitável).
- O schema de `territories`/`gazettes`/`querido_diario_spiders` (banco
  `queridodiario`) já vem completo no dump da VPS antiga — **não é
  necessário** rodar `scrapy qd-sync-spiders` manualmente em produção como
  fizemos no bootstrap do ambiente dev local; isso só seria necessário se o
  Postgres de produção ficasse vazio permanentemente (não é o caso aqui).

### 1. Dump/restore do Postgres

Seguir `scripts/db-migration/README.md` (Fases 0-3), rodando os scripts **de
dentro da VPS antiga**:

```bash
./00-setup-vps.md         # preparo (uma vez): WireGuard, kubectl, env vars
./01-dump-postgres.sh     # ensaio a quente primeiro, depois final na janela de manutenção
./02-restore-postgres.sh  # restaura no Revoada — bancos devem estar vazios
./03-verify-postgres.sh   # gate: contagens origem vs destino
```

Neste ponto os bancos `queridodiario`/`backend`/`companies` no Revoada têm o
schema e os dados completos da VPS antiga (incluindo `django_migrations` já
aplicadas até a versão do backend que estava rodando lá).

### 2. Deploy da aplicação

Com o Postgres já populado, dar push nos commits pendentes (dispara
`deploy.yml`) ou `make k8s-apply-prod` manualmente. Isso recria
`api`/`backend`/`celery-beat`/`celery-worker`/`data-processing`/`opensearch`.

- O `initContainer` de `migrate` do backend só aplica migrations *novas*
  (delta entre o que já veio no dump e o código atual) — idempotente, seguro.
- O `data-processing` (CronJob, roda de hora em hora, ou dispare manualmente
  com `kubectl create job --from=cronjob/data-processing <nome> -n
  querido-diario`) cria o índice `queridodiario` no OpenSearch **com o
  mapping correto** (analyzer `brazilian`, subcampos `.exact`, `sort.field`
  etc — ver `tasks/create_index.py` no repo `querido-diario-data-processing`)
  como primeiro passo do pipeline, e começa a processar qualquer gazette
  ainda `processed=false` vinda do dump.

**Importante**: dispare o `data-processing` manualmente (ou espere a próxima
hora cheia) *antes* do passo 3 abaixo — o índice precisa existir com o
mapping certo antes do bulk-copy do OpenSearch, senão
`opensearch-migrate.py` deixa o OpenSearch criar o índice sozinho com
mapping default (sem analyzer/sort corretos).

### 3. Migração do índice OpenSearch

```bash
kubectl port-forward svc/opensearch 9200:9200 -n querido-diario &
python3 opensearch-migrate.py --dry-run   # confere contagens
python3 opensearch-migrate.py             # migração real (idempotente por _id)
```

Bulk-copia os documentos já processados (texto extraído, embeddings) do
OpenSearch da VPS antiga pro índice novo — complementa o que o
`data-processing` já processou por conta própria no passo 2.

### 4. Verificação e cutover

Seguir Fase 3 (gate `03-verify-postgres.sh` + contagem do
`opensearch-migrate.py`) e Fase 4 (smoke test manual, troca de DNS, manter
VPS antiga no ar como rollback) do `scripts/db-migration/README.md`.

## Notas soltas

- `opensearch-migrate.py` não cria o índice com o mapping customizado — ver
  nota no passo 2 acima sobre disparar o `data-processing` antes.
- `scripts/check_secret_refs.py` roda no CI a cada push/PR — se um manifesto
  novo referenciar uma chave de secret que `deploy.yml` não provê, o deploy
  falha antes de chegar no cluster.
