# Guia de Referência - Variáveis de Ambiente

> 📅 **Última atualização**: Setembro 2025 (Pós-refatoração)

## Visão Geral

Este documento serve como referência completa para todas as variáveis de ambiente utilizadas na plataforma Querido Diário. Após a refatoração, o processo foi drasticamente simplificado.

## Como Usar Este Guia

- **Desenvolvimento**: Use `make dev` (gera .env automaticamente)
- **Produção**: Use `make setup-env-prod` para gerar `.env` e configure conforme este guia
- **Template de Referência**: Todas as variáveis estão definidas em `templates/env.prod.sample`

## 🌐 Configuração de Domínios

### Domínios Base

| Variável | Descrição | Exemplo Desenvolvimento | Exemplo Produção |
|----------|-----------|------------------------|------------------|
| `DOMAIN` | Domínio principal do frontend | `queridodiario.local` | `queridodiario.ok.org.br` |

**Subdomínios compostos automaticamente:**

- **API**: `api.${DOMAIN}` (ex: `api.queridodiario.local`)
- **Backend/Admin**: `backend-api.${DOMAIN}` (ex: `backend-api.queridodiario.local`)

### SSL/TLS

| Variável | Descrição | Valor |
|----------|-----------|-------|
| `CERT_RESOLVER` | Resolver de certificados do Traefik | `leresolver` |

## 🐳 Configuração Docker

### Tags de Imagem

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `API_IMAGE_TAG` | Tag da imagem da API | `latest` |
| `BACKEND_IMAGE_TAG` | Tag da imagem do Backend | `latest` |
| `DATA_PROCESSING_IMAGE_TAG` | Tag da imagem do Data Processing | `latest` |
| `APACHE_TIKA_IMAGE_TAG` | Tag da imagem do Apache Tika | `latest` |

## 💾 Configuração de Banco de Dados

### PostgreSQL Principal

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `POSTGRES_DB` | Nome do banco principal | `queridodiariodb` | `queridodiariodb` |
| `POSTGRES_USER` | Usuário do banco principal | `queridodiario` | `[configurar]` |
| `POSTGRES_PASSWORD` | Senha do banco principal | `queridodiario` | `[configurar]` |
| `POSTGRES_HOST` | Host do banco principal | `postgres` | `[host externo]` |
| `POSTGRES_PORT` | Porta do banco principal | `5432` | `5432` |

### Backend Database URL

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `QD_BACKEND_DB_URL` | String completa de conexão (gerada automaticamente no docker-compose a partir das variáveis POSTGRES_*) | `postgres://user:pass@host:5432/db` |

**Nota:** A `QD_BACKEND_DB_URL` é construída automaticamente no docker-compose usando interpolação das variáveis `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` e `POSTGRES_PASSWORD`. Não é necessário defini-la manualmente nos arquivos `.env`.

### Banco de Empresas (API)

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `POSTGRES_COMPANIES_HOST` | Host do banco de empresas | `postgres` | `[host externo]` |
| `POSTGRES_COMPANIES_DB` | Nome do banco de empresas | `companiesdb` | `[configurar]` |
| `POSTGRES_COMPANIES_USER` | Usuário do banco de empresas | `companies` | `[configurar]` |
| `POSTGRES_COMPANIES_PASSWORD` | Senha do banco de empresas | `companies` | `[configurar]` |

### Banco de Agregados (API)

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `POSTGRES_AGGREGATES_HOST` | Host do banco de agregados | `postgres` | `[host externo]` |
| `POSTGRES_AGGREGATES_DB` | Nome do banco de agregados | `queridodiariodb` | `[configurar]` |
| `POSTGRES_AGGREGATES_USER` | Usuário do banco de agregados | `queridodiario` | `[configurar]` |
| `POSTGRES_AGGREGATES_PASSWORD` | Senha do banco de agregados | `queridodiario` | `[configurar]` |

## 🔍 Configuração OpenSearch

### API OpenSearch

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `QUERIDO_DIARIO_OPENSEARCH_HOST` | Host do OpenSearch (gerada automaticamente no docker-compose a partir de OPENSEARCH_HOST) | `opensearch:9200` | `[host externo:9200]` |
| `QUERIDO_DIARIO_OPENSEARCH_USER` | Usuário do OpenSearch (gerada automaticamente no docker-compose a partir de OPENSEARCH_USER) | `admin` | `[configurar]` |
| `QUERIDO_DIARIO_OPENSEARCH_PASSWORD` | Senha do OpenSearch (gerada automaticamente no docker-compose a partir de OPENSEARCH_PASSWORD) | `admin` | `[configurar]` |

**Nota:** As variáveis `QUERIDO_DIARIO_OPENSEARCH_*` são construídas automaticamente no docker-compose usando interpolação das variáveis `OPENSEARCH_*`. A variável `GAZETTE_OPENSEARCH_INDEX` também é composta automaticamente usando o valor de `OPENSEARCH_INDEX`. Não é necessário defini-las manualmente nos arquivos `.env`.

### Data Processing OpenSearch

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `OPENSEARCH_HOST` | URL completa do OpenSearch | `http://opensearch:9200` | `https://[host externo]:9200` |
| `OPENSEARCH_INDEX` | Nome do índice | `querido-diario` | `querido-diario` |
| `OPENSEARCH_USER` | Usuário | `admin` | `[configurar]` |
| `OPENSEARCH_PASSWORD` | Senha | `admin` | `[configurar]` |

## 📁 Configuração de Storage

### Configuração S3/MinIO

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `STORAGE_REGION` | Região do storage | `us-east-1` | `[configurar]` |
| `STORAGE_ENDPOINT` | Endpoint do storage | `http://minio:9000` | `https://[storage externo]` |
| `STORAGE_ACCESS_KEY` | Chave de acesso | `minio-access-key` | `[configurar]` |
| `STORAGE_ACCESS_SECRET` | Chave secreta | `minio-secret-key` | `[configurar]` |
| `STORAGE_BUCKET` | Nome do bucket | `queridodiariobucket` | `[configurar]` |

### Endpoints de Arquivos

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `QUERIDO_DIARIO_FILES_ENDPOINT` | URL pública dos arquivos (gerada automaticamente no docker-compose a partir de STORAGE_ENDPOINT + STORAGE_BUCKET) | `https://storage.example.com/bucket/` |

**Nota:** A `QUERIDO_DIARIO_FILES_ENDPOINT` é construída automaticamente no docker-compose usando interpolação: `${STORAGE_ENDPOINT}/${STORAGE_BUCKET}/`. Não é necessário defini-la manualmente nos arquivos `.env`.

## 📨 Configuração Redis/Celery

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `CELERY_BROKER_URL` | URL do broker Redis | `redis://redis:6378` | `redis://redis:6378` |
| `CELERY_RESULT_BACKEND` | Backend de resultados | `redis://redis:6378` | `redis://redis:6378` |

## 🔐 Configuração de Segurança

### Django Backend

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `QD_BACKEND_SECRET_KEY` | Chave secreta do Django | `[padrão inseguro]` | `[gerar chave segura]` |
| `QD_BACKEND_DEBUG` | Modo debug | `True` | `False` |

### Debug Global

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `DEBUG` | Debug geral | `1` | `0` |
| `DATA_PROCESSING_DEBUG` | Debug do processamento | `1` | `0` |
| `QUERIDO_DIARIO_DEBUG` | Debug da API | `True` | `False` |

## 🌐 Configuração CORS

### Backend CORS

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `QD_BACKEND_ALLOWED_HOSTS` | Hosts permitidos | `localhost,backend.local` | `admin.domain.com,domain.com` |
| `QD_BACKEND_ALLOWED_ORIGINS` | Origens CORS | `http://localhost:4200` | `https://domain.com` |
| `QD_BACKEND_CSRF_TRUSTED_ORIGINS` | Origens CSRF | `http://localhost:8000` | `https://admin.domain.com` |

### API CORS

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `QUERIDO_DIARIO_CORS_ALLOW_ORIGINS` | Origens permitidas | `*` | `https://domain.com` |
| `QUERIDO_DIARIO_CORS_ALLOW_CREDENTIALS` | Permitir credenciais | `True` | `True` |
| `QUERIDO_DIARIO_CORS_ALLOW_METHODS` | Métodos permitidos | `*` | `*` |
| `QUERIDO_DIARIO_CORS_ALLOW_HEADERS` | Headers permitidos | `*` | `*` |

## 📧 Configuração de Email

### Backend Email (Mailjet)

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `MAILJET_API_KEY` | Chave API do Mailjet | `[sua-chave-mailjet]` |
| `MAILJET_SECRET_KEY` | Chave secreta do Mailjet | `[sua-chave-secreta]` |
| `DEFAULT_FROM_EMAIL` | Email padrão de envio | `noreply@domain.com` |
| `SERVER_EMAIL` | Email do servidor | `server@domain.com` |
| `QUOTATION_TO_EMAIL` | Email para cotações | `quotes@domain.com` |

### API Suggestions Email

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `QUERIDO_DIARIO_SUGGESTION_SENDER_NAME` | Nome do remetente | `Querido Diário` |
| `QUERIDO_DIARIO_SUGGESTION_RECIPIENT_EMAIL` | Email destinatário | `team@domain.com` |

**Nota:** As variáveis `QUERIDO_DIARIO_SUGGESTION_MAILJET_REST_API_KEY`, `QUERIDO_DIARIO_SUGGESTION_MAILJET_REST_API_SECRET` e `QUERIDO_DIARIO_SUGGESTION_SENDER_EMAIL` são compostas automaticamente no docker-compose usando os valores de `MAILJET_API_KEY`, `MAILJET_SECRET_KEY` e `DEFAULT_FROM_EMAIL` respectivamente.

## 🔧 Configuração da Aplicação

> ⚠️ **Nota**: Existe um TODO pendente no template sobre a configuração de `FRONT_BASE_URL` para desenvolvimento local.

### URLs da Aplicação

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `QD_API_URL` | URL interna da API | `http://querido-diario-api:8080` | `http://querido-diario-api:8080` |
| `STATIC_URL` | URL dos arquivos estáticos | `http://localhost:8000/api/static/` | `https://admin.domain.com/api/static/` |
| `FRONT_BASE_URL` | URL do frontend | `http://localhost:4200` | `https://domain.com` |

### Configurações Gerais

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DJANGO_SETTINGS_MODULE` | Módulo settings Django | `config.settings` |
| `PROJECT_TITLE` | Título do projeto | `Querido Diário` |
| `EXECUTION_MODE` | Modo de execução | `ALL` |

## 💾 Limites de Recursos (Produção)

### Limites de Memória

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `API_MEMORY_LIMIT` | Limite da API | `1G` |
| `API_MEMORY_RESERVATION` | Reserva da API | `512M` |
| `BACKEND_MEMORY_LIMIT` | Limite do Backend | `1G` |
| `BACKEND_MEMORY_RESERVATION` | Reserva do Backend | `512M` |
| `CELERY_WORKER_MEMORY_LIMIT` | Limite do Celery Worker | `1G` |
| `CELERY_WORKER_MEMORY_RESERVATION` | Reserva do Celery Worker | `512M` |
| `DATA_PROCESSING_MEMORY_LIMIT` | Limite do Data Processing | `2G` |
| `DATA_PROCESSING_MEMORY_RESERVATION` | Reserva do Data Processing | `1G` |

### Configuração de Workers

| Variável | Descrição | Desenvolvimento | Produção |
|----------|-----------|-----------------|----------|
| `CELERY_WORKER_REPLICAS` | Replicas do Celery | `1` | `2` |
| `BACKEND_WORKERS` | Workers do Gunicorn | `2` | `2` |

## 📄 Arquivos de Dados

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `CITY_DATABASE_CSV` | Arquivo CSV de cidades | `censo.csv` |
| `THEMES_DATABASE_JSON` | Arquivo JSON de temas | `themes_config.json` |

## 🔧 Apache Tika

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `APACHE_TIKA_SERVER` | URL do servidor Tika | `http://apache-tika:9998` |

## 📋 Checklist de Configuração

### Desenvolvimento

- [ ] Executar `make setup-env-dev`
- [ ] Verificar portas disponíveis (8080, 8000, 5432, 9200, 9000)
- [ ] Executar `make dev`

### Produção

- [ ] Executar `make setup-env-prod`
- [ ] Configurar banco de dados externo
- [ ] Configurar OpenSearch externo
- [ ] Configurar storage externo
- [ ] Configurar credenciais do Mailjet
- [ ] Gerar chave secreta Django segura
- [ ] Configurar DNS dos domínios
- [ ] Configurar Traefik/SSL
- [ ] Testar conectividade externa
- [ ] Executar deploy via Portainer
