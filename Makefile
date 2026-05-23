# Querido Diário Deployment Makefile
# ===================================

.PHONY: help \
        deploy-opensearch down-opensearch \
        build-api build-backend \
        build-data-processing-base build-data-processing build-tika \
        build-frontend build-all \
        spider-setup spider-list run-spider \
        k8s-build-base k8s-build-prod k8s-build-dev \
        k8s-apply-prod k8s-apply-dev k8s-diff-prod k8s-diff-dev \
        k8s-local-up k8s-local-down k8s-local-status k8s-local-hosts \
        k8s-local-garage-ui k8s-local-data-processing \
        k8s-local-frontend-build

REGISTRY = ghcr.io/okfn-brasil

QD_DIR               ?= ../querido-diario
API_DIR              ?= ../querido-diario-api
BACKEND_DIR          ?= ../querido-diario-backend/app
DATA_PROCESSING_DIR  ?= ../querido-diario-data-processing
FRONTEND_DIR         ?= ../querido-diario-frontend

FRONTEND_IMAGE       = $(REGISTRY)/querido-diario-frontend

COMPOSE_OPENSEARCH = docker compose -f docker-compose.opensearch.yml

help: ## Mostra esta mensagem de ajuda
	@echo "Comandos disponíveis:"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-30s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Inicio rapido:"
	@echo "  Kubernetes (local) : make k8s-local-up"
	@echo "  Kubernetes (prod)  : make k8s-apply-prod"
	@echo "  OpenSearch (VM)    : make deploy-opensearch"
	@echo ""
	@echo "Kubernetes local (kind):"
	@echo "  make k8s-local-up                          # cria cluster kind + sobe ambiente dev"
	@echo "  make k8s-local-down                        # destroi o cluster kind"
	@echo "  make k8s-local-status                      # status dos pods"
	@echo "  make k8s-local-hosts                       # adiciona entradas ao /etc/hosts (sudo)"
	@echo "  make k8s-local-garage-ui                   # port-forward Garage UI -> localhost:3909"
	@echo "  make k8s-local-data-processing             # executa data-processing manualmente"
	@echo ""
	@echo "Kubernetes (kustomize):"
	@echo "  make k8s-build-dev                         # dry-run overlay dev"
	@echo "  make k8s-build-prod                        # dry-run overlay producao"
	@echo "  make k8s-apply-dev                         # aplica overlay dev no cluster atual"
	@echo "  make k8s-apply-prod                        # aplica overlay producao no cluster atual"
	@echo "  make k8s-diff-dev                          # diff entre cluster e overlay dev"
	@echo "  make k8s-diff-prod                         # diff entre cluster e overlay producao"
	@echo ""
	@echo "Raspadores (execução local):"
	@echo "  make spider-setup                          # cria venv e instala deps (uma vez)"
	@echo "  make spider-list                           # lista todos os spiders"
	@echo "  make run-spider SPIDER=<nome>              # executa um spider"
	@echo "  make run-spider SPIDER=<nome> START=YYYY-MM-DD END=YYYY-MM-DD"
	@echo ""
	@echo "Build local (com cache remoto):"
	@echo "  make build-api                # API"
	@echo "  make build-backend            # Backend/Celery"
	@echo "  make build-data-processing-base  # base do Data Processing (deps Python)"
	@echo "  make build-data-processing    # Data Processing"
	@echo "  make build-tika               # Apache Tika"
	@echo "  make build-frontend           # Frontend"
	@echo "  make build-all                # todas as imagens acima"
	@echo ""
	@echo "Variaveis:"
	@echo "  QD_DIR=<path>                (padrao: ../querido-diario)"
	@echo "  API_DIR=<path>               (padrao: ../querido-diario-api)"
	@echo "  BACKEND_DIR=<path>           (padrao: ../querido-diario-backend/app)"
	@echo "  DATA_PROCESSING_DIR=<path>   (padrao: ../querido-diario-data-processing)"
	@echo "  FRONTEND_DIR=<path>          (padrao: ../querido-diario-frontend)"
	@echo "  SPIDER=<nome>                nome do spider a executar"
	@echo "  START=YYYY-MM-DD             data de inicio do raspador (opcional)"
	@echo "  END=YYYY-MM-DD               data de fim do raspador (opcional)"

# --- OpenSearch (VM de produção) ---

deploy-opensearch: ## Sobe o OpenSearch na VM de produção
	$(COMPOSE_OPENSEARCH) up -d

down-opensearch: ## Para o OpenSearch
	$(COMPOSE_OPENSEARCH) down

# --- Raspadores (execução local, produção permanece na Zyte) ---

spider-setup: ## Cria venv e instala dependências dos raspadores (executar uma vez)
	python3 -m venv $(QD_DIR)/data_collection/.venv
	$(QD_DIR)/data_collection/.venv/bin/pip install --upgrade pip
	$(QD_DIR)/data_collection/.venv/bin/pip install -r $(QD_DIR)/data_collection/requirements.txt

spider-list: ## Lista todos os raspadores disponíveis
	@test -f $(QD_DIR)/data_collection/.venv/bin/scrapy || \
	    (echo "ERRO: venv nao encontrado — execute: make spider-setup"; exit 1)
	cd $(QD_DIR)/data_collection && .venv/bin/scrapy list

run-spider: ## Executa um raspador localmente (SPIDER=nome [START=YYYY-MM-DD] [END=YYYY-MM-DD])
	@test -n "$(SPIDER)" || \
	    (echo "ERRO: defina SPIDER=<nome>   ex: make run-spider SPIDER=sp_campinas START=2025-01-01"; exit 1)
	@test -f $(QD_DIR)/data_collection/.venv/bin/scrapy || \
	    (echo "ERRO: venv nao encontrado — execute: make spider-setup"; exit 1)
	cd $(QD_DIR)/data_collection && \
	    if [ -f .local.env ]; then set -a; . ./.local.env; set +a; fi && \
	    .venv/bin/scrapy crawl $(SPIDER) \
	    $(if $(START),-a start=$(START)) \
	    $(if $(END),-a end=$(END))

# --- Build local (com cache remoto do registry) ---

build-api: ## Build local da imagem da API usando cache do registry
	docker buildx build \
	    --cache-from type=registry,ref=$(REGISTRY)/querido-diario-api:latest \
	    --load \
	    -t $(REGISTRY)/querido-diario-api:local \
	    $(API_DIR)

build-backend: ## Build local da imagem do Backend usando cache do registry
	docker buildx build \
	    --cache-from type=registry,ref=$(REGISTRY)/querido-diario-backend:latest \
	    --load \
	    -t $(REGISTRY)/querido-diario-backend:local \
	    $(BACKEND_DIR)

build-data-processing-base: ## Build local da imagem base do Data Processing (reconstruir quando requirements.txt mudar)
	docker buildx build \
	    --cache-from type=registry,ref=$(REGISTRY)/querido-diario-data-processing/base:latest \
	    --load \
	    -t $(REGISTRY)/querido-diario-data-processing/base:local \
	    -f $(DATA_PROCESSING_DIR)/Dockerfile.base \
	    $(DATA_PROCESSING_DIR)

build-data-processing: ## Build local da imagem do Data Processing usando cache do registry
	docker buildx build \
	    --cache-from type=registry,ref=$(REGISTRY)/querido-diario-data-processing:latest \
	    --load \
	    -t $(REGISTRY)/querido-diario-data-processing:local \
	    $(DATA_PROCESSING_DIR)

build-tika: ## Build local da imagem do Apache Tika usando cache do registry
	docker buildx build \
	    --cache-from type=registry,ref=$(REGISTRY)/querido-diario-data-processing/apache-tika:latest \
	    --load \
	    -t $(REGISTRY)/querido-diario-data-processing/apache-tika:local \
	    -f $(DATA_PROCESSING_DIR)/Dockerfile_apache_tika \
	    $(DATA_PROCESSING_DIR)

build-frontend: ## Build local da imagem do Frontend usando cache do registry
	docker buildx build \
	    --cache-from type=registry,ref=$(REGISTRY)/querido-diario-frontend:latest \
	    --load \
	    -t $(REGISTRY)/querido-diario-frontend:local \
	    $(FRONTEND_DIR)

build-all: build-api build-backend build-data-processing build-tika build-frontend ## Build local de todas as imagens usando cache do registry

# --- Kubernetes (kustomize) ---

k8s-build-base: ## Gera YAML da base k8s (dry-run, sem aplicar)
	kubectl kustomize k8s/base

k8s-build-prod: ## Gera YAML do overlay de produção (dry-run, sem aplicar)
	kubectl kustomize k8s/overlays/production

k8s-build-dev: ## Gera YAML do overlay de desenvolvimento (dry-run, sem aplicar)
	kubectl kustomize k8s/overlays/dev

k8s-apply-prod: ## Aplica manifestos de produção no cluster atual
	kubectl apply -k k8s/overlays/production

k8s-apply-dev: ## Aplica manifestos de dev no cluster atual
	kubectl apply -k k8s/overlays/dev

k8s-diff-prod: ## Mostra diff entre estado atual do cluster e overlay de produção
	kubectl diff -k k8s/overlays/production

k8s-diff-dev: ## Mostra diff entre estado atual do cluster e overlay de dev
	kubectl diff -k k8s/overlays/dev

# --- Kubernetes local (kind) ---

k8s-local-up: ## Cria cluster kind local e sobe o ambiente de desenvolvimento
	bash k8s/local/setup.sh

k8s-local-down: ## Destroi o cluster kind local
	bash k8s/local/teardown.sh

k8s-local-status: ## Status dos pods no cluster local
	kubectl get pods -n querido-diario -o wide

k8s-local-hosts: ## Adiciona entradas ao /etc/hosts (requer sudo)
	@echo "127.0.0.1  queridodiario.local" | sudo tee -a /etc/hosts
	@echo "127.0.0.1  api.queridodiario.local" | sudo tee -a /etc/hosts
	@echo "127.0.0.1  backend-api.queridodiario.local" | sudo tee -a /etc/hosts
	@echo "Entradas adicionadas ao /etc/hosts."

k8s-local-garage-ui: ## Abre port-forward para o Garage Web UI (http://localhost:3909)
	kubectl port-forward svc/garage-webui 3909:3909 -n querido-diario

k8s-local-data-processing: ## Executa data-processing manualmente no cluster local
	kubectl create job --from=cronjob/data-processing data-processing-manual-$$(date +%s) \
	    -n querido-diario

k8s-local-frontend-build: ## Builda e carrega a imagem do frontend no cluster kind local
	docker build --network=host -t $(FRONTEND_IMAGE):local $(FRONTEND_DIR)
	kind load docker-image $(FRONTEND_IMAGE):local --name querido-diario-dev
