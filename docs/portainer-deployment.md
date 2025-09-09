# Deploy com Portainer

> 📅 **Última atualização**: Setembro 2025

## Visão Geral

Este guia explica como fazer deploy da plataforma Querido Diário usando Portainer, uma interface web para gerenciamento de containers Docker.

## Pré-requisitos

### Infraestrutura Externa Necessária

- **PostgreSQL** (instância externa)
- **OpenSearch/Elasticsearch** (cluster externo)
- **S3/MinIO/DigitalOcean Spaces** (storage externo)
- **Traefik** (reverse proxy com SSL)
- **Mailjet** (serviço de email)

### Servidor

- Docker e Docker Compose instalados
- Portainer instalado e configurado
- Network `frontend` criada para Traefik
- Certificados SSL configurados

## Processo de Deploy

### 1. Gerar Arquivos de Produção

```bash
# No repositório querido-diario-deployment
make generate-all
```

Isso irá gerar:

- `docker-compose-portainer.yml` - configuração otimizada para Portainer
- `.env.production` - variáveis de ambiente para produção

### 2. Configurar Variáveis de Ambiente

Edite o arquivo `.env.production` gerado com suas configurações:

```bash
```bash
# Domínios
DOMAIN=queridodiario.ok.org.br
# API será acessível em: api.${DOMAIN}
# Backend será acessível em: backend-api.${DOMAIN}

# Banco de Dados (externo)
# NOTA: Para o Portainer, ainda pode ser útil definir QD_BACKEND_DB_URL diretamente
# ou usar as variáveis individuais que serão interpoladas no docker-compose:
QD_BACKEND_DB_URL=postgres://user:password@external-db:5432/querido_diario
# OU alternativamente:
# POSTGRES_HOST=external-db
# POSTGRES_PORT=5432
# POSTGRES_DB=querido_diario
# POSTGRES_USER=user
# POSTGRES_PASSWORD=password

POSTGRES_COMPANIES_HOST=external-db.com
POSTGRES_AGGREGATES_HOST=external-db.com

# OpenSearch (externo)
QUERIDO_DIARIO_OPENSEARCH_HOST=external-opensearch.com:9200
QUERIDO_DIARIO_OPENSEARCH_USER=admin
QUERIDO_DIARIO_OPENSEARCH_PASSWORD=senha_segura

# Storage (externo)
QUERIDO_DIARIO_FILES_ENDPOINT=https://storage.example.com/bucket/

# Segurança
QD_BACKEND_SECRET_KEY=chave-super-secreta-django
CERT_RESOLVER=letsencrypt

# Email
MAILJET_API_KEY=sua-chave-mailjet
MAILJET_SECRET_KEY=sua-chave-secreta-mailjet
```

### 3. Deploy via Portainer

#### Opção A: Interface Web

1. Acesse o Portainer
2. Vá em **Stacks** → **Add Stack**
3. Digite um nome: `querido-diario`
4. Cole o conteúdo de `docker-compose-portainer.yml`
5. Em **Environment Variables**, cole o conteúdo de `.env.production`
6. Clique em **Deploy the stack**

#### Opção B: Via Git Repository

1. No Portainer, vá em **Stacks** → **Add Stack**
2. Selecione **Repository**
3. Configure:
   - **Repository URL**: URL do seu repositório
   - **Reference**: branch de produção
   - **Compose path**: `docker-compose-portainer.yml`
   - **Environment file**: `.env.production`

### 4. Verificar Deploy

```bash
# Verificar se todos os serviços estão rodando
docker ps

# Verificar logs
docker logs querido-diario-api
docker logs querido-diario-backend

# Testar endpoints
curl https://api.queridodiario.ok.org.br/health
curl https://admin.queridodiario.ok.org.br/health/
```

## Configurações de Rede

### Traefik Labels

O arquivo gerado automaticamente inclui labels do Traefik para:

- **Roteamento HTTPS**: baseado em domínio
- **Certificados SSL**: via Let's Encrypt
- **Redirecionamento HTTP→HTTPS**: automático
- **Load Balancing**: entre replicas

### Networks

- **frontend**: network externa compartilhada com Traefik
- **querido-diario-internal**: network interna para comunicação entre serviços

## Recursos e Limitações

### Configurações de Memória

O arquivo gerado inclui limitações de recursos configuráveis:

```bash
# Limites de memória (em .env.production)
API_MEMORY_LIMIT=1G
BACKEND_MEMORY_LIMIT=1G
CELERY_WORKER_MEMORY_LIMIT=1G
DATA_PROCESSING_MEMORY_LIMIT=2G
APACHE_TIKA_MEMORY_LIMIT=2G

# Replicas
CELERY_WORKER_REPLICAS=2
```

### Monitoramento

Todos os serviços incluem:

- **Health checks** configurados
- **Restart policies** automáticas
- **Logging** estruturado

## Troubleshooting

### Serviços não iniciam

1. Verificar logs do Portainer
2. Validar configurações de rede
3. Confirmar conectividade com serviços externos

```bash
# Verificar conectividade
docker exec querido-diario-api ping external-db.com
docker exec querido-diario-api nc -zv external-opensearch.com 9200
```

### Problemas de SSL

1. Verificar se o network `frontend` existe
2. Confirmar configuração do Traefik
3. Validar DNS dos domínios

### Problemas de Banco de Dados

1. Verificar string de conexão
2. Confirmar permissões do usuário
3. Testar conectividade de rede

```bash
# Testar conexão com banco
docker exec querido-diario-backend python manage.py dbshell
```

## Atualizações

### Atualizar Código

1. Fazer push para o repositório
2. No Portainer, ir na stack
3. Clicar em **Update the stack**
4. Confirmar a atualização

### Atualizar Configurações

1. Regenerar arquivos: `make generate-all`
2. Atualizar `.env.production` se necessário
3. Atualizar stack no Portainer

### Rollback

1. No Portainer, acessar a stack
2. Ver histórico de deployments
3. Selecionar versão anterior
4. Fazer rollback

## Backup e Recuperação

### Backup

- **Código**: versionado no Git
- **Configurações**: `.env.production` deve ser backup
- **Dados**: backup dos serviços externos (PostgreSQL, storage)

### Recuperação

1. Recriar infrastructure externa
2. Restaurar dados
3. Reconfiguar `.env.production`
4. Re-deploy via Portainer

## Segurança

### Variáveis Sensíveis

- Use **Portainer Secrets** para dados sensíveis
- Nunca commite `.env.production` no Git
- Rotacione chaves regularmente

### Network Security

- Services internos isolados na network `querido-diario-internal`
- Apenas API e Backend expostos via Traefik
- Comunicação externa via HTTPS apenas

### Monitoramento d esegurança

- Configure alertas para falhas de serviço
- Monitore uso de recursos
- Acompanhe logs de segurança
