# Querido Diário Deployment Makefile
# ===================================

.PHONY: help network \
        deploy-traefik deploy-services deploy-dbs deploy-all \
        dev dev-down \
        down-traefik down-services down-dbs \
        validate logs ps status restart update \
        run-data-processing \
        shell-api shell-backend \
        check-env \
        k8s-build-base k8s-build-prod k8s-build-dev \
        k8s-apply-prod k8s-apply-dev k8s-diff-prod k8s-diff-dev \
        k8s-local-up k8s-local-down k8s-local-status k8s-local-hosts \
        k8s-local-garage-ui k8s-local-data-processing

ENV_FILE ?= .env

COMPOSE_TRAEFIK  = docker compose -f docker-compose.traefik.yml  --env-file $(ENV_FILE)
COMPOSE_SERVICES = docker compose -f docker-compose.yml           --env-file $(ENV_FILE)
COMPOSE_DBS      = docker compose -f docker-compose.dbs.yml       --env-file $(ENV_FILE)
COMPOSE_DEV      = docker compose \
                     -f docker-compose.yml \
                     -f docker-compose.traefik.yml \
                     -f docker-compose.dev.yml \
                     --env-file $(ENV_FILE)

help: ## Mostra esta mensagem de ajuda
	@echo "Comandos disponíveis:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Inicio rapido:"
	@echo "  Desenvolvimento : make dev"
	@echo "  Producao        : make deploy-all"
	@echo ""
	@echo "Variaveis:"
	@echo "  ENV_FILE=<path>  (padrao: .env)"

# --- Infraestrutura ---

network: ## Cria a rede Docker 'frontend' (necessaria antes do primeiro deploy)
	docker network create frontend 2>/dev/null || true

# --- Producao ---

deploy-traefik: network ## Sobe o Traefik (reverse proxy + SSL)
	$(COMPOSE_TRAEFIK) up -d

deploy-services: network ## Sobe os servicos da aplicacao (API, backend, celery, tika, redis)
	$(COMPOSE_SERVICES) up -d

deploy-dbs: ## Sobe os containers de banco de dados (somente quando DBs sao containers)
	$(COMPOSE_DBS) up -d

deploy-all: deploy-traefik deploy-services ## Sobe traefik + servicos (deploy completo)

# --- Desenvolvimento ---

dev: network ## Sobe ambiente de desenvolvimento (traefik HTTP + servicos + infra local)
	$(COMPOSE_DEV) up -d

dev-down: ## Para e remove o ambiente de desenvolvimento
	$(COMPOSE_DEV) down

# --- Parar servicos ---

down-traefik: ## Para o Traefik
	$(COMPOSE_TRAEFIK) down

down-services: ## Para os servicos da aplicacao
	$(COMPOSE_SERVICES) down

down-dbs: ## Para os containers de banco de dados
	$(COMPOSE_DBS) down

# --- Validacao ---

validate: ## Valida sintaxe de todos os arquivos docker-compose
	@echo "Validando docker-compose.yml..."
	@$(COMPOSE_SERVICES) config > /dev/null && echo "  OK: docker-compose.yml"
	@echo "Validando docker-compose.traefik.yml..."
	@$(COMPOSE_TRAEFIK) config > /dev/null && echo "  OK: docker-compose.traefik.yml"
	@echo "Validando docker-compose.dbs.yml..."
	@$(COMPOSE_DBS) config > /dev/null && echo "  OK: docker-compose.dbs.yml"
	@echo "Validando docker-compose.dev.yml..."
	@$(COMPOSE_DEV) config > /dev/null && echo "  OK: docker-compose.dev.yml"

check-env: ## Verifica variaveis obrigatorias no .env
	@echo "Verificando $(ENV_FILE)..."
	@for var in DOMAIN QD_BACKEND_SECRET_KEY ACME_EMAIL \
	            QD_DATA_DB_HOST QD_BACKEND_DB_HOST \
	            QUERIDO_DIARIO_OPENSEARCH_HOST \
	            STORAGE_ACCESS_KEY STORAGE_ACCESS_SECRET STORAGE_BUCKET; do \
		val=$$(grep "^$${var}=" $(ENV_FILE) 2>/dev/null | cut -d'=' -f2-); \
		if [ -z "$$val" ]; then \
			echo "  FALTANDO: $$var"; \
		else \
			echo "  OK: $$var"; \
		fi; \
	done

# --- Utilitarios ---

logs: ## Exibe logs dos servicos (use SERVICE=nome para filtrar)
	$(COMPOSE_SERVICES) logs -f $(SERVICE)

ps: ## Lista containers em execucao
	$(COMPOSE_SERVICES) ps

status: ## Mostra status detalhado dos servicos
	$(COMPOSE_SERVICES) ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"

restart: ## Reinicia todos os servicos
	$(COMPOSE_SERVICES) restart $(SERVICE)

update: ## Atualiza imagens e reinicia servicos
	$(COMPOSE_SERVICES) pull
	$(COMPOSE_SERVICES) up -d

run-data-processing: ## Executa o data-processing manualmente (uso pontual)
	$(COMPOSE_SERVICES) run --rm data-processing

shell-api: ## Abre shell no container da API
	$(COMPOSE_SERVICES) exec api /bin/bash

shell-backend: ## Abre shell no container do Backend
	$(COMPOSE_SERVICES) exec backend /bin/bash

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
