# Configuração de SSL e Redirecionamentos do Traefik

## Resumo das Alterações

Este documento descreve as configurações implementadas no `docker-compose.yml` para garantir o correto funcionamento de SSL/TLS, redirecionamentos WWW e ACME challenges.

## Arquitetura de Roteamento

### Princípio de Design

**Separação de responsabilidades entre entrypoints:**
- **Entrypoint `web` (HTTP/80):** Usado APENAS para ACME challenges e redirecionamento global para HTTPS
- **Entrypoint `websecure` (HTTPS/443):** Usado para TODO o tráfego de aplicação

**Por que isso é importante:**
- Evita duplicação de routers (não precisa ter versões HTTP e HTTPS de cada rota)
- Garante que todo tráfego HTTP seja redirecionado para HTTPS (exceto ACME)
- Simplifica a configuração e reduz chance de erros

## Requisitos Atendidos

### 1. ✅ ACME Challenges (.well-known)

**Problema anterior:** O redirecionamento HTTP→HTTPS estava sendo aplicado globalmente, impedindo que o Let's Encrypt validasse certificados via HTTP challenge.

**Solução implementada:**
```yaml
# Router específico para ACME challenges (HTTP apenas, sem redirect)
- "traefik.http.routers.acme-challenge.rule=PathPrefix(`/.well-known/acme-challenge/`)"
- "traefik.http.routers.acme-challenge.entrypoints=web"
- "traefik.http.routers.acme-challenge.priority=999"

# Redirecionamento HTTP -> HTTPS para todos os hosts (exceto ACME)
- "traefik.http.routers.http-catchall.rule=PathPrefix(`/`) && !PathPrefix(`/.well-known/acme-challenge/`)"
- "traefik.http.routers.http-catchall.entrypoints=web"
- "traefik.http.routers.http-catchall.middlewares=redirect-to-https"
- "traefik.http.routers.http-catchall.priority=1"
```

**Como funciona:**
- Um router com prioridade 999 captura todas as requisições para `/.well-known/acme-challenge/` no entrypoint HTTP (porta 80)
- O router http-catchall tem prioridade 1 e redireciona todo o resto do tráfego HTTP para HTTPS
- A exclusão explícita de ACME challenges garante que o Let's Encrypt possa validar domínios via HTTP

### 2. ✅ Redirecionamento WWW → Parent Domain

**Problema anterior:** Havia middlewares específicos redundantes para cada subdomínio.

**Solução implementada:**

#### Middleware Universal
Um único middleware global captura TODOS os casos:
```yaml
# Middleware global para redirecionamento www -> non-www
- "traefik.http.middlewares.www-to-non-www.redirectregex.regex=^https?://www\\.(.*)"
- "traefik.http.middlewares.www-to-non-www.redirectregex.replacement=https://$${1}"
- "traefik.http.middlewares.www-to-non-www.redirectregex.permanent=true"
```

#### Routers WWW usando o middleware global
```yaml
# Domínio principal: www.domain → domain
- "traefik.http.routers.qd-frontend-www-redirect.middlewares=www-to-non-www"

# API: www.api.domain → api.domain
- "traefik.http.routers.querido-diario-api-www-redirect.middlewares=www-to-non-www"

# Backend: www.backend-api.domain → backend-api.domain
- "traefik.http.routers.querido-diario-backend-www-redirect.middlewares=www-to-non-www"
```

**Como funciona:**
- Regex `^https?://www\\.(.*)` captura tudo após `www.`
- Funciona para qualquer nível de subdomínio: `www.example.com`, `www.api.example.com`, `www.x.y.z.example.com`
- Todos os redirecionamentos WWW são permanentes (301)
- Routers WWW operam apenas no entrypoint HTTPS (websecure)
- O redirect HTTP→HTTPS acontece primeiro (via http-catchall), depois o redirect WWW→non-WWW

### 3. ✅ Redirecionamento HTTP → HTTPS

**Problema anterior:** O redirect era temporário (302) e não excluía ACME challenges explicitamente.

**Solução implementada:**
```yaml
- "traefik.http.middlewares.redirect-to-https.redirectscheme.scheme=https"
- "traefik.http.middlewares.redirect-to-https.redirectscheme.permanent=true"
```

**Como funciona:**
- Redirect permanente (301) para melhor SEO e performance
- Exclusão explícita de `/.well-known/acme-challenge/` no router
- Prioridade configurada corretamente (1) para não interferir com ACME (999)

## Fluxo de Requisições

### Entrypoint HTTP (web - porta 80)

**Regra 1: ACME Challenge (prioridade 999)**
```
http://qualquer-dominio/.well-known/acme-challenge/xxx
↓
Router: acme-challenge
↓
Let's Encrypt valida o certificado
✅ Resposta direta, sem redirecionamento
```

**Regra 2: Todo o resto (prioridade 1)**
```
http://qualquer-dominio/qualquer-path
↓
Router: http-catchall
↓
Middleware: redirect-to-https
↓
301 → https://qualquer-dominio/qualquer-path
```

### Entrypoint HTTPS (websecure - porta 443)

**Todos os routers de serviços operam APENAS neste entrypoint:**
- querido-diario-api (`api.domain`)
- querido-diario-api-path (`domain/api/*` → redirect para `api.domain`)
- querido-diario-backend (`backend-api.domain`)
- qd-frontend-main (`domain`)

**Routers de redirecionamento WWW:**
- `www.domain` → `domain`
- `www.api.domain` → `api.domain`
- `www.backend-api.domain` → `backend-api.domain`

### Cenário 1: Geração de Certificado SSL
```
http://example.com/.well-known/acme-challenge/xxx
↓
Router: acme-challenge (priority 999)
↓
Let's Encrypt valida o certificado
✅ Sem redirecionamento
```

### Cenário 2: Request HTTP Normal
```
http://example.com/
↓
Router: http-catchall (priority 1)
↓
Middleware: redirect-to-https
↓
301 → https://example.com/
```

### Cenário 3: Request para WWW
```
http://www.example.com/
↓
Router: http-catchall
↓
301 → https://www.example.com/
↓
Router: qd-frontend-www-redirect
↓
Middleware: www-to-non-www
↓
301 → https://example.com/
```

### Cenário 4: ACME Challenge em WWW
```
http://www.example.com/.well-known/acme-challenge/xxx
↓
Router: acme-challenge (priority 999)
↓
Let's Encrypt valida o certificado
✅ Sem redirecionamento
```

## Redundâncias Eliminadas

### 1. ❌ Routers com `entrypoints=web,websecure` (REMOVIDO)

**Problema anterior:**
- Routers de serviços tinham `entrypoints=web,websecure`
- Isso fazia com que respondessem diretamente em HTTP
- Conflitava com o router global `http-catchall`
- Dependendo da prioridade, poderia não redirecionar corretamente

**Solução aplicada:**
- Todos os routers de serviço agora usam APENAS `entrypoints=websecure`
- Router global `http-catchall` é o ÚNICO que captura tráfego HTTP (exceto ACME)
- Garante que 100% do tráfego HTTP seja redirecionado para HTTPS

**Routers corrigidos:**
```yaml
# Antes (INCORRETO):
- "traefik.http.routers.querido-diario-api.entrypoints=web,websecure"

# Depois (CORRETO):
- "traefik.http.routers.querido-diario-api.entrypoints=websecure"
```

**Total:** 4 routers corrigidos (API, API-path, Backend, Frontend)

### 2. ❌ Middlewares WWW específicos (REMOVIDO)

**Problema anterior:**
```yaml
# Middlewares separados para cada serviço
- "traefik.http.middlewares.www-api-to-api.redirectregex.regex=^https?://www\\.api\\.(.*)"
- "traefik.http.middlewares.www-backend-api-to-backend-api.redirectregex.regex=^https?://www\\.backend-api\\.(.*)"
```

**Por que eram redundantes:**
O middleware genérico `www-to-non-www` já cobre TODOS os casos:
```
www.example.com           → example.com            ✅
www.api.example.com       → api.example.com        ✅
www.backend-api.example.com → backend-api.example.com ✅
```

**Solução aplicada:**
- Removidos 2 middlewares específicos (6 linhas)
- Todos os routers WWW agora usam o middleware universal `www-to-non-www`

**Total:** 6 linhas removidas, configuração mais simples e manutenível

### 3. ❌ Router WWW-HTTP duplicado (REMOVIDO)

**Problema anterior:**
- Router `qd-frontend-www-http` duplicava funcionalidade do `http-catchall`
- Regras específicas de ACME em cada router WWW eram redundantes

**Solução aplicada:**
- Removido router `qd-frontend-www-http`
- Routers WWW operam APENAS em `websecure`
- O fluxo correto é: HTTP→HTTPS (via catchall) → WWW→non-WWW (via router específico)

### 3. ❌ Comentários obsoletos (REMOVIDO)

**Linhas removidas:**
```yaml
# - "traefik.http.routers.querido-diario-api.middlewares=api-strip-prefix,compression"
# - "traefik.http.routers.querido-diario-api-path.middlewares=api-redirect"
```

### 4. ❌ Middlewares WWW específicos por serviço (REMOVIDO)

**Problema anterior:**
- `www-api-to-api`: Regex `^https?://www\\.api\\.(.*)`
- `www-backend-api-to-backend-api`: Regex `^https?://www\\.backend-api\\.(.*)`

**Por que eram redundantes:**
O middleware genérico `www-to-non-www` com regex `^https?://www\\.(.*)` já captura todos os casos:
- `www.example.com` → captura `example.com`
- `www.api.example.com` → captura `api.example.com`
- `www.backend-api.example.com` → captura `backend-api.example.com`

**Solução:**
- Removidos middlewares `www-api-to-api` e `www-backend-api-to-backend-api`
- Todos os routers WWW agora usam apenas `www-to-non-www`
- **Resultado:** 6 linhas de configuração eliminadas

## Prioridades dos Routers

| Router | Priority | Motivo |
|--------|----------|--------|
| acme-challenge | 999 | Mais alta - deve processar ACME antes de qualquer outro |
| API/Backend WWW redirects | 200 | Alta - redirecionamentos específicos de serviços |
| API path prefix | 100 | Média - roteamento específico de API |
| Frontend WWW redirect | 10 | Baixa - redirecionamento geral |
| Frontend main | 1 | Mais baixa - catchall para domínio principal |
| http-catchall | 1 | Mais baixa - catchall geral |

## Configurações Importantes no DNS

Para que esta configuração funcione corretamente:

1. **Subdomínios multi-nível (www.\*, api.\*, etc.)** devem usar:
   - DNS-only (gray cloud) no Cloudflare
   - SSL gerenciado pelo Traefik via Let's Encrypt
   - Porta 80 (HTTP) acessível para ACME challenges

2. **Domínios principais** podem usar:
   - Cloudflare Proxy (orange cloud) ou DNS-only (gray cloud)
   - Se usar Cloudflare Proxy, configurar SSL como "Full" ou "Full (strict)"

## Testando a Configuração

### Teste 1: ACME Challenge
```bash
curl -I http://www.example.com/.well-known/acme-challenge/test
# Esperado: 200 ou 404, mas NÃO 301/302
```

### Teste 2: HTTP → HTTPS
```bash
curl -I http://example.com/
# Esperado: 301 Location: https://example.com/
```

### Teste 3: WWW → Non-WWW
```bash
curl -I https://www.example.com/
# Esperado: 301 Location: https://example.com/
```

### Teste 4: Combinado (HTTP + WWW)
```bash
curl -I http://www.example.com/
# Esperado: Dois redirects em sequência
# 1. 301 → https://www.example.com/
# 2. 301 → https://example.com/
```

## Troubleshooting

### Certificado não é gerado
- Verifique se a porta 80 está acessível externamente
- Confirme que não há firewall bloqueando HTTP
- Verifique os logs do Traefik: `docker compose logs traefik | grep acme`

### Redirect loop
- Verifique se o Cloudflare não está configurado como "Flexible SSL"
- Confirme as prioridades dos routers
- Verifique se há middlewares duplicados

### WWW não redireciona
- Confirme que o certificado foi gerado para www.domain
- Verifique os logs: `docker compose logs traefik | grep www`
- Teste diretamente no servidor (bypass Cloudflare): `curl -I -H "Host: www.example.com" http://IP_DO_SERVIDOR/`

## Referências

- [Traefik v3 Documentation](https://doc.traefik.io/traefik/)
- [Let's Encrypt HTTP-01 Challenge](https://letsencrypt.org/docs/challenge-types/#http-01-challenge)
- [Traefik Routers Priority](https://doc.traefik.io/traefik/routing/routers/#priority)
