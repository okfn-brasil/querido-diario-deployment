# Querido Diário — Deployment

Repositório de infraestrutura da plataforma [Querido Diário](https://queridodiario.ok.org.br), com suporte a dois modelos de deploy: **Docker Compose** (legado/simples) e **Kubernetes** (produção).

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
| OpenSearch | — | — |
| Storage (S3) | Garage / AWS S3 | — |

## Estrutura do repositório

```
querido-diario-deployment/
├── docker-compose.yml           # Serviços da aplicação
├── docker-compose.traefik.yml   # Traefik (reverse proxy + SSL)
├── docker-compose.dbs.yml       # Postgres em containers (opcional)
├── docker-compose.dev.yml       # Overrides para desenvolvimento local
├── .env                         # Variáveis de ambiente (não versionar valores reais)
├── Makefile                     # Todos os comandos (make help)
├── k8s/                         # Manifestos Kubernetes — ver k8s/README.md
│   ├── base/                    # Recursos base (compartilhados entre overlays)
│   ├── overlays/
│   │   ├── dev/                 # Overlay de desenvolvimento local (kind)
│   │   └── production/          # Overlay de produção
│   └── local/                   # Scripts do cluster kind local
├── docs/                        # Documentação técnica adicional
└── init-scripts/                # Scripts de inicialização de bancos
```

## Início rápido

```bash
make help   # lista todos os comandos disponíveis
```

---

## Docker Compose

Modo de deploy via Docker Compose. Adequado para ambientes simples ou máquinas sem k8s.

### Desenvolvimento local

```bash
cp .env.example .env   # configure as variáveis
make dev               # sobe todos os serviços localmente
```

Serviços disponíveis em desenvolvimento:

| URL | Serviço |
|---|---|
| http://api.queridodiario.local | API |
| http://backend-api.queridodiario.local | Backend |
| http://queridodiario.local | Frontend (se rodando separado) |

### Produção (Docker Compose)

```bash
# Edite .env com as variáveis de produção
make deploy-all        # sobe Traefik + serviços
```

Infraestrutura necessária (externa ao compose):
- PostgreSQL (3 bancos: `queridodiario`, `backend`, `companies`)
- OpenSearch
- Storage S3-compatível (AWS S3, Garage, etc.)
- DNS apontando para o servidor

### Comandos úteis (Docker Compose)

```bash
make validate          # valida sintaxe dos compose files
make check-env         # verifica variáveis obrigatórias no .env
make logs              # logs de todos os serviços
make status            # status dos containers
make restart           # reinicia os serviços
make shell-api         # shell no container da API
make shell-backend     # shell no container do Backend
```

---

## Kubernetes

Deploy completo em Kubernetes via Kustomize. Recomendado para produção.

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

### Produção (Kubernetes)

```bash
make k8s-diff-prod    # ver o que será aplicado (dry-run)
make k8s-apply-prod   # aplicar no cluster
```

---

## Licença

Este projeto está licenciado sob os termos definidos no arquivo [LICENSE.md](LICENSE.md).
