# Referência de Variáveis de Ambiente

Em Kubernetes, a configuração é distribuída entre dois objetos:

- **`ConfigMap` (`configmap-app.yaml`)** — variáveis não-sensíveis, versionadas no repositório
- **`Secret` (`app-secret`)** — credenciais e chaves, criadas manualmente no cluster (nunca versionadas com valores reais)

O template do secret está em `k8s/base/secret-app.yaml`. Credenciais do PostgreSQL ficam no secret separado `postgres-credentials` (`k8s/base/postgres/credentials-secret.yaml`).

---

## Domínios

| Variável | Descrição | Exemplo |
|---|---|---|
| `DOMAIN` | Domínio principal | `queridodiario.ok.org.br` |

Subdomínios derivados: `api.${DOMAIN}`, `backend-api.${DOMAIN}`.

---

## PostgreSQL

Gerenciado pelo CloudNativePG. As strings de conexão são compostas a partir das credenciais do secret `postgres-credentials` + nomes de banco definidos no ConfigMap.

| Variável | Descrição |
|---|---|
| `QD_DATA_DB_HOST` | Host do PostgreSQL (service do CNPG) |
| `QD_DATA_DB_USER` | Usuário do banco principal (`queridodiario`) |
| `QD_DATA_DB_PASSWORD` | Senha (via secret) |
| `QD_BACKEND_DB_HOST` | Host para o backend Django |
| `QD_BACKEND_DB_USER` | Usuário do banco backend |
| `QD_BACKEND_DB_PASSWORD` | Senha (via secret) |
| `QD_BACKEND_DB_URL` | URL completa de conexão Django (composta no manifest) |
| `POSTGRES_COMPANIES_HOST` | Host do banco de empresas |
| `POSTGRES_COMPANIES_USER` | Usuário |
| `POSTGRES_COMPANIES_PASSWORD` | Senha (via secret) |
| `POSTGRES_COMPANIES_DB` | Nome do banco |

---

## OpenSearch

| Variável | Descrição | Dev | Prod |
|---|---|---|---|
| `QUERIDO_DIARIO_OPENSEARCH_HOST` | URL do OpenSearch | `http://opensearch:9200` | `https://[externo]:9200` |
| `QUERIDO_DIARIO_OPENSEARCH_USER` | Usuário | `admin` | configurar |
| `QUERIDO_DIARIO_OPENSEARCH_PASSWORD` | Senha (via secret) | `admin` | configurar |
| `OPENSEARCH_INDEX` | Nome do índice | `querido-diario` | `querido-diario` |

---

## Storage (S3-compatível)

| Variável | Descrição | Dev | Prod |
|---|---|---|---|
| `STORAGE_ENDPOINT` | Endpoint S3 | `http://garage:3900` | URL do bucket AWS |
| `STORAGE_ACCESS_KEY` | Access key (via secret) | chave do Garage | AWS access key |
| `STORAGE_ACCESS_SECRET` | Secret key (via secret) | secret do Garage | AWS secret key |
| `STORAGE_BUCKET` | Nome do bucket | `queridodiariobucket` | configurar |
| `STORAGE_REGION` | Região | `garage` | `us-east-1` |

### Acesso público aos arquivos (CDN)

| Variável | Serviço | Descrição |
|---|---|---|
| `QUERIDO_DIARIO_FILES_ENDPOINT` | API | URL pública base dos arquivos (CloudFront ou endpoint direto) |
| `REPLACE_FILE_URL_BASE` | API | `true` para substituir URLs antigas por novo endpoint |
| `USE_RELATIVE_FILE_PATHS` | Data Processing | `true` para armazenar paths relativos (recomendado) |

Ver `docs/storage-migration-cloudfront.md` para cenários de migração.

---

## Redis / Celery

| Variável | Descrição | Valor típico |
|---|---|---|
| `CELERY_BROKER_URL` | URL do broker | `redis://redis:6379` |
| `CELERY_RESULT_BACKEND` | Backend de resultados | `redis://redis:6379` |

---

## Backend Django

| Variável | Descrição | Dev | Prod |
|---|---|---|---|
| `QD_BACKEND_SECRET_KEY` | Django secret key (via secret) | inseguro | gerar aleatório |
| `QD_BACKEND_DEBUG` | Modo debug | `True` | `False` |
| `QD_BACKEND_ALLOWED_HOSTS` | Hosts permitidos | `*` | domínios reais |
| `QD_BACKEND_ALLOWED_ORIGINS` | Origens CORS | `*` | domínios reais |
| `QD_BACKEND_CSRF_TRUSTED_ORIGINS` | Origens CSRF | — | `https://backend-api.${DOMAIN}` |

---

## API (FastAPI)

| Variável | Descrição |
|---|---|
| `QUERIDO_DIARIO_CORS_ALLOW_ORIGINS` | Origens CORS permitidas |
| `QUERIDO_DIARIO_DEBUG` | Modo debug |

---

## Email (Mailjet)

| Variável | Descrição |
|---|---|
| `MAILJET_API_KEY` | API key (via secret) |
| `MAILJET_SECRET_KEY` | Secret key (via secret) |
| `DEFAULT_FROM_EMAIL` | Email remetente padrão |
| `QUERIDO_DIARIO_SUGGESTION_RECIPIENT_EMAIL` | Destinatário de sugestões |

---

## Apache Tika

| Variável | Valor típico |
|---|---|
| `APACHE_TIKA_SERVER` | `http://apache-tika:9998` |

---

## Checklist de produção

### Antes do primeiro deploy

- [ ] Criar secret `app-secret` com todas as credenciais (`kubectl create secret generic ...`)
- [ ] Criar secret `postgres-credentials` para o CloudNativePG
- [ ] Editar `k8s/base/configmap-app.yaml` com domínio e URLs corretos
- [ ] Fixar tags de imagem em `k8s/overlays/production/kustomization.yaml`
- [ ] Configurar DNS (ver `docs/cloudflare-ssl-limitations.md`)
- [ ] Verificar StorageClass disponível no cluster (SSD recomendado para PostgreSQL)
- [ ] Planejar backup do PostgreSQL (WAL archiving via CloudNativePG)

### Deploy

```bash
make k8s-diff-prod    # revisar o que será aplicado
make k8s-apply-prod   # aplicar
```
