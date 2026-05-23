# ADR-007: Terminação SSL

**Data:** 2026-05-22
**Status:** Em avaliação

## Contexto

A plataforma expõe três subdomínios em produção:

- `queridodiario.ok.org.br` — frontend
- `api.queridodiario.ok.org.br` — API
- `backend-api.queridodiario.ok.org.br` — backend Django

O DNS é gerenciado pelo Cloudflare. O ingress controller é o Traefik (ver ADR-004).

**Complicador:** `api.queridodiario.ok.org.br` e
`backend-api.queridodiario.ok.org.br` são subdomínios de segundo nível em
relação ao domínio registrado `ok.org.br`. O Cloudflare Universal SSL (Free/Pro)
só cobre até o primeiro nível (`queridodiario.ok.org.br`), não subdomínios mais
profundos.

## Opções

### Opção A — Let's Encrypt via Traefik (ACME HTTP-01)

O Traefik obtém e renova certificados Let's Encrypt automaticamente para todos
os domínios. Os subdomínios `api.*` e `backend-api.*` ficam em **DNS-only**
(gray cloud) no Cloudflare, apontando diretamente para o cluster. O domínio
principal pode usar Cloudflare Proxy.

**Vantagens:**

- Gratuito
- Totalmente automatizado (renovação automática)
- Já está implementado e documentado (`docs/TRAEFIK_SSL_CONFIG.md`, `docs/cloudflare-ssl-limitations.md`)

**Desvantagens:**

- Requer porta 80 aberta no cluster para ACME HTTP-01 challenge
- Subdomínios fora do Cloudflare Proxy perdem proteção DDoS e CDN para essas rotas
- Configuração mais complexa (routers de prioridade, ACME exclusion, DNS split)

---

### Opção B — Cloudflare Origin CA + Full (Strict)

Emite-se um certificado de CA do próprio Cloudflare (gratuito, via dashboard) e
instala-se no Traefik. Cloudflare termina SSL no edge e valida o certificado de
origem. **Todos** os subdomínios ficam em Cloudflare Proxy (orange cloud). O
Traefik não precisa mais do ACME.

O certificado Origin CA é válido por até 15 anos e não precisa de renovação
automática. É confiado apenas pelo Cloudflare (não por browsers diretamente), o
que é suficiente já que todo tráfego passa pelo proxy.

**Vantagens:**

- Gratuito
- Elimina ACME e porta 80 para desafios
- Todos os subdomínios ficam sob Cloudflare Proxy (DDoS, CDN, analytics)
- Configuração mais simples no Traefik (um único certificado estático)
- Certificado de 15 anos — sem preocupação com renovação

**Desvantagens:**

- Exige que **todo** tráfego passe pela Cloudflare (bypass direto ao IP do cluster expõe HTTP ou certificado não-público)
- Requer configuração manual inicial do certificado Origin CA e montagem como Secret k8s
- Se a Cloudflare tiver indisponibilidade, o serviço fica inacessível mesmo que o cluster esteja saudável

---

### Opção C — Cloudflare Advanced Certificate Manager (ACM)

Contrata-se o Cloudflare ACM (~$10/mês) que emite um wildcard
`*.queridodiario.ok.org.br`. Cloudflare termina SSL no edge. O Traefik recebe
HTTP simples (ou HTTPS com Origin CA). Todos os subdomínios ficam sob Cloudflare
Proxy.

**Vantagens:**

- Configuração mais simples — wildcard cobre qualquer subdomínio futuro automaticamente
- Todos os subdomínios sob Cloudflare Proxy

**Desvantagens:**

- Custo: ~$10/mês por domínio
- Dependência da Cloudflare (mesma da Opção B)
- Pouco ganho sobre a Opção B considerando que os domínios são fixos e conhecidos

---

## Comparativo

| Critério | A — Let's Encrypt | B — Origin CA | C — ACM |
|---|---|---|---|
| Custo | Gratuito | Gratuito | ~$10/mês |
| Renovação | Automática (90 dias) | Manual (15 anos) | Automática |
| Complexidade de config | Alta | Baixa | Baixa |
| Porta 80 necessária | Sim | Não | Não |
| Todos os subdomínios no proxy | Não | Sim | Sim |
| Dependência da Cloudflare | Parcial | Total | Total |
| Já implementado | Sim | Não | Não |

## Decisão

_A definir._

## Critérios para a decisão

- Disposição para aceitar dependência total da Cloudflare para disponibilidade
- Valor da proteção DDoS/CDN da Cloudflare nos subdomínios de API e backend
- Preferência por simplicidade operacional vs. controle total sobre certificados
