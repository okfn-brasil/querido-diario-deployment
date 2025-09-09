# Querido Diário - Deployment

Sistema automatizado de deploy da plataforma Querido Diário com suporte completo para desenvolvimento e produção.

## 🚀 Início Rápido

### Desenvolvimento
```bash
make dev                # Gera .env + inicia todos os serviços
```

### Produção  
```bash
make generate-all       # Gera arquivos de produção
# Editar .env.production conforme necessário
make prod               # Deploy via Portainer
```

## 📋 Visão Geral da Plataforma

A plataforma Querido Diário é composta por:

- **API** (FastAPI): Serviço de acesso aos dados das gazetas
- **Backend** (Django): Interface web para administração
- **Data Processing**: Processamento de documentos de gazetas
- **Frontend** (Angular): Interface do usuário (deploy separado)
- **Infraestrutura**: PostgreSQL, OpenSearch, MinIO/S3, Redis

## 🎯 Sistema de Geração Automática

Esta solução elimina redundâncias através de **geração automática** de configurações:

### Estrutura de Arquivos
```
📁 querido-diario-deployment/
├── 🎯 TEMPLATES MESTRES
│   └── templates/
│       ├── env.complete.sample          # Template mestre de variáveis
│       ├── overrides.example            # Exemplo de sobrescritas
│       ├── docker-compose.yml           # Configuração base completa
│       ├── docker-compose.dev.yml       # Overrides de desenvolvimento
│       └── docker-compose.traefik.example.yml  # Template Traefik
│
├── 🤖 GERADOS AUTOMATICAMENTE (ignorados pelo git)
│   ├── .env                            # Para desenvolvimento
│   ├── .env.production                 # Para produção
│   ├── docker-compose.yml              # Copiado do template
│   ├── docker-compose.dev.yml          # Copiado do template
│   ├── docker-compose-portainer.yml    # Gerado para produção
│   └── docker-compose.traefik.yml      # Copiado do template
│
├── 🛠️ AUTOMAÇÃO
│   ├── scripts/
│   │   ├── generate-env.py              # Gerador unificado de .env
│   │   └── generate-portainer-compose.py # Gerador de produção
│   └── Makefile                         # Comandos automatizados
│
└── 📚 DOCUMENTAÇÃO
    └── docs/                            # Documentação técnica
```

## 🎮 Comandos Principais

| Comando | Descrição |
|---------|-------------|
| `make dev` | Gera arquivos + inicia ambiente de desenvolvimento |
| `make generate-dev` | Gera docker-compose.yml + docker-compose.dev.yml |
| `make generate-prod` | Gera docker-compose-portainer.yml para produção |
| `make generate-traefik` | Gera docker-compose.traefik.yml |
| `make setup-env-dev` | Gera .env para desenvolvimento |
| `make setup-env-prod` | Gera .env.production para produção |
| `make generate-all` | Gera todos os arquivos de produção |
| `make prod` | Deploy completo de produção |
| `make validate` | Valida sintaxe dos arquivos docker-compose |
| `make clean-env` | Remove arquivos gerados |
| `make help` | Lista todos os comandos disponíveis |

## 🏗️ Configuração de Ambientes

### Desenvolvimento

O ambiente de desenvolvimento usa containers locais para toda a infraestrutura:

```bash
# Setup automatizado (recomendado)
make dev                        # Gera arquivos + inicia todos os serviços

# Setup manual (se necessário)
make generate-dev              # Gera docker-compose.yml + docker-compose.dev.yml
make setup-env-dev             # Gera .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d
```

**Características:**

- Todos os serviços em containers locais
- Debug habilitado
- CORS permissivo para desenvolvimento
- Dados persistentes em volumes locais

### Produção

O ambiente de produção usa serviços externos gerenciados:

```bash
# Setup automatizado (recomendado)
make generate-all              # Gera docker-compose-portainer.yml + .env.production
# Editar .env.production com configurações de produção
make prod                      # Deploy via Portainer

# Setup manual (se necessário)
make generate-prod             # Gera docker-compose-portainer.yml
make setup-env-prod           # Gera .env.production
# Editar .env.production
docker compose -f docker-compose-portainer.yml --env-file .env.production up -d
```

**Características:**

- Serviços externos para infraestrutura (PostgreSQL, OpenSearch, S3)
- Debug desabilitado
- HTTPS obrigatório via Traefik
- Configurações de segurança e performance
- Limites de recursos configurados

## ⚙️ Configuração de Produção

### Serviços Externos Necessários

Antes do deploy de produção, configure:

```bash
# Editar .env.production com suas configurações

# Domínios
DOMAIN=queridodiario.ok.org.br
# API será acessível em: api.${DOMAIN}
# Backend será acessível em: backend-api.${DOMAIN}

# Banco de Dados (externo)
# NOTA: QD_BACKEND_DB_URL é gerada automaticamente no docker-compose.
# Defina apenas as variáveis individuais:
POSTGRES_HOST=external-db
POSTGRES_PORT=5432
POSTGRES_DB=db
POSTGRES_USER=user
POSTGRES_PASSWORD=password

# OpenSearch (externo)
# NOTA: QUERIDO_DIARIO_OPENSEARCH_* são geradas automaticamente no docker-compose.
# Defina apenas as variáveis base:
OPENSEARCH_HOST=https://external-opensearch:9200
OPENSEARCH_USER=username
OPENSEARCH_PASSWORD=password

# Storage (externo S3/MinIO/DigitalOcean Spaces)
# NOTA: QUERIDO_DIARIO_FILES_ENDPOINT é gerada automaticamente no docker-compose.
# Defina apenas as variáveis base:
STORAGE_ENDPOINT=https://storage.example.com
STORAGE_BUCKET=bucket

# Segurança
QD_BACKEND_SECRET_KEY=sua-chave-super-secreta

# Email (Mailjet)
MAILJET_API_KEY=sua-chave-mailjet
MAILJET_SECRET_KEY=sua-chave-secreta-mailjet
```

### Infraestrutura Necessária

- **Servidor**: Docker + Docker Compose + Portainer
- **PostgreSQL**: Instância externa para dados
- **OpenSearch**: Cluster externo para busca
- **S3/Storage**: Serviço externo para arquivos
- **Traefik**: Reverse proxy com SSL automático
- **DNS**: Registros apontando para o servidor

## 📚 Documentação Técnica

Consulte a documentação detalhada em [`docs/`](docs/):

### Guias de Setup

- **[Deploy com Portainer](docs/portainer-deployment.md)** - Guia completo de produção
- **[Configuração do Traefik](docs/traefik-setup.md)** - Setup de reverse proxy e SSL
- **[Variáveis de Ambiente](docs/environment-variables.md)** - Referência completa

### Características do Sistema

- **Automatização Completa**: Eliminação de edição manual de configurações
- **Separação de Ambientes**: Dev usa containers locais, prod usa serviços externos
- **Geração Inteligente**: Transformações automáticas por ambiente
- **Segurança**: Configurações otimizadas para produção
- **Performance**: Limites de recursos e replicas configuráveis

## 🔧 Troubleshooting

### Problemas Comuns

```bash
# Arquivos não geram
make clean-env                 # Limpar arquivos antigos
make setup-env-dev            # Tentar novamente

# Serviços não iniciam
docker compose ps             # Ver status
docker compose logs [serviço] # Ver logs específicos

# Problemas de rede
docker network ls             # Verificar networks
make validate                 # Validar configurações
```

### Comandos de Diagnóstico

```bash
make validate                  # Validar sintaxe dos compose files
make health                   # Verificar saúde dos serviços
make status                   # Ver status de todos os containers
```

## 🤝 Contribuição

Para contribuir com melhorias:

1. **Edite templates**: Modifique `templates/env.complete.sample` para adicionar/modificar variáveis
2. **Atualize scripts**: Modifique scripts em `scripts/` se necessário
3. **Teste mudanças**: Use `make generate-dev && make dev` para testar
4. **Regenere arquivos**: Use `make generate-all` para produção
5. **Valide**: Execute `make validate` para verificar sintaxe
6. **Documente**: Atualize documentação em `docs/` conforme necessário

### Fluxo de Desenvolvimento

```bash
# 1. Faça suas mudanças nos templates
vim templates/env.complete.sample

# 2. Regenere e teste
make clean-env
make dev

# 3. Valide configurações
make validate

# 4. Teste produção
make generate-all
```

## 📄 Licença

Este projeto está licenciado sob os termos definidos no arquivo [LICENSE.md](LICENSE.md).

## 🔧 Sistema de Templates

### Variáveis de Ambiente

Todas as variáveis de ambiente são gerenciadas através do template mestre `templates/env.complete.sample`. O sistema gera automaticamente arquivos de ambiente otimizados para cada ambiente:

- **Desenvolvimento**: Serviços locais, debug habilitado, CORS permissivo
- **Produção**: Serviços externos, debug desabilitado, segurança reforçada

Para customizar configurações:

1. **Edite `templates/env.complete.sample`** - Esta é a fonte única da verdade
2. **Regenere arquivos** - Use `make setup-env-dev` ou `make setup-env-prod`
3. **Para produção** - Edite o `.env.production` gerado com seus valores específicos

### Sistema de Overrides

O sistema suporta overrides automáticos através do arquivo `overrides.env`:

```bash
# Copie o exemplo
cp templates/overrides.example overrides.env

# Edite com suas configurações
# Este arquivo será aplicado automaticamente em todos os comandos
```

### Docker Compose Templates

O sistema usa templates para gerar configurações apropriadas:

- **`templates/docker-compose.yml`**: Configuração base completa
- **`templates/docker-compose.dev.yml`**: Overrides para desenvolvimento
- **Geração automática**: `make generate-dev` copia os templates para uso

## 🔍 Validação e Debugging

```bash
# Validar configurações
make validate                  # Valida sintaxe dos compose files
make health                   # Verificar saúde dos serviços
make status                   # Ver status de todos os containers

# Ver logs
make logs                     # Logs de todos os serviços
make logs-api                 # Logs específicos da API
make logs-backend             # Logs específicos do Backend
```
