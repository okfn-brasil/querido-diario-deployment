# Querido Diário Deployment Makefile
# ===================================
#
# Compatível com Linux, macOS e Windows: todas as recipes chamam scripts
# Python (stdlib apenas) em vez de bash/grep/awk/sudo diretamente, então
# funcionam do mesmo jeito em qualquer shell (bash, zsh, PowerShell, cmd).
#
# Pré-requisitos:
#   - GNU Make (Linux/macOS: já vem instalado; Windows: `choco install make`,
#     `scoop install make`, ou use o Make do Git Bash/MSYS2/WSL)
#   - Python 3.9+ na variável PYTHON abaixo (padrão: python3)
#     Windows sem `python3.exe` no PATH: rode `make PYTHON=python <target>`
#   - Docker (com Linux containers habilitado no Docker Desktop, se aplicável)
#
# kubectl, kind e helm são instalados automaticamente pelos scripts quando
# ausentes (ver scripts/pycommon.py).

.PHONY: help \
        build-api build-backend \
        build-data-processing-base build-data-processing build-tika \
        build-frontend build-all \
        spider-setup spider-list run-spider \
        k8s-build-base k8s-build-prod k8s-build-dev \
        k8s-apply-prod k8s-apply-dev k8s-diff-prod k8s-diff-dev \
        k8s-local-up k8s-local-down k8s-local-status k8s-local-hosts \
        k8s-local-garage-ui k8s-local-data-processing \
        k8s-local-frontend-build

PYTHON ?= python3
REGISTRY = ghcr.io/okfn-brasil

QD_DIR               ?= ../querido-diario
API_DIR              ?= ../querido-diario-api
BACKEND_DIR          ?= ../querido-diario-backend/app
DATA_PROCESSING_DIR  ?= ../querido-diario-data-processing
FRONTEND_DIR         ?= ../querido-diario-frontend

FRONTEND_IMAGE       = $(REGISTRY)/querido-diario-frontend

help: ## Mostra esta mensagem de ajuda
	@$(PYTHON) scripts/help.py

# --- Raspadores (execução local, produção permanece na Zyte) ---

spider-setup: ## Cria venv e instala dependências dos raspadores (executar uma vez)
	$(PYTHON) scripts/spider.py setup --qd-dir "$(QD_DIR)"

spider-list: ## Lista todos os raspadores disponíveis
	$(PYTHON) scripts/spider.py list --qd-dir "$(QD_DIR)"

run-spider: ## Executa um raspador localmente (SPIDER=nome [START=YYYY-MM-DD] [END=YYYY-MM-DD])
	$(PYTHON) scripts/spider.py run "$(SPIDER)" --qd-dir "$(QD_DIR)" $(if $(START),--start $(START)) $(if $(END),--end $(END))

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
	$(PYTHON) scripts/k8s_local_up.py

k8s-local-down: ## Destroi o cluster kind local
	$(PYTHON) scripts/k8s_local_down.py

k8s-local-status: ## Status dos pods no cluster local
	kubectl get pods -n querido-diario -o wide

k8s-local-hosts: ## Adiciona entradas ao hosts file (Linux/Mac: sudo; Windows: terminal como Administrador)
	$(PYTHON) scripts/k8s_local_hosts.py

k8s-local-garage-ui: ## Abre port-forward para o Garage Web UI (http://localhost:3909)
	kubectl port-forward svc/garage-webui 3909:3909 -n querido-diario

k8s-local-data-processing: ## Executa data-processing manualmente no cluster local
	$(PYTHON) scripts/k8s_local_data_processing.py

k8s-local-frontend-build: ## Builda e carrega a imagem do frontend no cluster kind local
	docker build --network=host -t $(FRONTEND_IMAGE):local $(FRONTEND_DIR)
	kind load docker-image $(FRONTEND_IMAGE):local --name querido-diario-dev
