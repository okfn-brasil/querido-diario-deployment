# CLAUDE.md — Querido Diário Deployment

Repositório de infraestrutura da plataforma [Querido Diário](https://queridodiario.ok.org.br) (OKFN Brasil).
Deploy em **Kubernetes via Kustomize**. Consulte `make help` para todos os comandos disponíveis.

---

## Repositórios da plataforma

| Serviço | Tecnologia | Repositório GitHub |
|---|---|---|
| **Este repositório** | Kubernetes/Kustomize | [querido-diario-deployment](https://github.com/okfn-brasil/querido-diario-deployment) |
| Frontend | Angular | [querido-diario-frontend](https://github.com/okfn-brasil/querido-diario-frontend) |
| API | FastAPI | [querido-diario-api](https://github.com/okfn-brasil/querido-diario-api) |
| Backend (admin/celery) | Django | [querido-diario-backend](https://github.com/okfn-brasil/querido-diario-backend) |
| Raspadores (Scrapy spiders) | Python/Scrapy | [querido-diario](https://github.com/okfn-brasil/querido-diario) |
| Data Processing (ETL/indexação) | Python | [querido-diario-data-processing](https://github.com/okfn-brasil/querido-diario-data-processing) |

Outros componentes (Apache Tika, Redis, PostgreSQL, OpenSearch, Storage) são serviços de infraestrutura sem repositório próprio neste contexto.

Por padrão, os repositórios dos outros projetos são esperados como irmãos deste diretório:
```
../querido-diario/                  # raspadores (Scrapy)
../querido-diario-api/
../querido-diario-backend/app/
../querido-diario-data-processing/  # ETL + indexação no OpenSearch
../querido-diario-frontend/
```

---

## Arquitetura

```
Internet → Traefik (IngressRoute CRDs) → Serviços K8s
                                        ├── frontend (nginx/Angular)
                                        ├── api (FastAPI, porta 8080)
                                        └── backend (Django, porta 8080)
                                              └── celery-beat / celery-worker → Redis
PostgreSQL gerenciado pelo CloudNativePG operator
OpenSearch: container local (dev) | StatefulSet single-node no cluster k8s (prod)
Storage S3: Garage local (dev) | AWS S3 ou compatível (prod)
```

### Decisões de arquitetura (ADRs)

Todas em `adrs/`. Leia antes de propor mudanças estruturais:

| ADR | Decisão |
|---|---|
| ADR-001 | Kubernetes como plataforma de deploy (migração de Docker Compose) |
| ADR-002 | PostgreSQL via CloudNativePG operator |
| ADR-003 | ~~OpenSearch em VM externa em produção~~ — superado pelo ADR-008 |
| ADR-004 | Traefik v3 com IngressRoute CRDs (Gateway API analisado e descartado) |
| ADR-005 | Raspadores via Zyte (Scrapy Cloud) em produção; CronJob k8s como alternativa |
| ADR-006 | Garage como storage S3-compatível em desenvolvimento local |
| ADR-007 | Terminação SSL: cert-manager + Let's Encrypt (não `tls.certResolver` do Traefik) |
| ADR-008 | OpenSearch single-node dentro do cluster k8s em produção (StatefulSet, sem HA) |

---

## Estrutura de arquivos

```
k8s/
├── base/                    # Manifestos canônicos compartilhados entre overlays
│   ├── kustomization.yaml
│   ├── configmap-app.yaml   # Variáveis não-sensíveis da aplicação
│   ├── secret-app.yaml      # TEMPLATE — não versionar com valores reais
│   ├── traefik-middlewares.yaml
│   ├── postgres/            # CloudNativePG Cluster + credentials Secret (template)
│   ├── frontend/ api/ backend/ redis/ apache-tika/ celery-beat/ celery-worker/
│   └── data-processing/     # CronJob (roda de hora em hora)
├── overlays/
│   ├── dev/                 # kind local: infra embutida, limites menores, HTTP
│   │   └── infra/           # Garage, OpenSearch (só dev)
│   ├── production/          # Prod: réplicas, limites maiores, imagens fixas
│   └── production-local/    # GITIGNORED — valores reais (endpoint S3, ClusterIssuer)
├── local/
│   └── traefik-values.yaml
adrs/                        # Architecture Decision Records
docs/                        # Documentação técnica complementar
scripts/                     # Automação (Python, multiplataforma — ver Makefile)
│   ├── pycommon.py          # Helpers compartilhados (log, download, ensure_kubectl/kind/helm...)
│   ├── k8s_local_up.py      # Idempotente: kind + Traefik + CNPG + overlay dev
│   ├── k8s_local_down.py
│   └── ...
```

---

## Desenvolvimento local (kind)

### Pré-requisitos
- `docker` (com Linux containers habilitado no Docker Desktop, se Mac/Windows)
- `python3` ≥ 3.9 (usado pelos scripts de automação em `scripts/`, sem dependências externas)
- GNU Make — no Windows: `choco install make` / `scoop install make` / Git Bash / WSL
- `kubectl`, `helm` e `kind` ≥ 0.20 são instalados automaticamente pelos scripts se ausentes

Compatibilidade: todos os targets do `Makefile` chamam scripts Python (`scripts/*.py`) em vez de
bash, então funcionam do mesmo jeito em Linux, macOS e Windows. Se `python3` não estiver no PATH
do Windows, use `make PYTHON=python <target>`.

### Subir o ambiente

```bash
make k8s-local-up              # cria cluster kind + aplica overlay dev (~10min no 1º run)
make k8s-local-hosts           # adiciona *.queridodiario.local ao hosts file (sudo/Administrador)
make k8s-local-frontend-build  # builda e carrega imagem do frontend no cluster
```

### URLs locais

| URL | Serviço |
|---|---|
| http://queridodiario.local | Frontend |
| http://api.queridodiario.local | API |
| http://backend-api.queridodiario.local | Backend |
| http://localhost:3909 | Garage Web UI (`make k8s-local-garage-ui`) |

### Comandos úteis

```bash
make k8s-local-status           # status dos pods
make k8s-local-data-processing  # executa data-processing manualmente (CronJob suspenso em dev)
make k8s-local-down             # destroi o cluster kind
```

---

## Overlay de produção

### Dois níveis de overlay

```
overlays/production/          # versionado — patches sem dados sensíveis
overlays/production-local/    # GITIGNORED — valores reais (endpoint Ceph, ClusterIssuer, etc.)
```

O `production-local/` estende `production/` e deve ser criado manualmente na máquina de deploy.
Use `overlays/production-local.example/` como template (se existir).

### Deploy

```bash
make k8s-diff-prod    # ver o que será aplicado antes de aplicar
make k8s-apply-prod   # aplicar no cluster (requer kubeconfig configurado)
```

### Secrets de produção (criar manualmente, nunca versionar)

```bash
# Credenciais PostgreSQL (CloudNativePG bootstrap)
kubectl create secret generic postgres-credentials -n querido-diario \
  --from-literal=username='...' --from-literal=password='...'

# Backup PostgreSQL → S3/Ceph
kubectl create secret generic postgres-backup-secret -n querido-diario \
  --from-literal=ACCESS_KEY_ID='...' --from-literal=SECRET_ACCESS_KEY='...'

# Variáveis sensíveis da aplicação
kubectl create secret generic app-secret -n querido-diario \
  --from-literal=QD_BACKEND_SECRET_KEY='...' \
  --from-literal=QD_BACKEND_DB_URL='...' \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_HOST='...' \
  # ... ver k8s/README.md para lista completa
```

---

## Padrões de código

### Patches Kustomize (formato JSON Patch)

```yaml
patches:
  - patch: |-
      - op: replace       # use "replace" se o campo já existe na base
        path: /spec/storage/size
        value: 100Gi
      - op: add           # use "add" apenas para campos novos
        path: /spec/backup
        value: { ... }
    target:
      kind: Cluster
      name: postgres
```

### Traefik IngressRoute

- Dev: `entryPoints: [web]`, sem `tls`, domínio `*.queridodiario.local`
- Prod: `entryPoints: [websecure]`, `tls.secretName: queridodiario-tls`, nunca `tls.certResolver`
- Sempre criar par de IngressRoutes: um HTTPS (`websecure`) + um redirect HTTP→HTTPS (`web`)
- Middlewares disponíveis em `k8s/base/traefik-middlewares.yaml`

### Imagens Docker

- Dev: tag `:local` (build local via `make build-*`)
- Prod: tag de versão fixa (ex: `v1.2.3`), **nunca** `:latest`
- Registry: `ghcr.io/okfn-brasil/querido-diario-{service}`

### Namespace

Todos os recursos ficam no namespace `querido-diario`.

---

## Regras de privacidade / segurança

- `k8s/overlays/production-local/` está no `.gitignore` — nunca commitar
- IPs, hostnames e endpoints do cluster de produção nunca vão no git; usar `<PLACEHOLDER>` no overlay público
- Secrets com valores reais nunca são versionados; os arquivos em `base/` são apenas templates de estrutura
- Antes de commitar patches de produção, verificar se não há credenciais ou endereços internos no diff

---

## Builds Docker locais

```bash
make build-api                   # API → :local
make build-backend               # Backend/Celery → :local
make build-data-processing-base  # base Python (rebuildar ao mudar requirements.txt)
make build-data-processing       # Data Processing → :local
make build-tika                  # Apache Tika → :local
make build-frontend              # Frontend → :local
make build-all                   # todas as imagens acima
```

Todos usam `--cache-from` apontando para o GHCR, acelerando o build.

---

## Raspadores (scrapers)

Em produção os raspadores rodam na **Zyte (Scrapy Cloud)**. Para testes locais:

```bash
make spider-setup                                     # cria venv (uma vez)
make spider-list                                      # lista spiders disponíveis
make run-spider SPIDER=sp_campinas START=2025-01-01   # executa um spider
```

O código dos raspadores está em `../querido-diario/data_collection/`. `make run-spider` conecta automaticamente ao Postgres e ao Garage (S3) do cluster kind local (port-forward + credenciais do secret `app-secret`) — não precisa de `.local.env` pra esse caso. Crie `../querido-diario/data_collection/.local.env` só se quiser apontar pra outro ambiente (ex: Revoada); o que estiver lá tem prioridade sobre a auto-conexão.

---

## OpenSearch

OpenSearch roda como `StatefulSet` single-node dentro do próprio cluster k8s,
tanto em dev quanto em produção (ver ADR-008):
`k8s/overlays/dev/infra/opensearch.yaml` e
`k8s/overlays/production/opensearch/statefulset.yaml`. Em produção o plugin de
segurança fica habilitado, com a senha do usuário `admin` compartilhada com a
chave `QUERIDO_DIARIO_OPENSEARCH_PASSWORD` do secret `app-secret`; em dev o
plugin fica desabilitado para simplificar o dia a dia local.
