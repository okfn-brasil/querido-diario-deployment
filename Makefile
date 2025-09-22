# Querido Diário Deployment Makefile
# ===================================

.PHONY: help dev dev-build prod prod-build clean validate setup-env-dev setup-env-prod

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
	@echo "📋 Configuração:"
	@echo "  make setup-env-dev    # Gera .env para desenvolvimento"
	@echo "  make setup-env-prod   # Gera .env para produção"
	@echo ""
	@echo "🧹 Limpeza:"
	@echo "  make clean           # Para containers e remove volumes"
	@echo "  make clean-all       # Limpa containers, volumes e arquivos gerados"
	@echo ""

setup-env-dev: ## Gera arquivo .env para desenvolvimento local (domínio padrão)
	@echo "⚙️ Gerando arquivo .env para desenvolvimento..."
	@echo "🏠 Usando configuração padrão para desenvolvimento local"
	@cp templates/env.prod.sample .env
	@echo "DOMAIN=queridodiario.local" > .env.temp
	@echo "QD_BACKEND_SECRET_KEY=dev-secret-key-not-for-production" >> .env.temp
	@echo "QD_BACKEND_DEBUG=True" >> .env.temp
	@echo "DEBUG=1" >> .env.temp
	@grep -v "^DOMAIN=" templates/env.prod.sample | grep -v "^QD_BACKEND_SECRET_KEY=" | grep -v "^QD_BACKEND_DEBUG=" | grep -v "^DEBUG=" >> .env.temp
	@mv .env.temp .env
	@echo "✅ Arquivo .env criado para desenvolvimento!"
	@echo "💡 Use 'make dev' para iniciar os serviços."

setup-env-prod: ## Gera arquivo .env para produção (requer edição manual)
	@echo "⚙️ Gerando arquivo .env para produção..."
	@cp templates/env.prod.sample .env
	@echo "✅ Arquivo .env criado a partir de env.prod.sample"
	@echo ""
	@echo "⚠️  IMPORTANTE - Configure as seguintes variáveis obrigatórias em .env:"
	@echo "   • DOMAIN                  (seu domínio de produção)"
	@echo "   • QD_BACKEND_SECRET_KEY   (chave secreta do Django)"
	@echo "   • Strings de conexão dos bancos de dados externos"
	@echo "   • Configurações do OpenSearch externo"
	@echo "   • Configurações de storage (S3 ou similar)"
	@echo "   • Credenciais do serviço de email"
	@echo ""
	@echo "💡 Após configurar, use 'make prod' para fazer o deploy."

dev: setup-env-dev ## Inicia ambiente de desenvolvimento com todos os serviços
	@echo "🚀 Iniciando ambiente de desenvolvimento..."
	@echo "🌐 Criando rede frontend se não existir..."
	@docker network create frontend 2>/dev/null || true
	@echo "📦 Iniciando serviços de desenvolvimento..."
	docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d
	@echo ""
	@echo "✅ Serviços de desenvolvimento iniciados!"
	@echo ""
	@echo "📍 URLs disponíveis:"
	@echo "   • API: http://localhost:8080 ou http://api.queridodiario.local"
	@echo "   • Backend: http://localhost:8000 ou http://backend-api.queridodiario.local"
	@echo "   • OpenSearch: http://localhost:9200"
	@echo "   • MinIO: http://localhost:9000"
	@echo "   • Redis: localhost:6378"
	@echo ""
	@echo "💡 Para parar: make clean"

dev-build: setup-env-dev ## Reconstrói e inicia ambiente de desenvolvimento
	@echo "🏗️ Reconstruindo e iniciando ambiente de desenvolvimento..."
	@echo "🌐 Criando rede frontend se não existir..."
	@docker network create frontend 2>/dev/null || true
	@echo "📦 Reconstruindo e iniciando serviços..."
	docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d --build
	@echo "✅ Serviços de desenvolvimento reconstruídos e iniciados!"

prod: ## Inicia ambiente de produção
	@echo "🚀 Iniciando ambiente de produção..."
	@if [ ! -f .env ]; then \
		echo "❌ Erro: arquivo .env não encontrado!"; \
		echo "💡 Execute 'make setup-env-prod' e configure-o primeiro."; \
		exit 1; \
	fi
	@echo "🌐 Criando rede frontend se não existir..."
	@docker network create frontend 2>/dev/null || true
	@echo "📦 Iniciando serviços de produção..."
	docker compose -f docker-compose.yml up -d
	@echo ""
	@echo "✅ Serviços de produção iniciados!"
	@echo ""
	@echo "📍 URLs configuradas (verifique seu DNS):"
	@echo "   • Frontend: https://$$(grep '^DOMAIN=' .env | cut -d'=' -f2)"
	@echo "   • API: https://api.$$(grep '^DOMAIN=' .env | cut -d'=' -f2)"
	@echo "   • Backend: https://backend-api.$$(grep '^DOMAIN=' .env | cut -d'=' -f2)"
	@echo ""
	@echo "💡 Para parar: make clean"

prod-build: ## Reconstrói e inicia ambiente de produção
	@echo "🏗️ Reconstruindo e iniciando ambiente de produção..."
	@if [ ! -f .env ]; then \
		echo "❌ Erro: arquivo .env não encontrado!"; \
		echo "💡 Execute 'make setup-env-prod' e configure-o primeiro."; \
		exit 1; \
	fi
	@echo "🌐 Criando rede frontend se não existir..."
	@docker network create frontend 2>/dev/null || true
	@echo "📦 Reconstruindo e iniciando serviços..."
	docker compose -f docker-compose.yml up -d --build
	@echo "✅ Serviços de produção reconstruídos e iniciados!"

validate: ## Valida sintaxe dos arquivos docker-compose
	@echo "🔍 Validando arquivos docker-compose..."
	@echo "Verificando docker-compose de desenvolvimento..."
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev config > /dev/null && echo "✅ docker-compose de desenvolvimento está válido"
	@echo "Verificando docker-compose de produção..."
	@docker compose -f docker-compose.yml config > /dev/null && echo "✅ docker-compose de produção está válido"

clean: ## Para e remove todos os containers, redes e volumes
	@echo "🧹 Limpando containers e volumes..."
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v --remove-orphans 2>/dev/null || true; \
		docker compose -f docker-compose.yml down -v --remove-orphans 2>/dev/null || true; \
	fi
	@echo "✅ Limpeza de containers concluída!"

clean-env: ## Remove arquivos de ambiente gerados
	@echo "🧹 Limpando arquivos de ambiente..."
	@if [ -f .env ]; then \
		rm .env && echo "Removido .env"; \
	fi
	@echo "✅ Arquivos de ambiente limpos!"

clean-all: clean clean-env ## Remove containers, volumes e arquivos gerados
	@echo "✅ Limpeza completa concluída!"

logs: ## Mostra logs de todos os serviços
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f; \
	else \
		docker compose -f docker-compose.yml logs -f; \
	fi

logs-api: ## Mostra logs do serviço API
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f querido-diario-api; \
	else \
		docker compose -f docker-compose.yml logs -f querido-diario-api; \
	fi

logs-backend: ## Mostra logs do serviço Backend
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f querido-diario-backend; \
	else \
		docker compose -f docker-compose.yml logs -f querido-diario-backend; \
	fi

logs-traefik: ## Mostra logs do Traefik
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f traefik; \
	else \
		docker compose -f docker-compose.yml logs -f traefik; \
	fi

status: ## Mostra status de todos os serviços
	@echo "📊 Status dos Serviços:"
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml ps; \
	else \
		docker compose -f docker-compose.yml ps; \
	fi

restart: ## Reinicia todos os serviços
	@echo "🔄 Reiniciando serviços..."
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml restart; \
	else \
		docker compose -f docker-compose.yml restart; \
	fi
	@echo "✅ Serviços reiniciados!"

update: ## Atualiza todas as imagens de serviços
	@echo "📦 Atualizando imagens de serviços..."
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml pull; \
	else \
		docker compose -f docker-compose.yml pull; \
	fi
	@echo "✅ Imagens atualizadas! Execute 'make restart' para aplicar."

# Utilitários de desenvolvimento
db-reset: ## Reseta banco de dados (apenas desenvolvimento)
	@echo "🗃️ Resetando banco de dados de desenvolvimento..."
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml exec querido-diario-backend python manage.py migrate; \
	else \
		echo "❌ Execute 'make dev' primeiro para iniciar o ambiente de desenvolvimento"; \
	fi
	@echo "✅ Reset do banco de dados concluído!"

shell-api: ## Abre shell no container da API
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml exec querido-diario-api /bin/bash; \
	else \
		docker compose -f docker-compose.yml exec querido-diario-api /bin/bash; \
	fi

shell-backend: ## Abre shell no container do Backend
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml exec querido-diario-backend /bin/bash; \
	else \
		docker compose -f docker-compose.yml exec querido-diario-backend /bin/bash; \
	fi

health: ## Verifica saúde de todos os serviços
	@echo "🏥 Verificação de Saúde:"
	@if docker compose ps --services &>/dev/null; then \
		docker compose -f docker-compose.yml -f docker-compose.dev.yml ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"; \
	else \
		docker compose -f docker-compose.yml ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"; \
	fi

check-env: ## Verifica se as variáveis de ambiente obrigatórias estão definidas
	@echo "🔍 Verificando variáveis de ambiente..."
	@if [ -f .env ]; then \
		if grep -q "^DOMAIN=" .env; then \
			echo "✅ Variável DOMAIN definida: $$(grep '^DOMAIN=' .env | cut -d'=' -f2)"; \
		else \
			echo "❌ Variável DOMAIN não encontrada no .env"; \
		fi; \
		if grep -q "^QD_BACKEND_SECRET_KEY=" .env; then \
			echo "✅ Variável QD_BACKEND_SECRET_KEY definida"; \
		else \
			echo "❌ Variável QD_BACKEND_SECRET_KEY não encontrada no .env"; \
		fi; \
	else \
		echo "❌ Arquivo .env não encontrado. Execute 'make setup-env-dev' ou 'make setup-env-prod' primeiro."; \
	fi

network-create: ## Cria rede frontend para o Traefik
	@echo "🌐 Criando rede frontend..."
	@docker network create frontend 2>/dev/null || echo "ℹ️ Rede frontend já existe"
	@echo "✅ Rede frontend pronta!"

network-remove: ## Remove rede frontend
	@echo "🗑️ Removendo rede frontend..."
	@docker network rm frontend 2>/dev/null || echo "ℹ️ Rede frontend não existe"
	@echo "✅ Rede frontend removida!"
