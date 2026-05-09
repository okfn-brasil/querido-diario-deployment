# Querido Diário — Kubernetes

Manifestos Kubernetes para produção usando Kustomize.

## Pré-requisitos

- `kubectl` ≥ 1.24 (kustomize embutido)
- Traefik v3 instalado no cluster via Helm:
  ```bash
  helm repo add traefik https://traefik.github.io/charts
  helm install traefik traefik/traefik -n traefik --create-namespace
  ```
- Bancos de dados e OpenSearch provisionados externamente (não rodam no cluster)
- Namespace `querido-diario` criado ou será criado pelos manifestos

## Estrutura

```
k8s/
├── base/                    # Recursos base (namespace, configmap, secret template, serviços)
│   ├── kustomization.yaml
│   ├── configmap-app.yaml   # Variáveis não-sensíveis
│   ├── secret-app.yaml      # TEMPLATE — preencha e NÃO versione
│   ├── traefik-middlewares.yaml
│   ├── redis/
│   ├── apache-tika/
│   ├── api/
│   ├── backend/
│   ├── celery-beat/
│   ├── celery-worker/
│   └── data-processing/
└── overlays/
    ├── production/          # Réplicas e imagens de produção
    └── dev/                 # Limites menores, domínio local, CronJob suspenso
```

## Deploy de produção

### 1. Criar o Secret com valores reais

Nunca versione o arquivo com credenciais reais. Crie o secret diretamente:

```bash
kubectl create secret generic app-secret \
  --namespace querido-diario \
  --from-literal=QD_BACKEND_SECRET_KEY='...' \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_HOST='...' \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_USER='...' \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_PASSWORD='...' \
  --from-literal=QD_DATA_DB_HOST='...' \
  --from-literal=QD_DATA_DB_USER='...' \
  --from-literal=QD_DATA_DB_PASSWORD='...' \
  --from-literal=QD_BACKEND_DB_HOST='...' \
  --from-literal=QD_BACKEND_DB_USER='...' \
  --from-literal=QD_BACKEND_DB_PASSWORD='...' \
  --from-literal=QD_BACKEND_DB_URL='postgres://user:pass@host:5432/queridodiariobackend' \
  --from-literal=POSTGRES_COMPANIES_HOST='...' \
  --from-literal=POSTGRES_COMPANIES_USER='...' \
  --from-literal=POSTGRES_COMPANIES_PASSWORD='...' \
  --from-literal=STORAGE_ACCESS_KEY='...' \
  --from-literal=STORAGE_ACCESS_SECRET='...' \
  --from-literal=STORAGE_BUCKET='...' \
  --from-literal=MAILJET_API_KEY='...' \
  --from-literal=MAILJET_SECRET_KEY='...' \
  --from-literal=QUERIDO_DIARIO_SUGGESTION_RECIPIENT_EMAIL='...'
```

Alternativas mais seguras: [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) ou [External Secrets Operator](https://external-secrets.io/).

### 2. Configurar imagens de produção

Edite `k8s/overlays/production/kustomization.yaml` e substitua `latest` pelas tags de release:

```yaml
images:
  - name: ghcr.io/okfn-brasil/querido-diario-api
    newTag: "v1.2.3"
```

### 3. Ajustar domínio e configurações

Edite `k8s/base/configmap-app.yaml` com os valores corretos para o seu ambiente (domínio, hosts de DB, URLs de frontend, etc.).

### 4. Ver diff antes de aplicar

```bash
make k8s-diff-prod
# ou
kubectl diff -k k8s/overlays/production
```

### 5. Aplicar

```bash
make k8s-apply-prod
# ou
kubectl apply -k k8s/overlays/production
```

## data-processing (CronJob)

O serviço roda a cada hora por padrão (`0 * * * *`). Para executar manualmente:

```bash
kubectl create job --from=cronjob/data-processing data-processing-manual \
  -n querido-diario
```

Para acompanhar os logs:

```bash
kubectl logs -n querido-diario -l job-name=data-processing-manual -f
```

## Notas sobre static files (backend)

O PVC `static-files` usa `ReadWriteOnce` (1 réplica de backend). Se escalar o backend para múltiplas réplicas, migre para:
- `ReadWriteMany` com NFS/EFS, ou
- sirva os arquivos estáticos via S3/CDN e aponte `STATIC_URL` diretamente.

## Arquivos fora de escopo (não provisionados aqui)

- PostgreSQL (3 bancos: API, backend, receita)
- OpenSearch
- Instalação do Traefik (Helm chart externo)
- CI/CD e GitOps (ArgoCD, Flux)
