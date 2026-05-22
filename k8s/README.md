# Querido Diário — Kubernetes

Manifestos Kubernetes para a plataforma Querido Diário, gerenciados via [Kustomize](https://kustomize.io/) (embutido no `kubectl`).

## Estrutura

```
k8s/
├── base/                        # Recursos compartilhados entre overlays
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── configmap-app.yaml       # Variáveis não-sensíveis
│   ├── secret-app.yaml          # TEMPLATE — não versionar com valores reais
│   ├── traefik-middlewares.yaml # Middlewares Traefik (CORS, rate-limit, headers...)
│   ├── postgres/
│   │   ├── cluster.yaml         # CloudNativePG Cluster (PostgreSQL 15)
│   │   └── credentials-secret.yaml  # TEMPLATE — não versionar
│   ├── frontend/                # nginx servindo o app Angular
│   ├── api/
│   ├── backend/
│   ├── redis/
│   ├── apache-tika/
│   ├── celery-beat/
│   ├── celery-worker/
│   └── data-processing/
├── overlays/
│   ├── production/              # 2+ réplicas, 100Gi postgres, imagens fixas
│   └── dev/                     # kind local: infra embutida, limites menores
│       └── infra/
│           ├── postgres-credentials-dev.yaml
│           ├── opensearch.yaml
│           ├── garage.yaml      # Storage S3-compatível (Garage v2)
│           ├── garage-webui.yaml
│           └── init-jobs.yaml
└── local/
    ├── setup.sh                 # Script idempotente: kind + Traefik + CNPG + overlay dev
    ├── teardown.sh
    ├── kind-config.yaml
    └── traefik-values.yaml
```

## O que roda no cluster

| Serviço | Dev | Prod |
|---|---|---|
| Frontend (nginx/Angular) | ✓ | ✓ |
| API (FastAPI) | ✓ | ✓ |
| Backend (Django) | ✓ | ✓ |
| Celery Beat + Worker | ✓ | ✓ |
| Apache Tika | ✓ | ✓ |
| Redis | ✓ | ✓ |
| PostgreSQL (CloudNativePG) | ✓ (1 instância) | ✓ (3 instâncias) |
| OpenSearch | ✓ | externo |
| Garage (S3) | ✓ | externo (AWS S3) |

---

## Desenvolvimento local (kind)

### Pré-requisitos

- `docker`
- `kubectl` ≥ 1.24
- `helm` (instalado automaticamente pelo setup.sh se ausente)
- `kind` ≥ 0.20 (instalado automaticamente se ausente)

### Subir o ambiente

```bash
make k8s-local-up
```

O script `k8s/local/setup.sh` é **idempotente** — pode ser executado múltiplas vezes. Ele:

1. Verifica/instala `kind` e `helm`
2. Cria o cluster kind `querido-diario-dev` (k8s 1.31)
3. Instala Traefik via Helm (DaemonSet + hostPort 80)
4. Pré-carrega imagens no nó kind (evita timeout)
5. Instala o CloudNativePG operator
6. Aplica `k8s/overlays/dev`
7. Aguarda todos os serviços ficarem prontos

### Configurar /etc/hosts

```bash
make k8s-local-hosts   # requer sudo
```

Ou manualmente:
```
127.0.0.1  queridodiario.local
127.0.0.1  api.queridodiario.local
127.0.0.1  backend-api.queridodiario.local
```

### Buildar o frontend

A imagem do frontend não é baixada do registry — é construída localmente a partir do código:

```bash
make k8s-local-frontend-build   # docker build + kind load (~5min no primeiro run)
kubectl rollout restart deployment/frontend -n querido-diario
```

Por padrão busca o código em `../querido-diario-frontend`. Para outro caminho:
```bash
make k8s-local-frontend-build FRONTEND_DIR=/outro/caminho
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
make k8s-local-status            # status dos pods
make k8s-local-garage-ui         # port-forward para o Garage Web UI
make k8s-local-data-processing   # executa data-processing manualmente
make k8s-local-down              # destroi o cluster
```

---

## Deploy de produção

### Pré-requisitos no cluster

1. **Traefik v3** instalado via Helm com suporte a CRDs (`IngressRoute`, `Middleware`):
   ```bash
   helm repo add traefik https://traefik.github.io/charts
   helm upgrade --install traefik traefik/traefik \
     -n traefik --create-namespace \
     --set providers.kubernetesCRD.enabled=true \
     --set providers.kubernetesCRD.allowCrossNamespace=true
   ```

2. **CloudNativePG operator** instalado:
   ```bash
   kubectl apply --server-side \
     -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.24/releases/cnpg-1.24.0.yaml
   ```

### 1. Criar os Secrets

Os secrets nunca devem ser versionados com valores reais.

**Secret da aplicação:**
```bash
kubectl create secret generic app-secret \
  -n querido-diario \
  --from-literal=QD_BACKEND_SECRET_KEY='...' \
  --from-literal=QD_BACKEND_DB_URL='postgres://user:pass@postgres/backend' \
  --from-literal=QD_DATA_DB_USER='...' \
  --from-literal=QD_DATA_DB_PASSWORD='...' \
  --from-literal=QD_BACKEND_DB_USER='...' \
  --from-literal=QD_BACKEND_DB_PASSWORD='...' \
  --from-literal=POSTGRES_COMPANIES_USER='...' \
  --from-literal=POSTGRES_COMPANIES_PASSWORD='...' \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_HOST='https://...' \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_USER='...' \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_PASSWORD='...' \
  --from-literal=STORAGE_ACCESS_KEY='...' \
  --from-literal=STORAGE_ACCESS_SECRET='...' \
  --from-literal=STORAGE_BUCKET='...' \
  --from-literal=MAILJET_API_KEY='...' \
  --from-literal=MAILJET_SECRET_KEY='...' \
  --from-literal=QUERIDO_DIARIO_SUGGESTION_RECIPIENT_EMAIL='...'
```

**Secret de credenciais do PostgreSQL (usado pelo CloudNativePG no initdb):**
```bash
kubectl create secret generic postgres-credentials \
  -n querido-diario \
  --from-literal=username='...' \
  --from-literal=password='...'
```

Alternativas mais seguras: [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) ou [External Secrets Operator](https://external-secrets.io/).

### 2. Ajustar configurações

Edite `k8s/base/configmap-app.yaml` com os valores do ambiente de produção (domínio, URLs, etc.).

Edite `k8s/overlays/production/kustomization.yaml` para fixar as tags de imagem:
```yaml
images:
  - name: ghcr.io/okfn-brasil/querido-diario-api
    newTag: "v1.2.3"   # substitua pelo release desejado
```

### 3. Ver diff antes de aplicar

```bash
make k8s-diff-prod
```

### 4. Aplicar

```bash
make k8s-apply-prod
```

---

## Referência rápida

```bash
# Gerar YAML sem aplicar (dry-run)
make k8s-build-dev
make k8s-build-prod

# Ver diff entre cluster e manifests
make k8s-diff-dev
make k8s-diff-prod

# Aplicar
make k8s-apply-dev
make k8s-apply-prod
```

## data-processing (CronJob)

Roda automaticamente a cada hora (`0 * * * *`). Em dev o CronJob está suspenso.

Para executar manualmente:
```bash
make k8s-local-data-processing   # dev (kind)

# ou em qualquer cluster:
kubectl create job --from=cronjob/data-processing data-processing-manual-$(date +%s) \
  -n querido-diario
kubectl logs -n querido-diario -l job-name=data-processing-manual -f
```

## Notas

**static files (backend):** O PVC `static-files` usa `ReadWriteOnce` (1 réplica). Para escalar o backend, migre para `ReadWriteMany` (NFS/EFS) ou sirva os estáticos via S3/CDN.

**PostgreSQL:** Gerenciado pelo [CloudNativePG](https://cloudnative-pg.io/). Em prod roda com 3 instâncias (primary + 2 replicas). Os bancos `queridodiario`, `backend` e `companies` são criados automaticamente no primeiro boot via `postInitSQL`.

**OpenSearch e Storage:** Em produção são serviços externos (não provisionados neste repositório). Em dev, o overlay inclui OpenSearch e Garage (S3-compatível) como Deployments locais.
