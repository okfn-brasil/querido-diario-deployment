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
│           ├── opensearch.yaml  # StatefulSet single-node (índice criado pelo data-processing)
│           ├── garage.yaml      # Storage S3-compatível (Garage v2)
│           └── garage-webui.yaml
└── local/
    ├── kind-config.yaml
    └── traefik-values.yaml
```

Os scripts que orquestram o cluster local (`k8s_local_up.py`, `k8s_local_down.py`, `k8s_local_hosts.py`,
`k8s_local_data_processing.py`) ficam em `scripts/` na raiz do repositório — são invocados pelo
`Makefile` e rodam em Linux, macOS e Windows (Python puro, sem dependências externas).

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
| OpenSearch | ✓ | ✓ (single-node, sem HA) |
| Garage (S3) | ✓ | externo (AWS S3) |

---

## Desenvolvimento local (kind)

### Pré-requisitos

- `docker`
- `kubectl` ≥ 1.24
- `python3` ≥ 3.9
- `kubectl`, `helm` e `kind` são instalados automaticamente pelos scripts Python se ausentes

### Subir o ambiente

```bash
make k8s-local-up
```

O script `scripts/k8s_local_up.py` (chamado por `make k8s-local-up`) é **idempotente** — pode ser executado múltiplas vezes. Ele:

1. Verifica/instala `kind` e `helm`
2. Cria o cluster kind `querido-diario-dev` (k8s 1.31)
3. Instala Traefik via Helm (DaemonSet + hostPort 80)
4. Pré-carrega imagens no nó kind (evita timeout)
5. Instala o CloudNativePG operator
6. Aplica `k8s/overlays/dev`
7. Aguarda todos os serviços ficarem prontos

### Configurar /etc/hosts

```bash
make k8s-local-hosts   # Linux/Mac: pede sudo; Windows: rode o terminal como Administrador
```

Ou manualmente:
```
127.0.0.1  queridodiario.local
127.0.0.1  api.queridodiario.local
127.0.0.1  backend-api.queridodiario.local
```

### Buildar o frontend

A imagem do frontend não é baixada do registry — é construída localmente a partir do código.

**Opção 1 — build com cache remoto (recomendado):**
```bash
make build-frontend              # buildx + cache do GHCR → :local no daemon Docker
kind load docker-image ghcr.io/okfn-brasil/querido-diario-frontend:local \
    --name querido-diario-dev    # carrega no cluster kind
kubectl rollout restart deployment/frontend -n querido-diario
```

**Opção 2 — build simples + kind load em um passo:**
```bash
make k8s-local-frontend-build   # docker build + kind load (~5min no primeiro run)
kubectl rollout restart deployment/frontend -n querido-diario
```

Por padrão busca o código em `../querido-diario-frontend`. Para outro caminho:
```bash
make build-frontend FRONTEND_DIR=/outro/caminho
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

### Troubleshooting

**`ctr: content digest sha256:... not found` ao carregar imagens no kind (Mac/Windows)**

Bug conhecido do `kind` com o Docker Desktop quando a opção **"Use containerd for
pulling and storing images"** está habilitada (Settings > General). Com ela ativa,
um `docker pull` sem `--platform` explícito guarda a manifest-list completa
(referências a *todas* as plataformas de uma imagem multi-arch), mas só baixa os
blobs da plataforma local. O `kind load docker-image` usa
`ctr images import --all-platforms` e falha tentando importar blobs que nunca
foram baixados.

`scripts/k8s_local_up.py` já tenta se recuperar sozinho (descarta a imagem em
cache local e repuxa fixando `--platform`) e não trava o `make k8s-local-up` por
causa disso — os pods conseguem puxar a imagem diretamente da internet como
fallback, só um pouco mais lento. Se o aviso persistir, desabilite a opção acima
em Docker Desktop e reinicie o Docker.

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

**OpenSearch:** Em produção roda como `StatefulSet` single-node dentro do cluster k8s, em `k8s/overlays/production/opensearch/` (ver ADR-008). Em dev, o overlay inclui OpenSearch como `Deployment` local (plugin de segurança desabilitado).

**Storage:** Em produção é um serviço externo (AWS S3, não provisionado neste repositório). Em dev, o overlay inclui Garage (S3-compatível) como `Deployment` local.
