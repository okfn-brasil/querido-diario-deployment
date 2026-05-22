# Configuração do Traefik

> 📅 **Última atualização**: Novembro 2025 (CORS fix + Cloudflare SSL limitations)
> ⚠️ **Versão**: Traefik v3 via Helm (Kubernetes)

## Instalação (Kubernetes)

Traefik é instalado via Helm como DaemonSet com hostPort 80/443:

```bash
helm repo add traefik https://traefik.github.io/charts
helm upgrade --install traefik traefik/traefik \
  -n traefik --create-namespace \
  -f k8s/local/traefik-values.yaml
```

O arquivo `k8s/local/traefik-values.yaml` contém a configuração base. Em produção, ajustar conforme necessário (ACME email, réplicas, etc.).

Roteamento é feito via CRDs `IngressRoute` e `Middleware` do Traefik, definidos nos manifestos em `k8s/base/` e `k8s/base/traefik-middlewares.yaml`.

---

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

## Configuração DNS

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

## Middlewares (Kubernetes)

Definidos em `k8s/base/traefik-middlewares.yaml` como recursos `Middleware` do Traefik CRD e referenciados nas `IngressRoute` de cada serviço.

### Middlewares disponíveis

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

### Como aplicar nos serviços

Referencie o middleware na `IngressRoute` do serviço:

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: api
spec:
  routes:
    - match: Host(`api.queridodiario.ok.org.br`)
      middlewares:
        - name: cors-headers
        - name: api-rate-limit
        - name: security-headers
```

Para customizar, edite `k8s/base/traefik-middlewares.yaml`.

## Troubleshooting

### Logs do Traefik (k8s)

```bash
kubectl logs -n traefik -l app.kubernetes.io/name=traefik -f
kubectl logs -n traefik -l app.kubernetes.io/name=traefik | grep acme
kubectl logs -n traefik -l app.kubernetes.io/name=traefik | grep -i error
```

### Certificados SSL

O Traefik armazena certificados Let's Encrypt em um PVC. Para verificar:

```bash
kubectl get certificate -n querido-diario 2>/dev/null
kubectl logs -n traefik -l app.kubernetes.io/name=traefik | grep "Certificate obtained"
```

### Atualizações do Traefik

```bash
helm upgrade traefik traefik/traefik -n traefik -f k8s/local/traefik-values.yaml
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
