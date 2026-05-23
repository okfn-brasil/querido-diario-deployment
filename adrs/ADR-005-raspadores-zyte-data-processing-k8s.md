# ADR-005: Raspadores na Zyte, Data Processing como CronJob k8s

**Data:** 2026-05-22
**Status:** Decidido

## Contexto

O pipeline de coleta de dados tem duas etapas distintas:

1. **Raspagem:** acesso a sites de prefeituras, download de PDFs dos diários
   oficiais, upload para o Storage S3. Feito pelos spiders Scrapy do repositório
   `querido-diario`.
2. **Processamento:** leitura dos PDFs do S3, extração de texto via Apache Tika,
   indexação no OpenSearch. Feito pelo `querido-diario-data-processing`.

A raspagem já rodava na Zyte (Scrapy Cloud) em produção. A questão era onde
rodar o data-processing.

## Decisão

- **Raspadores:** continuam na **Zyte (Scrapy Cloud)**, agendados via GitHub Actions no repositório `querido-diario`. A Zyte oferece proxies inteligentes, gerenciamento de jobs e infraestrutura otimizada para Scrapy — substituir isso traria custo operacional alto sem ganho claro.
- **Data Processing:** roda como **CronJob no cluster k8s**, já dentro da infraestrutura controlada pelo repositório de deployment. Ativo em produção (`suspend: false`), suspenso em dev (`suspend: true`).

Para testes locais dos raspadores sem depender da Zyte: `make run-spider`.

## Alternativas consideradas

| Alternativa | Descartada por |
|---|---|
| Raspadores como CronJob k8s | Perderia proxies inteligentes da Zyte; sites bloqueiam IPs fora do Brasil |
| Data Processing na Zyte | Não é um projeto Scrapy; sem razão para usar Scrapy Cloud |
| Data Processing em GitHub Actions | Sem acesso direto ao cluster k8s (OpenSearch, Tika); jobs longos problemáticos |

## Consequências

- Raspadores e data-processing têm ciclos de release independentes e repositórios separados.
- Falha na Zyte não afeta o cluster k8s e vice-versa.
- Para executar data-processing manualmente no cluster local: `make k8s-local-data-processing`.
- Spiders com `zyte_smartproxy_enabled = True` não funcionam em execução local sem VPN/IP brasileiro.
