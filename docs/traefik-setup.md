# Configuração do Traefik

> 📅 **Última atualização**: Setembro 2025  
> ⚠️ **Versão testada**: Traefik v3.0

## Visão Geral

O Traefik é um reverse proxy moderno que gerencia automaticamente o roteamento e certificados SSL para a plataforma Querido Diário.

## Configuração Base

### docker-compose.traefik.yml

```yaml
version: '3.8'

services:
  traefik:
    image: traefik:v3.0
    container_name: traefik
    restart: unless-stopped
    command:
      # Providers
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --providers.docker.network=frontend
      
      # Entrypoints
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      
      # SSL Certificates
      - --certificatesresolvers.letsencrypt.acme.email=admin@queridodiario.ok.org.br
      - --certificatesresolvers.letsencrypt.acme.storage=/acme.json
      - --certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web
      
      # Logging
      - --log.level=INFO
      - --accesslog=true
    
    ports:
      - "80:80"
      - "443:443"
    
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - traefik-acme:/acme.json
    
    networks:
      - frontend
    
    labels:
      # Redirect HTTP para HTTPS
      - "traefik.http.routers.http-catchall.rule=hostregexp(`{host:.+}`)"
      - "traefik.http.routers.http-catchall.entrypoints=web"
      - "traefik.http.routers.http-catchall.middlewares=redirect-to-https"
      - "traefik.http.middlewares.redirect-to-https.redirectscheme.scheme=https"

volumes:
  traefik-acme:
    driver: local

networks:
  frontend:
    external: true
```

### Variáveis de Ambiente

```bash
# .env para Traefik
ACME_EMAIL=admin@queridodiario.ok.org.br
```

## Configuração da Rede

### Criar Network Frontend

```bash
# Criar network compartilhada
docker network create frontend

# Verificar se foi criada
docker network ls | grep frontend
```

### Configuração DNS

Configure os registros DNS para apontar para o servidor:

```
A    queridodiario.ok.org.br           → IP_DO_SERVIDOR
A    api.queridodiario.ok.org.br       → IP_DO_SERVIDOR  
A    admin.queridodiario.ok.org.br     → IP_DO_SERVIDOR
```

## Labels do Traefik

### Labels Automáticos

O sistema de geração automática adiciona os labels necessários:

```yaml
labels:
  # Habilitar Traefik
  - "traefik.enable=true"
  - "traefik.docker.network=frontend"
  
  # Roteamento HTTP (redirect para HTTPS)
  - "traefik.http.routers.querido-diario-api-http.rule=Host(`api.queridodiario.ok.org.br`)"
  - "traefik.http.routers.querido-diario-api-http.entrypoints=web"
  - "traefik.http.routers.querido-diario-api-http.middlewares=https-redirect"
  
  # Roteamento HTTPS
  - "traefik.http.routers.querido-diario-api-https.rule=Host(`api.queridodiario.ok.org.br`)"
  - "traefik.http.routers.querido-diario-api-https.entrypoints=websecure"
  - "traefik.http.routers.querido-diario-api-https.tls=true"
  - "traefik.http.routers.querido-diario-api-https.tls.certresolver=letsencrypt"
  
  # Configuração do serviço
  - "traefik.http.services.querido-diario-api.loadbalancer.server.port=8080"
```

### Middlewares Personalizados

Os middlewares são definidos globalmente no arquivo `docker-compose.traefik.yml` e **aplicados automaticamente** durante a geração do arquivo de produção.

#### Aplicação Automática em Produção

O script `generate-portainer-compose.py` aplica automaticamente os middlewares apropriados:

- **API (`querido-diario-api`)**: `cors-headers,api-rate-limit,security-headers,compression`
- **Backend (`querido-diario-backend`)**: `api-rate-limit,security-headers,compression`

#### Middlewares Disponíveis

```yaml
# CORS Headers - Para APIs que precisam de CORS
cors-headers:
  - accesscontrolallowmethods: GET,POST,OPTIONS,PUT,DELETE
  - accesscontrolalloworigin: https://queridodiario.ok.org.br
  - accesscontrolallowcredentials: true
  - accesscontrolmaxage: 3600

# Rate Limiting - Padrão para aplicações web
rate-limit:
  - burst: 100 requisições
  - average: 50 requisições/minuto

# API Rate Limiting - Mais restritivo para APIs
api-rate-limit:
  - burst: 50 requisições  
  - average: 25 requisições/minuto

# Security Headers - Headers de segurança obrigatórios
security-headers:
  - frameDeny: true (anti-clickjacking)
  - contentTypeNosniff: true
  - browserXssFilter: true
  - referrerPolicy: strict-origin-when-cross-origin
  - HSTS: 1 ano com subdomínios

# Compression - Compressão automática
compression:
  - Gzip/Deflate para responses
```

#### Como Aplicar nos Serviços

**Desenvolvimento Manual**: Para usar os middlewares em desenvolvimento ou configurações customizadas, adicione nas labels:

```yaml
# Exemplo: Configuração manual personalizada
querido-diario-api:
  labels:
    - "traefik.http.routers.api-https.middlewares=cors-headers,rate-limit,security-headers"

# Exemplo: Frontend apenas com segurança e compressão  
querido-diario-frontend:
  labels:
    - "traefik.http.routers.frontend-https.middlewares=security-headers,compression"
```

**Produção**: Os middlewares são aplicados automaticamente pelo script `make generate-prod`:

- ✅ **API**: CORS + Rate limiting restrito + Security headers + Compression
- ✅ **Backend**: Rate limiting restrito + Security headers + Compression

#### Customização

Para ajustar os middlewares:

1. **Definições globais**: Edite `templates/docker-compose.traefik.example.yml`
2. **Aplicação automática**: Edite `scripts/generate-portainer-compose.py`
3. **Regenere os arquivos**: Execute `make generate-all`

## Monitoramento

### Logs

```bash
# Ver logs do Traefik
docker logs traefik -f

# Logs de acesso
docker exec traefik cat /var/log/access.log

# Verificar certificados
docker exec traefik ls -la /acme.json
```

### Métricas

Configure Prometheus para coletar métricas:

```yaml
command:
  - --metrics.prometheus=true
  - --metrics.prometheus.addEntryPointsLabels=true
  - --metrics.prometheus.addServicesLabels=true
```

## Troubleshooting

### Certificados SSL

```bash
# Verificar certificados
docker exec traefik cat /acme.json

# Logs do ACME
docker logs traefik | grep acme

# Forçar renovação
docker exec traefik rm /acme.json
docker restart traefik
```

### Problemas de Roteamento

```bash
# Verificar logs do Traefik
docker logs traefik | grep -i error

# Testar conectividade
docker exec traefik ping querido-diario-api
```

### Network Issues

```bash
# Verificar network
docker network inspect frontend

# Verificar containers na network
docker network inspect frontend | jq '.[0].Containers'

# Testar conectividade
docker exec traefik ping querido-diario-api
```

## Segurança

### Configurações de Segurança

```yaml
command:
  # TLS mínimo
  - --entrypoints.websecure.http.tls.options=modern@file
  
  # Headers de segurança
  - --entrypoints.websecure.http.middlewares=security-headers@docker
  
  # Rate limiting global
  - --entrypoints.websecure.http.middlewares=rate-limit@docker
```

### Firewall

```bash
# Permitir apenas portas necessárias
ufw allow 80
ufw allow 443
ufw allow 22
ufw --force enable
```

## Backup e Recuperação

### Backup

```bash
# Backup dos certificados
docker cp traefik:/acme.json ./backup/acme.json.backup

# Backup da configuração
cp docker-compose.traefik.yml ./backup/
```

### Recuperação

```bash
# Restaurar certificados
docker cp ./backup/acme.json.backup traefik:/acme.json
docker restart traefik
```

## Atualizações

### Atualizar Traefik

```bash
# Fazer backup
docker cp traefik:/acme.json ./acme.json.backup

# Atualizar imagem
docker pull traefik:v3.0
docker compose -f docker-compose.traefik.yml up -d

# Verificar funcionamento
curl -I https://api.queridodiario.ok.org.br
```
