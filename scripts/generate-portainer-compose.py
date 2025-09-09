#!/usr/bin/env python3
"""
Script para gerar docker-compose-portainer.yml a partir do templates/docker-compose.yml base.

Este script transforma o arquivo base para:
1. Remover serviços de infraestrutura local (postgres, opensearch, minio)
2. Adicionar labels do Traefik para produção com middlewares automáticos:
   - API: cors-headers + api-rate-limit + security-headers + compression
   - Backend: api-rate-limit + security-headers + compression
3. Configurar networks externos (frontend)
4. Adicionar configurações de deploy/recursos
5. Ajustar environment variables para produção
"""

import yaml
import sys
import os
from pathlib import Path
from typing import Dict, Any


def load_yaml(file_path: str) -> Dict[str, Any]:
    """Carrega arquivo YAML"""
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(data: Dict[str, Any], file_path: str) -> None:
    """Salva arquivo YAML com formatação adequada"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(
            "# Auto-generated from templates/docker-compose.yml by generate-portainer-compose.py\n"
        )
        f.write(
            "# DO NOT EDIT MANUALLY - Make changes to templates/docker-compose.yml and regenerate\n\n"
        )
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            indent=2,
            sort_keys=False,
        )


def remove_dev_services(compose_data: Dict[str, Any]) -> None:
    """Remove serviços de desenvolvimento (postgres, opensearch, minio)"""
    dev_services = ["postgres", "opensearch", "minio"]

    for service in dev_services:
        if service in compose_data.get("services", {}):
            del compose_data["services"][service]

    # Remove volumes de desenvolvimento
    dev_volumes = ["postgres-data", "opensearch-data", "minio-data"]
    volumes = compose_data.get("volumes", {})
    for volume in dev_volumes:
        if volume in volumes:
            del volumes[volume]


def add_traefik_labels(service_config: Dict[str, Any], service_name: str) -> None:
    """Adiciona labels do Traefik para roteamento em produção"""
    labels = service_config.setdefault("labels", [])

    if service_name == "querido-diario-api":
        traefik_labels = [
            "traefik.enable=true",
            "traefik.docker.network=frontend",
            # HTTP Router (redirect to HTTPS)
            "traefik.http.routers.querido-diario-api-http.rule=Host(`api.${DOMAIN}`)",
            "traefik.http.routers.querido-diario-api-http.entrypoints=web",
            "traefik.http.routers.querido-diario-api-http.middlewares=https-redirect",
            # HTTPS Router with middlewares
            "traefik.http.routers.querido-diario-api-https.rule=Host(`api.${DOMAIN}`)",
            "traefik.http.routers.querido-diario-api-https.entrypoints=websecure",
            "traefik.http.routers.querido-diario-api-https.tls=true",
            "traefik.http.routers.querido-diario-api-https.tls.certresolver=${CERT_RESOLVER}",
            "traefik.http.routers.querido-diario-api-https.middlewares=cors-headers,api-rate-limit,security-headers,compression",
            # Service configuration
            "traefik.http.services.querido-diario-api.loadbalancer.server.port=8080",
            # HTTPS Redirect Middleware
            "traefik.http.middlewares.https-redirect.redirectscheme.scheme=https",
            "traefik.http.middlewares.https-redirect.redirectscheme.permanent=true",
        ]

    elif service_name == "querido-diario-backend":
        traefik_labels = [
            "traefik.enable=true",
            "traefik.docker.network=frontend",
            # HTTP Router (redirect to HTTPS)
            "traefik.http.routers.querido-diario-backend-http.rule=Host(`backend-api.${DOMAIN}`)",
            "traefik.http.routers.querido-diario-backend-http.entrypoints=web",
            "traefik.http.routers.querido-diario-backend-http.middlewares=https-redirect",
            # HTTPS Router with middlewares
            "traefik.http.routers.querido-diario-backend-https.rule=Host(`backend-api.${DOMAIN}`)",
            "traefik.http.routers.querido-diario-backend-https.entrypoints=websecure",
            "traefik.http.routers.querido-diario-backend-https.tls=true",
            "traefik.http.routers.querido-diario-backend-https.tls.certresolver=${CERT_RESOLVER}",
            "traefik.http.routers.querido-diario-backend-https.middlewares=api-rate-limit,security-headers,compression",
            # Service configuration
            "traefik.http.services.querido-diario-backend.loadbalancer.server.port=8000",
        ]
    else:
        return

    # Remove labels existentes do Traefik e adiciona os novos
    labels[:] = [label for label in labels if not label.startswith("traefik.")]
    labels.extend(traefik_labels)


def add_production_networks(service_config: Dict[str, Any], service_name: str) -> None:
    """Adiciona networks de produção (frontend para API/Backend)"""
    networks = service_config.setdefault("networks", [])

    if service_name in ["querido-diario-api", "querido-diario-backend"]:
        if "frontend" not in networks:
            networks.append("frontend")

    # Todos os serviços devem estar na rede interna
    if "querido-diario-internal" not in networks:
        networks.append("querido-diario-internal")


def add_deploy_config(service_config: Dict[str, Any], service_name: str) -> None:
    """Adiciona configurações de deploy e recursos"""
    deploy = service_config.setdefault("deploy", {})
    resources = deploy.setdefault("resources", {})

    # Configurações de recursos por serviço
    resource_configs = {
        "querido-diario-api": {
            "limits": {"memory": "${API_MEMORY_LIMIT:-1G}"},
            "reservations": {"memory": "${API_MEMORY_RESERVATION:-512M}"},
        },
        "querido-diario-backend": {
            "limits": {"memory": "${BACKEND_MEMORY_LIMIT:-1G}"},
            "reservations": {"memory": "${BACKEND_MEMORY_RESERVATION:-512M}"},
        },
        "celery-beat": {
            "limits": {"memory": "${CELERY_BEAT_MEMORY_LIMIT:-512M}"},
            "reservations": {"memory": "${CELERY_BEAT_MEMORY_RESERVATION:-256M}"},
        },
        "celery-worker": {
            "limits": {"memory": "${CELERY_WORKER_MEMORY_LIMIT:-1G}"},
            "reservations": {"memory": "${CELERY_WORKER_MEMORY_RESERVATION:-512M}"},
        },
        "querido-diario-data-processing": {
            "limits": {"memory": "${DATA_PROCESSING_MEMORY_LIMIT:-2G}"},
            "reservations": {"memory": "${DATA_PROCESSING_MEMORY_RESERVATION:-1G}"},
        },
        "apache-tika": {
            "limits": {"memory": "${APACHE_TIKA_MEMORY_LIMIT:-2G}"},
            "reservations": {"memory": "${APACHE_TIKA_MEMORY_RESERVATION:-1G}"},
        },
        "redis": {
            "limits": {"memory": "${REDIS_MEMORY_LIMIT:-256M}"},
            "reservations": {"memory": "${REDIS_MEMORY_RESERVATION:-128M}"},
        },
    }

    if service_name in resource_configs:
        resources.update(resource_configs[service_name])

    # Configuração de replicas para celery-worker
    if service_name == "celery-worker":
        deploy["replicas"] = "${CELERY_WORKER_REPLICAS:-2}"


def update_environment_for_production(
    service_config: Dict[str, Any], service_name: str
) -> None:
    """Atualiza environment variables para produção"""
    env = service_config.setdefault("environment", {})

    if service_name == "querido-diario-api":
        # Configurações específicas para produção da API
        production_env = {
            # OpenSearch configuration (external in production)
            "QUERIDO_DIARIO_OPENSEARCH_HOST": "${QUERIDO_DIARIO_OPENSEARCH_HOST}",
            "QUERIDO_DIARIO_OPENSEARCH_USER": "${QUERIDO_DIARIO_OPENSEARCH_USER}",
            "QUERIDO_DIARIO_OPENSEARCH_PASSWORD": "${QUERIDO_DIARIO_OPENSEARCH_PASSWORD}",
            "GAZETTE_OPENSEARCH_INDEX": "${OPENSEARCH_INDEX:-querido-diario}",
            # PostgreSQL configuration (external in production)
            "POSTGRES_COMPANIES_USER": "${POSTGRES_COMPANIES_USER}",
            "POSTGRES_COMPANIES_PASSWORD": "${POSTGRES_COMPANIES_PASSWORD}",
            "POSTGRES_COMPANIES_DB": "${POSTGRES_COMPANIES_DB}",
            "POSTGRES_COMPANIES_HOST": "${POSTGRES_COMPANIES_HOST}",
            "POSTGRES_COMPANIES_PORT": "${POSTGRES_COMPANIES_PORT}",
            "POSTGRES_AGGREGATES_USER": "${POSTGRES_AGGREGATES_USER}",
            "POSTGRES_AGGREGATES_PASSWORD": "${POSTGRES_AGGREGATES_PASSWORD}",
            "POSTGRES_AGGREGATES_DB": "${POSTGRES_AGGREGATES_DB}",
            "POSTGRES_AGGREGATES_HOST": "${POSTGRES_AGGREGATES_HOST}",
            "POSTGRES_AGGREGATES_PORT": "${POSTGRES_AGGREGATES_PORT}",
            # File storage configuration (external in production)
            "QUERIDO_DIARIO_FILES_ENDPOINT": "${QUERIDO_DIARIO_FILES_ENDPOINT}",
            # Production settings
            "QUERIDO_DIARIO_CORS_ALLOW_ORIGINS": "${QUERIDO_DIARIO_CORS_ALLOW_ORIGINS:-https://${DOMAIN}}",
            "QUERIDO_DIARIO_CORS_ALLOW_CREDENTIALS": "${QUERIDO_DIARIO_CORS_ALLOW_CREDENTIALS:-True}",
            "QUERIDO_DIARIO_DEBUG": "${QUERIDO_DIARIO_DEBUG:-False}",
            "QUERIDO_DIARIO_ENABLE_CORS": "${QUERIDO_DIARIO_ENABLE_CORS:-True}",
        }

        # Remove configurações de desenvolvimento e substitui por produção
        dev_keys = [
            "QUERIDO_DIARIO_OPENSEARCH_HOST",
            "POSTGRES_COMPANIES_HOST",
            "POSTGRES_AGGREGATES_HOST",
            "QUERIDO_DIARIO_FILES_ENDPOINT",
        ]

        for key in dev_keys:
            if key in env and not env[key].startswith("${"):
                env[key] = production_env[key]

        # Adiciona novas configurações
        env.update(production_env)

    elif service_name == "querido-diario-backend":
        # Configurações específicas para produção do Backend
        production_env = {
            "QD_BACKEND_SECRET_KEY": "${QD_BACKEND_SECRET_KEY}",
            "QD_BACKEND_DEBUG": "${QD_BACKEND_DEBUG:-False}",
            "QD_BACKEND_ALLOWED_HOSTS": "${QD_BACKEND_ALLOWED_HOSTS:-backend-api.${DOMAIN},${DOMAIN}}",
            "QD_BACKEND_ALLOWED_ORIGINS": "${QD_BACKEND_ALLOWED_ORIGINS:-https://${DOMAIN},https://backend-api.${DOMAIN}}",
            "QD_BACKEND_CSRF_TRUSTED_ORIGINS": "${QD_BACKEND_CSRF_TRUSTED_ORIGINS:-https://backend-api.${DOMAIN}}",
            # Database configuration (external in production)
            "QD_BACKEND_DB_URL": "${QD_BACKEND_DB_URL}",
            # Application configuration
            "STATIC_URL": "${STATIC_URL:-https://backend-api.${DOMAIN}/api/static/}",
            "FRONT_BASE_URL": "${FRONT_BASE_URL:-https://${DOMAIN}}",
        }

        env.update(production_env)


def update_commands_for_production(
    service_config: Dict[str, Any], service_name: str
) -> None:
    """Atualiza commands para produção"""
    if service_name == "querido-diario-backend":
        service_config["command"] = (
            "gunicorn config.wsgi:application -w ${BACKEND_WORKERS:-2} -b :8000 --log-level info"
        )


def update_networks_definition(compose_data: Dict[str, Any]) -> None:
    """Atualiza definição de networks para produção"""
    networks = compose_data.setdefault("networks", {})

    # Network frontend deve ser externa (Traefik)
    networks["frontend"] = {"external": True, "name": "frontend"}

    # Network interna
    networks["querido-diario-internal"] = {"driver": "bridge", "internal": False}


def generate_portainer_compose(base_file: str, output_file: str) -> None:
    """Função principal que gera o docker-compose-portainer.yml"""
    print(f"Carregando {base_file}...")
    compose_data = load_yaml(base_file)

    print("Removendo serviços de desenvolvimento...")
    remove_dev_services(compose_data)

    print("Configurando serviços para produção...")
    services = compose_data.get("services", {})

    for service_name, service_config in services.items():
        print(f"  Configurando {service_name}...")

        # Adiciona labels do Traefik
        add_traefik_labels(service_config, service_name)

        # Adiciona networks de produção
        add_production_networks(service_config, service_name)

        # Adiciona configurações de deploy
        add_deploy_config(service_config, service_name)

        # Atualiza environment variables
        update_environment_for_production(service_config, service_name)

        # Atualiza commands
        update_commands_for_production(service_config, service_name)

    print("Atualizando definições de networks...")
    update_networks_definition(compose_data)

    print(f"Salvando {output_file}...")
    save_yaml(compose_data, output_file)

    print("✅ Geração concluída!")
    print(f"📄 Arquivo gerado: {output_file}")
    print("\n💡 Para usar:")
    print("   docker compose -f docker-compose-portainer.yml up -d")


def main():
    """Função principal"""
    base_file = "templates/docker-compose.yml"
    output_file = "docker-compose-portainer.yml"

    if not os.path.exists(base_file):
        print(f"❌ Erro: Arquivo {base_file} não encontrado!")
        print("Execute este script no diretório que contém templates/docker-compose.yml")
        sys.exit(1)

    try:
        generate_portainer_compose(base_file, output_file)
    except Exception as e:
        print(f"❌ Erro durante a geração: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
