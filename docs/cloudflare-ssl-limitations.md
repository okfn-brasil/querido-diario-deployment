# Cloudflare SSL Limitations - Quick Reference

> 📅 **Created**: November 2025
> ⚠️ **Critical for production deployments**

## TL;DR

**Cloudflare Free/Pro cannot issue SSL certificates for multi-level subdomains!**

```
✅ ok.org.br                        → Cloudflare can issue SSL
✅ queridodiario.ok.org.br          → Cloudflare can issue SSL
❌ www.queridodiario.ok.org.br      → Cloudflare CANNOT issue SSL
❌ api.queridodiario.ok.org.br      → Cloudflare CANNOT issue SSL
❌ *.queridodiario.ok.org.br        → Cloudflare CANNOT issue SSL
```

## The Problem

Cloudflare's Universal SSL (included in Free and Pro plans) can only issue certificates for:
- The root domain (e.g., `ok.org.br`)
- First-level subdomains (e.g., `queridodiario.ok.org.br`)

It **cannot** issue certificates for:
- Second-level subdomains (e.g., `www.queridodiario.ok.org.br`)
- Third-level or deeper subdomains (e.g., `test.api.queridodiario.ok.org.br`)

### What Happens When Misconfigured?

If you enable Cloudflare Proxy (orange cloud) for `www.queridodiario.ok.org.br`:

1. **SSL Handshake Failure**:
   ```
   curl: (35) TLS connect error: error:0A000410:SSL routines::ssl/tls alert handshake failure
   ```

2. **Browser Errors**:
   - NET::ERR_SSL_PROTOCOL_ERROR
   - SSL_ERROR_HANDSHAKE_FAILURE_ALERT
   - Connection refused

3. **CORS Failures**:
   ```
   Access to XMLHttpRequest at 'https://queridodiario.ok.org.br/api/cities' 
   from origin 'https://www.queridodiario.ok.org.br' has been blocked by CORS policy
   ```

## The Solution

### DNS Configuration in Cloudflare

| Record Type | Name | Content | Proxy Status | SSL Provider |
|-------------|------|---------|--------------|--------------|
| A | `queridodiario` | `98.87.176.123` | ☁️ **Proxied** (Orange) | Cloudflare Universal SSL |
| A | `www.queridodiario` | `98.87.176.123` | 🔒 **DNS only** (Gray) | Traefik + Let's Encrypt |
| A | `api.queridodiario` | `98.87.176.123` | 🔒 **DNS only** (Gray) | Traefik + Let's Encrypt |
| A | `www.api.queridodiario` | `98.87.176.123` | 🔒 **DNS only** (Gray) | Traefik + Let's Encrypt |
| A | `backend-api.queridodiario` | `98.87.176.123` | 🔒 **DNS only** (Gray) | Traefik + Let's Encrypt |
| A | `www.backend-api.queridodiario` | `98.87.176.123` | 🔒 **DNS only** (Gray) | Traefik + Let's Encrypt |

### How to Configure in Cloudflare Dashboard

1. **Go to DNS Settings** for `ok.org.br` domain
2. **Find each A record**
3. **Click the cloud icon** to toggle:
   - **Orange cloud** = Proxied (Cloudflare handles SSL)
   - **Gray cloud** = DNS only (Traffic goes directly to your server)

### Visual Guide

```
Before (BROKEN):
www.queridodiario.ok.org.br → Cloudflare Proxy → ❌ SSL Handshake Failure

After (WORKING):
www.queridodiario.ok.org.br → DNS Resolution → Server → Traefik → ✅ Let's Encrypt SSL
```

## Verification

### Test if DNS is configured correctly:

```bash
# Check DNS resolution
dig +short www.queridodiario.ok.org.br

# Should return your server IP directly (e.g., 98.87.176.123)
# NOT Cloudflare IPs (172.*, 104.*, 2606:*)

# Test SSL handshake
curl -I https://www.queridodiario.ok.org.br/

# Should return HTTP/2 30x (redirect to non-www)
# NOT "SSL handshake failure"
```

### Test if Traefik is issuing certificates:

```bash
# Check certificate on www subdomain
echo | openssl s_client -connect www.queridodiario.ok.org.br:443 -servername www.queridodiario.ok.org.br 2>&1 | grep -E "(subject|issuer)"

# Should show:
# subject=CN=www.queridodiario.ok.org.br
# issuer=C=US; O=Let's Encrypt; CN=...
```

## Common Mistakes

### ❌ Mistake 1: All subdomains proxied through Cloudflare

```
queridodiario     ☁️ Proxied
www.queridodiario ☁️ Proxied  ← WRONG! SSL will fail
api.queridodiario ☁️ Proxied  ← WRONG! SSL will fail
```

**Result**: SSL handshake failures, CORS errors, site doesn't load

### ❌ Mistake 2: Using Cloudflare Page Rules for www redirect

```
Page Rule: www.queridodiario.ok.org.br/* → queridodiario.ok.org.br/$1
```

**Problem**: Page Rule runs AFTER SSL handshake, so if SSL fails, redirect never happens!

**Solution**: Use Traefik redirect (already configured in `docker-compose.yml`)

### ❌ Mistake 3: Forgetting to configure api subdomain

```
api.queridodiario ☁️ Proxied  ← WRONG!
```

**Result**: API returns Cloudflare SSL certificate, CORS fails

## Reference Links

- [Cloudflare SSL Coverage](https://developers.cloudflare.com/ssl/edge-certificates/universal-ssl/limitations/)
- [Let's Encrypt with Traefik](https://doc.traefik.io/traefik/https/acme/)
- [Querido Diário Traefik Setup](./traefik-setup.md)
- [CORS Fix Documentation](../CORS-FIX-CLOUDFLARE.md)

## Cloudflare Plans Comparison

| Plan | SSL Coverage |
|------|--------------|
| **Free** | Root domain + 1st level subdomains |
| **Pro** | Root domain + 1st level subdomains |
| **Business** | Root domain + 1st level subdomains + **wildcard** |
| **Enterprise** | Custom SSL certificates supported |

**Note**: Even Business plan uses wildcard certificate (e.g., `*.queridodiario.ok.org.br`), which still doesn't cover second-level like `www.queridodiario.ok.org.br`.

## Quick Checklist

Before deploying to production:

- [ ] Main domain (`queridodiario.ok.org.br`) is **Proxied** (orange cloud)
- [ ] WWW subdomain (`www.queridodiario.ok.org.br`) is **DNS only** (gray cloud)
- [ ] API subdomain (`api.queridodiario.ok.org.br`) is **DNS only** (gray cloud)
- [ ] WWW API subdomain (`www.api.queridodiario.ok.org.br`) is **DNS only** (gray cloud)
- [ ] Backend API subdomain (`backend-api.queridodiario.ok.org.br`) is **DNS only** (gray cloud)
- [ ] WWW Backend API subdomain (`www.backend-api.queridodiario.ok.org.br`) is **DNS only** (gray cloud)
- [ ] All DNS records point to your server IP
- [ ] Traefik is configured with Let's Encrypt (already in `docker-compose.yml`)
- [ ] Cloudflare Page Rule redirects `/api/*` to API subdomain (for main domain only)
- [ ] Test SSL handshake on all subdomains (including www variants)
- [ ] Test CORS from www subdomain
- [ ] Test API calls from frontend
- [ ] Test www.api.domain redirects to api.domain
- [ ] Test www.backend-api.domain redirects to backend-api.domain

## Troubleshooting

### Issue: "SSL handshake failure" on www subdomain

**Cause**: www subdomain is proxied through Cloudflare (orange cloud)

**Fix**: Change to DNS only (gray cloud) in Cloudflare DNS settings

### Issue: "CORS blocked" when accessing from www

**Cause**: Either SSL failure (see above) or CORS headers not configured

**Fix**: 
1. Ensure www is DNS only (gray cloud)
2. Verify Traefik CORS middleware includes `www.${DOMAIN}` in allowed origins
3. Check `docker-compose.yml` line ~497 for CORS configuration

### Issue: API subdomain returns HTML instead of JSON

**Cause**: API subdomain is proxied through Cloudflare, which routes to Netlify

**Fix**: Change API subdomain to DNS only (gray cloud)

### Issue: Let's Encrypt rate limit exceeded

**Cause**: Too many certificate requests (5 per week per domain)

**Fix**:
1. Wait 7 days for rate limit reset
2. Use staging environment for testing
3. Ensure DNS is configured correctly before deploying

### Issue: ACME certificate error 403 unauthorized

**Error message:**
```
unable to obtain ACME certificate for domains error="unable to generate a certificate for the domains [www.api.queridodiario.ok.org.br]: error: one or more domains had a problem:
[www.api.queridodiario.ok.org.br] invalid authorization: acme: error: 403 :: urn:ietf:params:acme:error:unauthorized :: Invalid response from https://www.api.queridodiario.ok.org.br/.well-known/acme-challenge/...
```

**Cause**: The redirect middleware is redirecting ACME challenge requests, preventing Let's Encrypt from verifying domain ownership.

**Fix**: The routers must exclude `/.well-known/acme-challenge/` from redirects:

```yaml
# CORRECT - Excludes ACME challenge path
- "traefik.http.routers.frontend-www-redirect.rule=Host(`www.${DOMAIN}`) && !PathPrefix(`/.well-known/acme-challenge/`)"

# WRONG - Redirects everything including ACME challenges
- "traefik.http.routers.frontend-www-redirect.rule=Host(`www.${DOMAIN}`)"
```

This is already fixed in `docker-compose.yml` (November 2025).

## Additional Notes

- This limitation applies to **all** Cloudflare Free/Pro users
- **Not** a bug or misconfiguration on our side
- **Not** fixable with Cloudflare settings alone
- **Solution**: Hybrid approach (Cloudflare for main, Traefik for subdomains)
- Architecture is already implemented in `docker-compose.yml`
- Just needs correct DNS configuration in Cloudflare dashboard
