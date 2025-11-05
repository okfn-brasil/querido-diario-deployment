# Configuração do Traefik

> 📅 **Última atualização**: Novembro 2025 (CORS fix + Cloudflare SSL limitations)
> ⚠️ **Versão**: Traefik v3.5 (integrado)

## ⚠️ IMPORTANTE: Limitações de SSL do Cloudflare

**Cloudflare Free/Pro não pode emitir certificados SSL para subdomínios de segundo nível!**

### O que funciona com Cloudflare Proxy:
- ✅ `ok.org.br` (domínio raiz)
- ✅ `queridodiario.ok.org.br` (primeiro nível)

### O que NÃO funciona com Cloudflare Proxy:
- ❌ `www.queridodiario.ok.org.br` (segundo nível)
- ❌ Qualquer `*.queridodiario.ok.org.br` (segundo nível)

### Solução: DNS-Only + Traefik

**Todos os subdomínios multi-nível devem:**
1. Usar **DNS-only mode** (gray cloud) no Cloudflare
2. Apontar diretamente para o servidor Traefik
3. Obter SSL certificates via **Let's Encrypt** no Traefik

```
DNS Configuration:
  queridodiario.ok.org.br          → Cloudflare Proxy (orange cloud) ✅
  www.queridodiario.ok.org.br      → DNS-only (gray cloud) → Traefik ✅
  api.queridodiario.ok.org.br      → DNS-only (gray cloud) → Traefik ✅
  www.api.queridodiario.ok.org.br  → DNS-only (gray cloud) → Traefik ✅
  backend-api.queridodiario        → DNS-only (gray cloud) → Traefik ✅
  www.backend-api.queridodiario    → DNS-only (gray cloud) → Traefik ✅
```

## Visão Geral

Após a refatoração, o Traefik foi **oficialmente integrado** ao docker-compose
principal, eliminando a necessidade de configuração separada. O Traefik é
automaticamente configurado e iniciado junto com os demais serviços.

## ✅ Principais Mudanças

- **Integração completa**: Traefik faz parte do `docker-compose.yml`
- **Configuração automática**: SSL, middlewares e roteamento pré-configurados
- **Desenvolvimento sem HTTPS**: HTTP local para facilitar desenvolvimento
- **Produção com SSL automático**: Let's Encrypt integrado
- **WWW redirect**: Redirecionamento automático de www para non-www
- **Multi-level subdomain support**: SSL para todos os subdomínios via Let's Encrypt

## Configuração Automática

### Para Desenvolvimento

```bash
make dev
```

**Configuração automática:**
- HTTP apenas (sem SSL)
- Roteamento para `api.queridodiario.local` e `backend-api.queridodiario.local`
- Middlewares de CORS e compressão
      
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

**CRÍTICO: Configure o Proxy Status corretamente no Cloudflare!**

#### Cloudflare DNS Settings:

| Type | Name | Content | Proxy Status | SSL |
|------|------|---------|--------------|-----|
| A | `queridodiario` | IP_DO_SERVIDOR | ☁️ Proxied (Orange) | Cloudflare |
| A | `www.queridodiario` | IP_DO_SERVIDOR | 🔒 DNS only (Gray) | Traefik/Let's Encrypt |
| A | `api.queridodiario` | IP_DO_SERVIDOR | 🔒 DNS only (Gray) | Traefik/Let's Encrypt |
| A | `www.api.queridodiario` | IP_DO_SERVIDOR | 🔒 DNS only (Gray) | Traefik/Let's Encrypt |
| A | `backend-api.queridodiario` | IP_DO_SERVIDOR | 🔒 DNS only (Gray) | Traefik/Let's Encrypt |
| A | `www.backend-api.queridodiario` | IP_DO_SERVIDOR | 🔒 DNS only (Gray) | Traefik/Let's Encrypt |

**Por quê?**
- **Orange Cloud (Proxied)**: Cloudflare pode emitir SSL apenas para primeiro nível (`queridodiario.ok.org.br`)
- **Gray Cloud (DNS only)**: Multi-level subdomains (`www.queridodiario.ok.org.br`) precisam SSL do Traefik

**Sintoma se configurado errado:**
```
SSL handshake failure
TLS alert, handshake failure (552)
CORS errors from www subdomain
```

#### Exemplo de configuração correta:

```bash
# No Cloudflare:
# 1. Vá em DNS Settings
# 2. Para cada registro A:
#    - queridodiario: Clique na nuvem para ficar LARANJA (Proxied)
#    - www, api, www.api, backend-api, www.backend-api: 
#      Clique na nuvem para ficar CINZA (DNS only)
```

**WWW Redirect Coverage:**
- ✅ `www.queridodiario.ok.org.br` → `queridodiario.ok.org.br`
- ✅ `www.api.queridodiario.ok.org.br` → `api.queridodiario.ok.org.br`
- ✅ `www.backend-api.queridodiario.ok.org.br` → `backend-api.queridodiario.ok.org.br`

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

1. **Definições globais**: Edite `docker-compose.traefik.example.yml`
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

## CORS e API Redirect (Novembro 2025)

### Problema Resolvido

O sistema tinha três problemas com CORS:

1. **301 Redirect sem CORS headers**: Quando o frontend chamava `/api/*`, recebia um redirect 301 para `api.domain` sem headers CORS
2. **SSL Certificate inválido**: O subdomínio da API usava certificado auto-assinado
3. **CORS headers não aplicados a redirects**: Os middlewares CORS não eram aplicados nas respostas de redirect

### Solução Implementada

#### 1. Redirect com CORS Headers

Criado middleware específico que adiciona CORS headers antes do redirect:

```yaml
# CORS for redirects - separate middleware that adds CORS to redirect responses
- "traefik.http.middlewares.cors-redirect.headers.accessControlAllowMethods=GET,POST,OPTIONS,PUT,DELETE,PATCH"
- "traefik.http.middlewares.cors-redirect.headers.accessControlAllowOriginList=https://${DOMAIN},https://api.${DOMAIN},https://backend-api.${DOMAIN},https://backend.${DOMAIN},https://querido-diario-plataforma.netlify.app"
- "traefik.http.middlewares.cors-redirect.headers.accessControlAllowHeaders=Content-Type,Authorization,X-Requested-With,Accept,Origin,Access-Control-Request-Method,Access-Control-Request-Headers"
- "traefik.http.middlewares.cors-redirect.headers.accessControlAllowCredentials=true"
- "traefik.http.middlewares.cors-redirect.headers.accessControlMaxAge=3600"
- "traefik.http.middlewares.cors-redirect.headers.accessControlExposeHeaders=Content-Length,Content-Range"
- "traefik.http.middlewares.cors-redirect.headers.addVaryHeader=true"
```

#### 2. API Redirect Middleware

Middleware que redireciona `/api/*` para `api.domain/*` mantendo o path:

```yaml
# API Redirect Middleware - Redirect /api/* to api.domain with CORS headers
- "traefik.http.middlewares.api-redirect.redirectregex.regex=^https?://([^/]+)/api/(.*)"
- "traefik.http.middlewares.api-redirect.redirectregex.replacement=https://api.$${1}/$${2}"
- "traefik.http.middlewares.api-redirect.redirectregex.permanent=false"
```

**Nota**: Usa redirect 302 (temporary) em vez de 301 (permanent) para evitar cache agressivo do browser.

#### 3. WWW to Non-WWW Redirect

**Importante**: Por limitações de SSL do Cloudflare, o redirecionamento www é gerenciado pelo Traefik:

```yaml
# Roteamento para www subdomain com SSL via Let's Encrypt
- "traefik.http.routers.frontend-www-redirect.rule=Host(`www.${DOMAIN}`)"
- "traefik.http.routers.frontend-www-redirect.entrypoints=web,websecure"
- "traefik.http.routers.frontend-www-redirect.tls.certresolver=leresolver"
- "traefik.http.routers.frontend-www-redirect.middlewares=www-to-non-www"
- "traefik.http.routers.frontend-www-redirect.priority=10"

# Middleware de redirecionamento
- "traefik.http.middlewares.www-to-non-www.redirectregex.regex=^https://www\\.(.*)"
- "traefik.http.middlewares.www-to-non-www.redirectregex.replacement=https://$${1}"
- "traefik.http.middlewares.www-to-non-www.redirectregex.permanent=true"
```

**Por que não usar Cloudflare para isso?**
- Cloudflare Free/Pro não pode emitir certificado SSL para `www.queridodiario.ok.org.br`
- Resultado: SSL handshake failure
- Solução: DNS-only no Cloudflare + redirect no Traefik com Let's Encrypt

**Nota importante sobre ACME challenges:**
Os routers de redirect incluem `!PathPrefix('/.well-known/acme-challenge/')` para garantir que o Let's Encrypt possa validar o domínio durante a emissão do certificado. Sem isso, o redirect interfere na validação ACME e os certificados falham com erro 403.

#### 4. Certificado SSL para api.domain

O router da API garante que o Let's Encrypt gera certificado para `api.${DOMAIN}`:

```yaml
# Roteamento de subdomínio da API (api.dominio)
- "traefik.http.routers.querido-diario-api.rule=Host(`api.${DOMAIN}`)"
- "traefik.http.routers.querido-diario-api.entrypoints=web,websecure"
- "traefik.http.routers.querido-diario-api.tls.certresolver=${CERT_RESOLVER:-leresolver}"
```

#### 4. Router para /api/* Path

O router do path `/api/*` agora usa os middlewares de CORS e redirect:

```yaml
# Roteamento de caminho da API no domínio principal (/api/* redireciona para api.domain com CORS)
- "traefik.http.routers.querido-diario-api-path.rule=Host(`${DOMAIN}`) && PathPrefix(`/api`)"
- "traefik.http.routers.querido-diario-api-path.entrypoints=web,websecure"
- "traefik.http.routers.querido-diario-api-path.tls.certresolver=${CERT_RESOLVER:-leresolver}"
- "traefik.http.routers.querido-diario-api-path.middlewares=cors-redirect,api-redirect"
- "traefik.http.routers.querido-diario-api-path.priority=100"
```

### Fluxo Completo

1. Browser faz requisição para `https://queridodiario.ok.org.br/api/cities?levels=3`
2. Traefik aplica middleware `cors-redirect` (adiciona CORS headers)
3. Traefik aplica middleware `api-redirect` (gera redirect para `https://api.queridodiario.ok.org.br/cities?levels=3`)
4. Browser recebe 302 com CORS headers válidos
5. Browser segue redirect para `api.queridodiario.ok.org.br`
6. Traefik serve a API com certificado SSL válido e CORS headers

### Testando

```bash
# Teste 1: Verificar redirect com CORS
curl -I https://queridodiario.ok.org.br/api/cities?levels=3

# Deve retornar:
# HTTP/2 302
# location: https://api.queridodiario.ok.org.br/cities?levels=3
# access-control-allow-origin: https://queridodiario.ok.org.br
# access-control-allow-credentials: true

# Teste 2: Verificar API direta com SSL válido
curl -I https://api.queridodiario.ok.org.br/cities?levels=3

# Deve retornar:
# HTTP/2 200
# access-control-allow-origin: *
# (sem erro de SSL)

# Teste 3: Teste completo do browser
# Abra https://queridodiario.ok.org.br e verifique que não há erros CORS no console
```
