# Querido Diário Deployment Makefile
# ===================================

.PHONY: help dev prod generate-prod generate-dev clean validate

# Target padrão
help: ## Mostra esta mensagem de ajuda
	@echo "📋 Comandos disponíveis:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "🚀 Início rápido:"
	@echo "  Desenvolvimento: make dev"
	@echo "  Produção:       make prod"
	@echo ""
	@echo "📋 Gerar arquivos:"
	@echo "  make generate-dev        # Gera docker-compose.yml para desenvolvimento"
	@echo "  make generate-prod       # Gera docker-compose-portainer.yml para produção"
	@echo "  make generate-traefik    # Gera docker-compose.traefik.yml"
	@echo ""
	@echo "🎯 Configuração de ambiente:"
	@echo "  make setup-env-dev-interactive    # Desenvolvimento com domínio personalizado"
	@echo "  make setup-env-prod              # Produção com domínio personalizado"
	@echo "  make setup-env-prod-default      # Produção com domínio padrão"
	@echo ""
	@echo "💡 Sobrescritas automáticas:"
	@echo "  Se o arquivo 'overrides.env' existir, será aplicado automaticamente"
	@echo ""

generate-dev: ## Copia arquivos docker-compose para desenvolvimento
	@echo "📋 Copiando arquivos docker-compose de desenvolvimento..."
	@cp templates/docker-compose.yml docker-compose.yml
	@cp templates/docker-compose.dev.yml docker-compose.dev.yml
	@echo "✅ Arquivos docker-compose criados para desenvolvimento!"
	@echo "💡 Use: docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d"

dev: generate-dev setup-env-dev ## Gera .env e inicia ambiente de desenvolvimento com todos os serviços
	@echo "🚀 Iniciando ambiente de desenvolvimento..."
	docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d
	@echo "✅ Serviços de desenvolvimento iniciados!"
	@echo "📍 API: http://localhost:8080"
	@echo "📍 Backend: http://localhost:8000"

dev-build: generate-dev setup-env-dev ## Constrói e inicia ambiente de desenvolvimento
	@echo "🏗️ Construindo e iniciando ambiente de desenvolvimento..."
	docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d --build
	@echo "✅ Serviços de desenvolvimento construídos e iniciados!"

generate-prod: ## Gera docker-compose-portainer.yml para produção a partir do template
	@echo "⚙️ Gerando arquivo docker-compose de produção..."
	python3 scripts/generate-portainer-compose.py
	@echo "✅ Arquivo de produção gerado: docker-compose-portainer.yml"
	@echo "💡 Use 'make setup-env-prod' para gerar o arquivo .env correspondente!"

prod: generate-prod setup-env-prod ## Gera arquivos de produção e inicia ambiente de produção
	@echo "🚀 Iniciando ambiente de produção..."
	@if [ ! -f .env.production ]; then \
		echo "❌ Erro: arquivo .env.production não encontrado!"; \
		echo "💡 Execute 'make setup-env-prod' e configure-o primeiro."; \
		exit 1; \
	fi
	docker compose -f docker-compose-portainer.yml --env-file .env.production up -d
	@echo "✅ Serviços de produção iniciados!"

validate: ## Valida sintaxe dos arquivos docker-compose
	@echo "🔍 Validando arquivos docker-compose..."
	@if [ -f docker-compose.yml ] && [ -f docker-compose.dev.yml ]; then \
		echo "Verificando docker-compose de desenvolvimento..."; \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev config > /dev/null && echo "✅ docker-compose de desenvolvimento está válido"; \
	else \
		echo "⚠️ Arquivos de desenvolvimento não encontrados. Execute 'make generate-dev' primeiro."; \
	fi
	@if [ -f docker-compose-portainer.yml ]; then \
		echo "Verificando docker-compose-portainer.yml..."; \
		docker compose -f docker-compose-portainer.yml config > /dev/null && echo "✅ docker-compose-portainer.yml está válido"; \
	else \
		echo "⚠️ docker-compose-portainer.yml não encontrado. Execute 'make generate-prod' primeiro."; \
	fi

clean: ## Para e remove todos os containers, redes e volumes
	@echo "🧹 Limpando..."
	@if [ -f docker-compose.yml ]; then \
		docker compose down -v --remove-orphans; \
	fi
	@if [ -f docker-compose-portainer.yml ]; then \
		docker compose -f docker-compose-portainer.yml down -v --remove-orphans; \
	fi
	@echo "✅ Limpeza concluída!"

clean-env: ## Remove arquivos de ambiente gerados
	@echo "🧹 Limpando arquivos de ambiente..."
	@if [ -f .env ]; then \
		rm .env && echo "Removido .env"; \
	fi
	@if [ -f .env.production ]; then \
		rm .env.production && echo "Removido .env.production"; \
	fi
	@echo "✅ Arquivos de ambiente limpos!"

clean-all: clean clean-env ## Remove containers e arquivos gerados
	@if [ -f docker-compose-portainer.yml ]; then \
		rm docker-compose-portainer.yml && echo "Removido docker-compose-portainer.yml"; \
	fi
	@echo "✅ Todos os arquivos gerados foram limpos!"

logs: ## Mostra logs de todos os serviços
	docker compose logs -f

logs-api: ## Mostra logs do serviço API
	docker compose logs -f querido-diario-api

logs-backend: ## Mostra logs do serviço Backend
	docker compose logs -f querido-diario-backend

status: ## Mostra status de todos os serviços
	@echo "📊 Status dos Serviços:"
	docker compose ps

restart: ## Reinicia todos os serviços
	@echo "🔄 Reiniciando serviços..."
	docker compose restart
	@echo "✅ Serviços reiniciados!"

update: ## Atualiza todas as imagens de serviços
	@echo "📦 Atualizando imagens de serviços..."
	docker compose pull
	@echo "✅ Imagens atualizadas! Execute 'make restart' para aplicar."

setup-env-dev: ## Gera arquivo .env para desenvolvimento com domínio padrão (overrides automáticos)
	@echo "⚙️ Gerando arquivo de ambiente de desenvolvimento..."
	@if [ -f overrides.env ]; then \
		echo "📂 Arquivo de sobrescritas encontrado: overrides.env"; \
		python3 scripts/generate-env.py dev --default --override-file=overrides.env; \
	else \
		python3 scripts/generate-env.py dev --default; \
	fi
	@echo "💡 Arquivo .env de desenvolvimento pronto! Use 'make dev' para iniciar os serviços."

setup-env-dev-interactive: ## Gera arquivo .env para desenvolvimento com configuração interativa de domínio
	@echo "🎯 Gerando arquivo de ambiente de desenvolvimento (interativo)..."
	@if [ -f overrides.env ]; then \
		echo "� Aplicando sobrescritas de overrides.env"; \
		python3 scripts/generate-env.py dev --override-file=overrides.env; \
	else \
		python3 scripts/generate-env.py dev; \
	fi

setup-env-prod: ## Gera arquivo .env.production para produção com configuração interativa de domínio
	@echo "🎯 Gerando arquivo de ambiente de produção (interativo)..."
	@if [ -f overrides.env ]; then \
		echo "📂 Aplicando sobrescritas de overrides.env"; \
		python3 scripts/generate-env.py prod --override-file=overrides.env; \
	else \
		python3 scripts/generate-env.py prod; \
	fi

setup-env-prod-default: ## Gera arquivo .env.production para produção com domínio padrão
	@echo "⚙️ Gerando arquivo de ambiente de produção (domínio padrão)..."
	@if [ -f overrides.env ]; then \
		echo "📂 Aplicando sobrescritas de overrides.env"; \
		python3 scripts/generate-env.py prod --default --override-file=overrides.env; \
	else \
		python3 scripts/generate-env.py prod --default; \
	fi
	@echo "💡 Arquivo .env.production pronto! Revise antes de fazer deploy."

setup-env: setup-env-dev ## Alias para setup-env-dev (padrão para desenvolvimento)

generate-traefik: ## Copia exemplo docker-compose do Traefik para arquivo de trabalho
	@echo "📋 Copiando exemplo docker-compose do Traefik..."
	@cp templates/docker-compose.traefik.example.yml docker-compose.traefik.yml
	@echo "✅ docker-compose.traefik.yml criado!"
	@echo "💡 Próximos passos:"
	@echo "   1. Criar rede frontend: docker network create frontend"
	@echo "   2. Configurar registros DNS (veja docs/traefik-setup.md)"
	@echo "   3. Iniciar Traefik: docker compose -f docker-compose.traefik.yml up -d"

generate-all: generate-prod setup-env-prod generate-traefik ## Gera todos os arquivos de produção (docker-compose, env e traefik)
	@echo "✅ Todos os arquivos de produção gerados!"
	@echo "📄 Arquivos criados:"
	@echo "   • docker-compose-portainer.yml"
	@echo "   • .env.production"
	@echo ""
	@echo "⚠️  Próximos passos:"
	@echo "   1. Revise e customize .env.production"
	@echo "   2. Faça deploy com: make prod"

check-env: ## Verifica se as variáveis de ambiente obrigatórias estão definidas
	@echo "🔍 Verificando variáveis de ambiente..."
	@python3 -c "import os; missing = [var for var in ['DOMAIN'] if not os.getenv(var)]; print('✅ Variáveis obrigatórias definidas') if not missing else print(f'❌ Variáveis em falta: {missing}')"

# Utilitários de desenvolvimento
db-reset: ## Reseta banco de dados (apenas desenvolvimento)
	@echo "🗃️ Resetando banco de dados de desenvolvimento..."
	docker compose exec querido-diario-backend python manage.py migrate
	@echo "✅ Reset do banco de dados concluído!"

shell-api: ## Abre shell no container da API
	docker compose exec querido-diario-api /bin/bash

shell-backend: ## Abre shell no container do Backend
	docker compose exec querido-diario-backend /bin/bash

health: ## Verifica saúde de todos os serviços
	@echo "🏥 Verificação de Saúde:"
	@docker compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
