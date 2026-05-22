# Querido Diário — Deployment

Repositório de infraestrutura da plataforma [Querido Diário](https://queridodiario.ok.org.br). O deploy é feito em **Kubernetes** via Kustomize. OpenSearch roda em VM separada via Docker Compose.

## Visão geral da plataforma

| Serviço | Tecnologia | Repositório |
|---|---|---|
| Frontend | Angular | [querido-diario-frontend](https://github.com/okfn-brasil/querido-diario-frontend) |
| API | FastAPI | [querido-diario-api](https://github.com/okfn-brasil/querido-diario-api) |
| Backend | Django | [querido-diario-backend](https://github.com/okfn-brasil/querido-diario-backend) |
| Data Processing | Python/Scrapy | [querido-diario](https://github.com/okfn-brasil/querido-diario) |
| Apache Tika | Java | — |
| Redis | — | — |
| PostgreSQL | CloudNativePG | — |
| OpenSearch | Docker Compose (VM) | — |
| Storage (S3) | Garage (dev) / AWS S3 (prod) | — |

## Estrutura do repositório

```
querido-diario-deployment/
├── Makefile                         # Todos os comandos (make help)
├── docker-compose.opensearch.yml    # OpenSearch em VM de produção
├── k8s/                             # Manifestos Kubernetes — ver k8s/README.md
│   ├── base/                        # Recursos base (compartilhados entre overlays)
│   ├── overlays/
│   │   ├── dev/                     # Overlay de desenvolvimento local (kind)
│   │   └── production/              # Overlay de produção
│   └── local/                       # Scripts do cluster kind local
└── docs/                            # Documentação técnica
```

## Início rápido

```bash
make help   # lista todos os comandos disponíveis
```

---

## Kubernetes

Deploy completo em Kubernetes via Kustomize.

Ver **[k8s/README.md](k8s/README.md)** para o guia completo.

### Desenvolvimento local (kind)

```bash
make k8s-local-up                # cria cluster kind + sobe tudo (~10min no primeiro run)
make k8s-local-hosts             # adiciona entradas ao /etc/hosts (requer sudo)
make k8s-local-frontend-build    # builda e carrega a imagem do frontend
```

URLs disponíveis após o setup:

| URL | Serviço |
|---|---|
| http://queridodiario.local | Frontend |
| http://api.queridodiario.local | API |
| http://backend-api.queridodiario.local | Backend |
| `make k8s-local-garage-ui` → http://localhost:3909 | Garage Web UI |

### Produção

```bash
make k8s-diff-prod    # ver o que será aplicado
make k8s-apply-prod   # aplicar no cluster
```

---

## OpenSearch (VM)

Em produção, o OpenSearch roda numa VM separada via Docker Compose:

```bash
# Pré-requisito no host (uma vez):
sudo sysctl -w vm.max_map_count=262144
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf

# Subir:
OPENSEARCH_PASSWORD=<senha> make deploy-opensearch

# Parar:
make down-opensearch
```

O OpenSearch fica acessível apenas localmente (`127.0.0.1:9200`). O cluster k8s acessa via hostname/IP da VM.

---

## Build local de imagens

Targets para build local usando cache remoto do GHCR:

```bash
make build-api                   # ghcr.io/okfn-brasil/querido-diario-api:local
make build-backend               # ghcr.io/okfn-brasil/querido-diario-backend:local
make build-data-processing-base  # base de deps Python (rebuildar quando requirements.txt mudar)
make build-data-processing       # ghcr.io/okfn-brasil/querido-diario-data-processing:local
make build-tika                  # ghcr.io/okfn-brasil/querido-diario-data-processing/apache-tika:local
make build-frontend              # ghcr.io/okfn-brasil/querido-diario-frontend:local

make build-all                   # todas as imagens acima
```

---

## Raspadores (execução local)

Os raspadores rodam em produção na **Zyte (Scrapy Cloud)**. Para testes locais:

```bash
make spider-setup                                     # uma vez: cria venv e instala deps
make spider-list                                      # lista todos os spiders
make run-spider SPIDER=sp_campinas START=2025-01-01   # executa um spider
```

Por padrão salva arquivos em `../querido-diario/data_collection/data/` e metadados em SQLite local. Para conectar ao Garage/PostgreSQL do cluster kind, configure `../querido-diario/data_collection/.local.env`.

---

## Licença

Este projeto está licenciado sob os termos definidos no arquivo [LICENSE.md](LICENSE.md).
