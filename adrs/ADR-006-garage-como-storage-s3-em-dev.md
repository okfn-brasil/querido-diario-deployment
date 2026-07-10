# ADR-006: Garage como S3-compatível em desenvolvimento

**Data:** 2026-05-22
**Status:** Decidido

## Contexto

Em desenvolvimento local (kind), os serviços precisam de um storage
S3-compatível para que raspadores e data-processing possam armazenar e ler
arquivos de diários, sem depender de credenciais AWS reais. O storage precisava
rodar dentro do cluster kind como Deployment.

## Decisão

Usar **[Garage v2](https://garagehq.deuxfleurs.fr/)** como storage S3-compatível
no ambiente dev. Garage é leve, sem dependências externas e tem API S3
compatível o suficiente para os casos de uso do projeto.

Um `garage-webui` é provisionado junto para inspeção visual dos buckets durante
desenvolvimento.

Manifestos em `k8s/overlays/dev/infra/garage.yaml` e
`k8s/overlays/dev/infra/garage-webui.yaml`.

Em produção, o storage é **AWS S3** (externo ao cluster), configurado via
secret.

## Alternativas consideradas

| Alternativa | Descartada por |
|---|---|
| AWS S3 real em dev | Requer credenciais AWS; custo e dependência de conectividade externa |
| Localstack | Mais pesado; emula muitos serviços AWS além do S3, desnecessários aqui |

## Consequências

- Credenciais de acesso ao Garage em dev são fixas e não-sensíveis (definidas no overlay dev).
- A API S3 do Garage cobre os casos de uso do projeto (PUT, GET, list), mas pode divergir em comportamentos de borda da AWS S3.
- Bucket e key são criados automaticamente pelo próprio Garage na inicialização (flags `--single-node --default-bucket`), sem necessidade de Job de inicialização separado.
