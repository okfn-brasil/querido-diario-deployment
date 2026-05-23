# ADR-004: Traefik como ingress controller

**Data:** 2026-05-22
**Status:** Decidido

## Contexto

O cluster k8s precisa de um ingress controller para rotear tráfego externo para
os serviços, gerenciar SSL e aplicar middlewares (CORS, rate limiting, security
headers). A plataforma já usava Traefik no setup anterior via Docker Compose,
com configuração de middlewares e roteamento bem estabelecida.

## Decisão

Usar **Traefik v3** instalado via **Helm** como DaemonSet com `hostPort` 80/443.
Roteamento via CRDs `IngressRoute` e `Middleware`.

Configuração base em `k8s/local/traefik-values.yaml`. Middlewares compartilhados
em `k8s/base/traefik-middlewares.yaml`.

## Alternativas consideradas

| Alternativa | Descartada por |
|---|---|
| NGINX Ingress Controller | Configuração de middlewares mais verbosa; Traefik já conhecida pela equipe |
| Ingress padrão do k8s | Sem suporte nativo a CRDs de middleware; precisa de anotações específicas de implementação |
| Istio | Complexidade muito alta para o tamanho do projeto |
| Gateway API (padrão k8s) | Analisado separadamente abaixo |

## Análise: Gateway API vs. Traefik IngressRoute

A **Gateway API** é a sucessora oficial do recurso `Ingress` do Kubernetes, com status GA
desde a v1.28 (setembro 2023). Seus tipos core (`GatewayClass`, `Gateway`, `HTTPRoute`)
são mantidos pelo SIG-Network e representam a direção oficial de longo prazo para
roteamento em k8s.

### Vantagens do Gateway API

- **Portabilidade**: `HTTPRoute` é um recurso padrão k8s. Trocar de Traefik para outro
  controller (Envoy Gateway, nginx, etc.) não exige reescrever as rotas.
- **Separação de papéis**: `Gateway` (infra/cluster-admin) e `HTTPRoute` (equipe de app)
  são objetos distintos — facilita governança em times maiores.
- **Recursos avançados nativos**: traffic splitting (canary), header matching/rewrite,
  port-level TLS — sem depender de CRDs do controller.
- **Traefik v3 suporta Gateway API**: é possível usar `HTTPRoute` com Traefik hoje, sem
  trocar de controller.

### Por que Gateway API não é a melhor escolha aqui

O ponto crítico está nos **middlewares**. A ADR atual usa `Middleware` CRDs do Traefik
para CORS, rate-limiting e security headers — funcionalidades sem equivalente nativo no
Gateway API. As opções para contornar isso são:

1. **`ExtensionRef` apontando para `Middleware` Traefik**: o `HTTPRoute` referencia o
   CRD proprietário do Traefik. Resultado: perde a portabilidade (o principal benefício
   do Gateway API), mas ganha a verbosidade extra de dois objetos por rota.
2. **Filters nativos do Gateway API**: cobre apenas header manipulation simples. Não
   cobre rate-limiting nem security headers — precisaria de soluções externas (ex.:
   policy controllers separados).

Além disso, para este projeto:

- **Portabilidade não é prioridade**: não há plano de trocar Traefik por outro controller.
- **Time pequeno**: a separação de papéis cluster-admin/dev não agrega valor real.
- **IngressRoute já resolve o problema**: os objetivos de declaratividade e versionamento
  no git já estão sendo atingidos com os CRDs atuais.

### Quando reavaliar

Considerar migração para Gateway API se:
- O projeto adotar multi-tenancy com times separados gerenciando rotas;
- Houver necessidade de traffic splitting (canary/blue-green) para deploys graduais;
- A dependência em `Middleware` CRDs for reduzida ou eliminada.

**Conclusão**: manter `IngressRoute` + `Middleware` do Traefik. A decisão pode ser
revisada se qualquer condição acima mudar.

## Consequências

- Roteamento e middlewares declarados como recursos k8s (CRDs), versionados junto com os manifestos.
- Lock-in nos CRDs do Traefik (`IngressRoute`, `Middleware`) — aceitável dado que não há plano de troca de controller.
- Terminação SSL via Let's Encrypt gerenciada pelo próprio Traefik (ver `docs/traefik-setup.md`).
- DaemonSet + hostPort significa que cada nó do cluster expõe as portas 80/443 diretamente — adequado para cluster small/single-node; em cluster multi-node com load balancer externo, ajustar para `LoadBalancer` service.
