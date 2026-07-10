# ADR-001: Kubernetes como plataforma de deploy principal

**Data:** 2026-05-22
**Status:** Decidido

## Contexto

O deploy histórico da plataforma usava Docker Compose, com diferentes compose
files para cada camada (serviços, traefik, bancos, dev). Com o crescimento da
plataforma e a necessidade de gerenciar múltiplos serviços com réplicas, rolling
updates, health checks e configuração declarativa, o Docker Compose se tornou
limitante operacionalmente. Ademais, surgiu a oportunidade de rodarmos o projeto
num ambiente de K8s sem ter que ter o trabalho operacional de manter um cluster
de K8s, podendo simplesmente tirar vantagem das características de auto-scaling
do ambiente.

## Decisão

Migrar completamente para **Kubernetes via Kustomize**. Docker Compose é
removido do repositório (o OpenSearch chegou a ter uma fase intermediária em
VM via `docker-compose.opensearch.yml`, ver ADR-003 — superado pelo ADR-008
antes mesmo dessa VM ser criada).

Estrutura adotada:

- `k8s/base/` — recursos compartilhados entre ambientes
- `k8s/overlays/production/` — configuração de produção
- `k8s/overlays/dev/` — configuração de desenvolvimento local (kind)
- `k8s/local/` — scripts para cluster kind local

## Alternativas consideradas

| Alternativa | Descartada por |
|---|---|
| Manter Docker Compose para dev, k8s para prod | Dois modelos de deploy divergem com o tempo; bugs aparecem só em prod |
| Docker Swarm | Ecosistema menor, menos operadores disponíveis, sem vantagem clara |
| Nomad | Curva de aprendizado sem ganho relevante para o tamanho do projeto |

## Consequências

- Desenvolvimento local requer `kind` + `kubectl` + `helm` (setup via `make k8s-local-up`)
- Configuração declarativa e versionada para todos os ambientes
- Acesso a operators (CloudNativePG, potencialmente OpenSearch Operator futuramente)
- OpenSearch continua em VM separada via Docker Compose por razões de recursos (ver ADR-003)
