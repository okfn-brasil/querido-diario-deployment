# Querido Diário - Deployment

Sistema simplificado de deploy da plataforma Querido Diário com suporte para desenvolvimento e produção.

## 🚀 Início Rápido

### Desenvolvimento
```bash
make dev                # Gera .env + inicia todos os serviços localmente
```

### Produção  
```bash
make setup-env-prod     # Gera .env a partir do template
# Editar .env com suas configurações específicas
make prod               # Deploy de produção
```

## 📋 Visão Geral da Plataforma

A plataforma Querido Diário é composta por:

- **API** (FastAPI): Serviço de acesso aos dados das gazetas
- **Backend** (Django): Interface web para administração
- **Data Processing**: Processamento de documentos de gazetas
- **Frontend** (Angular): Interface do usuário (deploy separado)
- **Infraestrutura**: PostgreSQL, OpenSearch, MinIO/S3, Redis, Traefik

## 🎯 Estrutura Simplificada

Após a refatoração, o projeto foi drasticamente simplificado:

### Estrutura de Arquivos
```
📁 querido-diario-deployment/
├── 📋 TEMPLATES (Fonte única da verdade)
│   └── templates/
│       ├── env.prod.sample             # Template de variáveis para produção
│       ├── docker-compose.yml          # Configuração completa com Traefik integrado
│       └── docker-compose.dev.yml      # Overrides para desenvolvimento local
│
├── 🤖 GERADOS (só o .env, ignore no git)
│   └── .env                            # Arquivo de ambiente para o ambiente atual
│
├── 📚 DOCUMENTAÇÃO
│   └── docs/                           # Documentação técnica
│
├── 🗂️ OUTROS
│   ├── Makefile                        # Comandos simplificados
│   ├── init-scripts/                   # Scripts de inicialização de bancos
│   └── _deprecated/                    # Scripts antigos movidos (não usar)
```

## 🎮 Comandos Principais

| Comando | Descrição |
|---------|-------------|
| `make dev` | Inicia ambiente de desenvolvimento completo |
| `make dev-build` | Reconstrói e inicia ambiente de desenvolvimento |
| `make prod` | Inicia ambiente de produção |
| `make prod-build` | Reconstrói e inicia ambiente de produção |
| `make setup-env-dev` | Gera .env para desenvolvimento |
| `make setup-env-prod` | Gera .env para produção |
| `make validate` | Valida sintaxe dos arquivos docker-compose |
| `make clean` | Para containers e remove volumes |
| `make clean-all` | Limpeza completa |
| `make logs` | Mostra logs de todos os serviços |
| `make status` | Mostra status dos serviços |
| `make help` | Lista todos os comandos disponíveis |

## 🏗️ Configuração de Ambientes

### Desenvolvimento

O ambiente de desenvolvimento usa containers locais para toda a infraestrutura e está configurado para funcionar "out of the box":

```bash
make dev                        # Um comando, tudo funcionando!
```

**Características:**

- ✅ Configuração automática com domínio local (`queridodiario.local`)
- ✅ Todos os serviços em containers locais (PostgreSQL, OpenSearch, MinIO, Redis)
- ✅ Traefik configurado para HTTP (sem SSL)
- ✅ Debug habilitado
- ✅ CORS permissivo para desenvolvimento
- ✅ Dados persistentes em volumes locais
- ✅ Portas expostas para acesso direto aos serviços

**URLs disponíveis:**
- API: http://localhost:8080 ou http://api.queridodiario.local
- Backend: http://localhost:8000 ou http://backend-api.queridodiario.local
- OpenSearch: http://localhost:9200
- MinIO: http://localhost:9000
- Redis: localhost:6378

### Produção

O ambiente de produção usa o mesmo docker-compose principal, mas sem os profiles de desenvolvimento e com configurações para serviços externos:

```bash
make setup-env-prod             # Gera .env baseado no template
# Editar .env com suas configurações
make prod                       # Deploy de produção
```

**Características:**

- ✅ Traefik integrado com SSL automático (Let's Encrypt)
- ✅ Configuração para serviços externos (PostgreSQL, OpenSearch, S3)
- ✅ Debug desabilitado
- ✅ HTTPS obrigatório
- ✅ Configurações de segurança e performance
- ✅ Limites de recursos configurados

## ⚙️ Configuração de Produção

### Variáveis Obrigatórias

Edite o arquivo `.env` gerado com suas configurações:

```bash
# DOMÍNIO (obrigatório)
DOMAIN=queridodiario.ok.org.br

# SEGURANÇA (obrigatório)
QD_BACKEND_SECRET_KEY=sua-chave-super-secreta-django

# BANCO DE DADOS - API (externo)
QD_DATA_DB_HOST=seu-postgres-host
QD_DATA_DB_USER=seu-usuario
QD_DATA_DB_PASSWORD=sua-senha
QD_DATA_DB_NAME=queridodiario

# BANCO DE DADOS - Backend (externo)
QD_BACKEND_DB_HOST=seu-postgres-host
QD_BACKEND_DB_USER=seu-usuario-backend
QD_BACKEND_DB_PASSWORD=sua-senha-backend
QD_BACKEND_DB_NAME=backend

# OPENSEARCH (externo)
QUERIDO_DIARIO_OPENSEARCH_HOST=https://seu-opensearch:9200
QUERIDO_DIARIO_OPENSEARCH_USER=usuario
QUERIDO_DIARIO_OPENSEARCH_PASSWORD=senha

# STORAGE S3/MinIO (externo)
STORAGE_ENDPOINT=https://seu-s3.amazonaws.com
STORAGE_ACCESS_KEY=sua-access-key
STORAGE_ACCESS_SECRET=sua-secret-key
STORAGE_BUCKET=queridodiariobucket

# EMAIL - Mailjet
MAILJET_API_KEY=sua-chave-mailjet
MAILJET_SECRET_KEY=sua-secret-mailjet
DEFAULT_FROM_EMAIL=noreply@queridodiario.ok.org.br
```

### Infraestrutura Necessária

- **Servidor**: Docker + Docker Compose
- **PostgreSQL**: Instância externa para dados
- **OpenSearch**: Cluster externo para busca
- **S3/Storage**: Serviço de armazenamento de arquivos
- **DNS**: Registros A/CNAME apontando para o servidor

## 🎯 Principais Melhorias da Refatoração

### ✅ Simplificação Radical

1. **Eliminação de scripts complexos**: Não é mais necessário gerar arquivos intermediários
2. **Traefik integrado**: Reverse proxy e SSL fazem parte da stack principal
3. **Configuração única**: Um arquivo `.env` para cada ambiente
4. **Comandos diretos**: `make dev` e `make prod` fazem tudo automaticamente

### ✅ Redução de Complexidade

**ANTES:**
- 6+ arquivos para gerar
- Scripts Python complexos
- Templates separados para diferentes componentes
- Configuração manual de Traefik
- Múltiplos arquivos de ambiente

**DEPOIS:**
- 1 arquivo `.env` por ambiente
- Docker Compose direto dos templates
- Traefik integrado na stack
- Comandos Make simples

### ✅ Desenvolvimento Local Otimizado

- **HTTP local**: Sem necessidade de certificados para desenvolvimento
- **Domínio local padrão**: `queridodiario.local` configurado automaticamente
- **Portas expostas**: Acesso direto aos serviços para debugging
- **Volumes persistentes**: Dados mantidos entre restarts

### ✅ Produção Simplificada

- **Configuração externa**: Bancos e storage externos
- **SSL automático**: Let's Encrypt integrado
- **Segurança**: Headers e rate limiting configurados
- **Performance**: Limites de recursos otimizados

## 📚 Documentação Técnica

Consulte a documentação detalhada em [`docs/`](docs/):

- **[Deploy com Portainer](docs/portainer-deployment.md)** - Guia de produção
- **[Configuração do Traefik](docs/traefik-setup.md)** - Setup de reverse proxy e SSL
- **[Variáveis de Ambiente](docs/environment-variables.md)** - Referência completa
- **[Overrides](docs/overrides.md)** - Customizações avançadas

## 🔧 Troubleshooting

### Problemas Comuns

```bash
# Verificar status dos serviços
make status
make health

# Ver logs
make logs                     # Todos os serviços
make logs-api                 # Apenas API
make logs-backend             # Apenas Backend
make logs-traefik             # Apenas Traefik

# Reiniciar serviços
make restart

# Limpeza completa
make clean-all
```

### Comandos de Diagnóstico

```bash
make validate                  # Validar sintaxe dos compose files
make check-env                # Verificar variáveis obrigatórias
make network-create           # Criar rede frontend se necessário
```

### Desenvolvimento - Acesso aos serviços

Se preferir acessar diretamente pelos containers:

```bash
# Shell nos containers
make shell-api               # Acesso ao container da API
make shell-backend           # Acesso ao container do Backend

# Reset de banco (desenvolvimento)
make db-reset               # Roda migrações do Django
```

## 🤝 Contribuição

Para contribuir com melhorias:

1. **Edite templates**: Modifique arquivos em `templates/`
2. **Teste mudanças**: Use `make dev` para testar
3. **Valide**: Execute `make validate`
4. **Atualize docs**: Modifique documentação conforme necessário

### Fluxo de Desenvolvimento

```bash
# 1. Faça suas mudanças nos templates
vim templates/docker-compose.yml
vim templates/env.prod.sample

# 2. Teste
make clean-all
make dev

# 3. Valide configurações
make validate
make status
```

## 📄 Licença

Este projeto está licenciado sob os termos definidos no arquivo [LICENSE.md](LICENSE.md).

---

## 🎉 Resumo da Nova Estrutura

A refatoração do projeto resultou em uma estrutura **drasticamente mais simples**:

- **✅ Zero geração de arquivos intermediários**
- **✅ Traefik oficialmente parte da stack**
- **✅ Configuração local sem HTTPS** para desenvolvimento
- **✅ Um comando para rodar tudo** (`make dev` / `make prod`)
- **✅ Templates como fonte única da verdade**
- **✅ Ambiente de desenvolvimento funciona out-of-the-box**

O objetivo foi **eliminar complexidade desnecessária** mantendo toda a funcionalidade necessária para desenvolvimento e produção.