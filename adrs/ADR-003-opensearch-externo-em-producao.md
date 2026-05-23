# ADR-003: OpenSearch externo em produção, Docker Compose em VM

**Data:** 2026-05-22
**Status:** Decidido

## Contexto

OpenSearch é necessário para indexação e busca de diários. Diferente dos demais
serviços, tem requisitos de sistema específicos (`vm.max_map_count = 262144` no
host) e consome 2–4 GB de RAM por nó para uso real. Rodar com HA dentro do
cluster k8s exige um operator adicional e recursos significativos.

Em desenvolvimento local (kind), o cluster não tem folga de memória para isso.

## Decisão

- **Produção:** OpenSearch roda em **VM separada via Docker Compose** (`docker-compose.opensearch.yml`), acessível ao cluster k8s via hostname/IP interno. Mantém o cluster k8s focado nos serviços da aplicação.
- **Desenvolvimento (kind):** roda como `Deployment` simples dentro do cluster, com security plugin desabilitado e sem persistência — suficiente para testes locais.

## Alternativas consideradas

| Alternativa | Descartada por |
|---|---|
| OpenSearch dentro do cluster k8s em prod | Requisitos de host (`vm.max_map_count`) complicam nodes k8s gerenciados; overhead operacional do operator e consumo de recursos múltiplicado por n-cópias |
| OpenSearch Operator | Complexidade desnecessária para single-node; serviço externo é mais simples de operar |
| Serviço gerenciado externo (AWS OpenSearch Service, Bonsai) | Válido no futuro; por ora, VM própria tem custo menor e controle total |

## Consequências

- Backup do OpenSearch é responsabilidade da VM (snapshot de volume ou snapshot API do OpenSearch).
- Atualização de versão do OpenSearch é manual (pull da nova imagem + restart).
- A VM do OpenSearch precisa ter `vm.max_map_count=262144` configurado permanentemente em `/etc/sysctl.conf`.
- OpenSearch fica exposto apenas em `127.0.0.1:9200` na VM; acesso do cluster via rede interna.
