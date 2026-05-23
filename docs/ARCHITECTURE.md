# Arquitetura do Querido Diário — Deployment

## Visão Geral

A plataforma Querido Diário roda em Kubernetes (via Kustomize), com Traefik como ingress controller e CloudNativePG para PostgreSQL. Storage de arquivos e OpenSearch são provisionados externamente em produção; em desenvolvimento local (kind), rodam como Deployments simples dentro do próprio cluster.

## Diagrama de componentes

```
                        Internet
                           │
                    [Cloudflare DNS]
                           │
                      [Traefik v3]          ← instalado via Helm
                     /     │     \
                    /      │      \
               [API]  [Backend]  [Frontend]
             FastAPI   Django      nginx
                │    /   │   \
                │   /    │    \
           [PostgreSQL] [Redis] [OpenSearch]
           CloudNativePG        (externo em prod)
                │
           [Storage S3]         ← Garage (dev) / AWS S3 (prod)
                │
         [Data Processing]      ← CronJob k8s (agendado no cluster)
         [Apache Tika]

         [Raspadores (Scrapy)]  ← rodam na Zyte, escrevem no Storage S3
```

## Serviços no cluster

| Serviço | Imagem | Dev | Prod |
|---|---|---|---|
| Frontend (nginx/Angular) | `ghcr.io/okfn-brasil/querido-diario-frontend` | ✓ | ✓ |
| API (FastAPI) | `ghcr.io/okfn-brasil/querido-diario-api` | ✓ | ✓ |
| Backend (Django) | `ghcr.io/okfn-brasil/querido-diario-backend` | ✓ | ✓ |
| Celery Beat + Worker | `ghcr.io/okfn-brasil/querido-diario-backend` | ✓ | ✓ |
| Apache Tika | `ghcr.io/okfn-brasil/querido-diario-data-processing/apache-tika` | ✓ | ✓ |
| Redis | `redis:7` | ✓ | ✓ |
| PostgreSQL (CloudNativePG) | gerenciado pelo operator | 1 instância | 3 instâncias |
| OpenSearch | `opensearchproject/opensearch` | ✓ (Deployment) | externo |
| Garage (S3-compatível) | `dxflrs/garage` | ✓ (Deployment) | externo (AWS S3) |
| Data Processing | `ghcr.io/okfn-brasil/querido-diario-data-processing` | CronJob suspenso | CronJob k8s ativo |
| Raspadores (Scrapy) | — (Zyte gerencia) | `make run-spider` (local) | Zyte (Scrapy Cloud) |

## Estrutura Kustomize

```
k8s/
├── base/               # recursos compartilhados entre overlays
│   ├── api/
│   ├── backend/
│   ├── celery-beat/
│   ├── celery-worker/
│   ├── frontend/
│   ├── apache-tika/
│   ├── redis/
│   ├── data-processing/
│   ├── postgres/       # CloudNativePG Cluster
│   ├── configmap-app.yaml
│   ├── secret-app.yaml     # TEMPLATE — não versionar com valores reais
│   └── traefik-middlewares.yaml
├── overlays/
│   ├── production/     # 2+ réplicas, 100Gi postgres, imagens fixadas
│   └── dev/            # kind: infra embutida (OpenSearch, Garage), limites menores
│       └── infra/
│           ├── opensearch.yaml
│           ├── garage.yaml
│           ├── garage-webui.yaml
│           └── init-jobs.yaml
└── local/              # scripts para cluster kind local
    ├── setup.sh        # idempotente: kind + Traefik + CNPG operator + overlay dev
    └── teardown.sh
```

## Fluxo de configuração

### Desenvolvimento local (kind)

```bash
make k8s-local-up       # cria cluster + aplica overlay dev (~10min no 1o run)
make k8s-local-hosts    # adiciona entradas ao /etc/hosts (requer sudo)
```

Configuração não-sensível em `k8s/base/configmap-app.yaml`. Credenciais aplicadas pelo overlay dev via arquivos de template em `k8s/overlays/dev/`.

### Produção

```bash
# Criar secrets (uma vez)
kubectl create secret generic app-secret -n querido-diario --from-literal=...
kubectl create secret generic postgres-credentials -n querido-diario --from-literal=...

# Deploy
make k8s-diff-prod      # revisar antes
make k8s-apply-prod
```

Ver `k8s/README.md` para o guia completo de produção.

## Roteamento e SSL

Traefik v3 instalado via Helm com DaemonSet + hostPort 80/443. Roteamento via `IngressRoute` CRDs. SSL via Let's Encrypt (ACME HTTP-01).

Cloudflare atua apenas no domínio principal (`queridodiario.ok.org.br`) como proxy. Subdomínios (`api.*`, `backend-api.*`) devem ser DNS-only para permitir que o Traefik emita certificados. Ver `docs/cloudflare-ssl-limitations.md`.

## Raspadores e Data Processing

São dois componentes distintos:

**Raspadores (`querido-diario`)** — coletam PDFs dos diários oficiais e salvam no Storage S3. Rodam na **Zyte (Scrapy Cloud)**, agendados via GitHub Actions. Para testes locais: `make run-spider`.

**Data Processing (`querido-diario-data-processing`)** — processa os PDFs do S3 via Apache Tika, extrai texto e indexa no OpenSearch. Roda como **CronJob no cluster k8s** (ativo em produção, suspenso em dev).

```bash
# Executar data-processing manualmente no cluster local (dev)
make k8s-local-data-processing

# Executar raspador localmente (testes)
make run-spider SPIDER=<nome> START=2025-01-01
```
