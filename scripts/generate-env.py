#!/usr/bin/env python3
"""
Script interativo para gerar arquivos de environment com composição de domínios.

Uso:
    python3 generate-interactive-env.py dev      # Gera .env para desenvolvimento
    python3 generate-interactive-env.py prod     # Gera .env.production para produção

O script permite ao usuário definir o domínio e automaticamente compõe todas as
variáveis relacionadas (API, Backend, CORS, URLs, etc.)
"""

import sys
import re
from pathlib import Path
from typing import Dict, Tuple, Optional


def get_domain_from_user(env_type: str, use_default: bool = False) -> str:
    """Solicita domínio do usuário com validação ou usa valor padrão"""
    default_domain = "queridodiario.local"

    if use_default:
        print(f"🌐 Usando domínio padrão: {default_domain}")
        return default_domain

    if env_type == "dev":
        print(f"🏠 Configurando ambiente de DESENVOLVIMENTO")
    else:
        print(f"🚀 Configurando ambiente de PRODUÇÃO")

    print(f"")
    print(f"📍 Qual domínio principal será usado?")
    print(f"   Exemplo: {default_domain}")
    print(f"")
    print(f"💡 Os seguintes subdomínios serão criados automaticamente:")
    print(f"   • Frontend: https://SEU_DOMINIO")
    print(f"   • API: https://api.SEU_DOMINIO")
    print(f"   • Backend/Admin: https://backend-api.SEU_DOMINIO")
    print(f"")

    while True:
        domain = input(f"Domínio [{default_domain}]: ").strip()

        if not domain:
            domain = default_domain
            break

        # Validação básica de domínio
        if not re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", domain):
            print(
                "❌ Formato de domínio inválido. Use formato como: exemplo.com ou sub.exemplo.org"
            )
            continue

        break

    print(f"")
    print(f"✅ Domínio definido: {domain}")
    print(f"📍 URLs que serão configuradas:")
    print(f"   • Frontend: https://{domain}")
    print(f"   • API: https://api.{domain}")
    print(f"   • Backend/Admin: https://backend-api.{domain}")
    print(f"")

    return domain


def get_protocol_and_ports(env_type: str) -> Tuple[str, str, str]:
    """Retorna protocolo e portas baseado no tipo de ambiente"""
    if env_type == "dev":
        # Desenvolvimento: HTTP local com portas específicas
        return "http", "4200", "8000"
    else:
        # Produção: HTTPS sem portas (443 implícita)
        return "https", "", ""


def compose_domain_variables(domain: str, env_type: str) -> Dict[str, str]:
    """Compõe todas as variáveis relacionadas ao domínio"""
    protocol, frontend_port, backend_port = get_protocol_and_ports(env_type)

    if env_type == "dev":
        # Desenvolvimento: localhost com portas específicas
        frontend_url = f"http://localhost:{frontend_port}"
        backend_static_url = f"http://localhost:{backend_port}/api/static/"

        # Para desenvolvimento, permitir tanto localhost quanto o domínio configurado
        allowed_hosts = f"localhost,backend-api.{domain},127.0.0.1"
        allowed_origins = f"http://localhost:{frontend_port},http://localhost:{backend_port},http://{domain}"
        csrf_origins = f"http://localhost:{backend_port},http://backend-api.{domain}"
        cors_allow_origins = frontend_url  # Frontend localhost para CORS
    else:
        # Produção: domínios com HTTPS
        frontend_url = f"{protocol}://{domain}"
        backend_url = f"{protocol}://backend-api.{domain}"
        backend_static_url = f"{backend_url}/api/static/"

        allowed_hosts = f"backend-api.{domain},{domain}"
        allowed_origins = f"{frontend_url},{backend_url}"
        csrf_origins = backend_url
        cors_allow_origins = frontend_url

    return {
        "DOMAIN": domain,
        "QD_BACKEND_ALLOWED_HOSTS": allowed_hosts,
        "QD_BACKEND_ALLOWED_ORIGINS": allowed_origins,
        "QD_BACKEND_CSRF_TRUSTED_ORIGINS": csrf_origins,
        "STATIC_URL": backend_static_url,
        "FRONT_BASE_URL": frontend_url,
        "QUERIDO_DIARIO_CORS_ALLOW_ORIGINS": cors_allow_origins,
        "DEFAULT_FROM_EMAIL": f"noreply@{domain}",
        "SERVER_EMAIL": f"server@{domain}",
        "QUOTATION_TO_EMAIL": f"quotes@{domain}",
        "QUERIDO_DIARIO_SUGGESTION_RECIPIENT_EMAIL": f"team@{domain}",
    }


def read_template() -> str:
    """Lê o arquivo template completo"""
    template_file = Path("templates/env.complete.sample")
    if not template_file.exists():
        raise FileNotFoundError("templates/env.complete.sample não encontrado!")

    return template_file.read_text(encoding="utf-8")


def apply_domain_substitutions(content: str, substitutions: Dict[str, str]) -> str:
    """Aplica as substituições de domínio no conteúdo"""
    print(f"🔄 Aplicando substituições de domínio...")

    for key, value in substitutions.items():
        # Procura por linhas que definem a variável (tanto ativas quanto comentadas)
        pattern = rf"^(#\s*)?{re.escape(key)}=.*$"
        replacement = f"{key}={value}"

        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            print(f"  ✅ {key} = {value}")
        else:
            # Se a variável não existe, adiciona no final da seção apropriada
            print(f"  ➕ Adicionando {key} = {value}")
            # Adiciona antes da primeira linha vazia ou no final
            if "\n\n" in content:
                parts = content.split("\n\n", 1)
                content = parts[0] + f"\n{key}={value}\n\n" + parts[1]
            else:
                content += f"\n{key}={value}\n"

    return content


def load_overrides(override_file: str) -> Dict[str, str]:
    """Carrega valores de um arquivo de sobrescritas"""
    if not Path(override_file).exists():
        raise FileNotFoundError(f"Arquivo de sobrescritas não encontrado: {override_file}")

    print(f"📂 Carregando sobrescritas de: {override_file}")

    overrides = {}
    with open(override_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            # Ignora comentários e linhas vazias
            if not line or line.startswith('#'):
                continue

            # Processa linhas no formato KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Remove aspas se presentes
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]

                overrides[key] = value
                print(f"  ✅ {key} = {value[:50]}{'...' if len(value) > 50 else ''}")
            else:
                print(f"  ⚠️ Linha {line_num} ignorada (formato inválido): {line}")

    print(f"📋 Carregadas {len(overrides)} variáveis do arquivo de sobrescritas")
    return overrides


def apply_overrides(content: str, overrides: Dict[str, str]) -> str:
    """Aplica sobrescritas ao conteúdo"""
    if not overrides:
        return content

    print(f"🔧 Aplicando {len(overrides)} sobrescritas...")

    for key, value in overrides.items():
        # Procura por linhas que definem a variável (tanto ativas quanto comentadas)
        pattern = rf"^(#\s*)?{re.escape(key)}=.*$"
        replacement = f"{key}={value}"

        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            print(f"  ✅ {key} atualizado")
        else:
            # Se a variável não existe, adiciona no final
            print(f"  ➕ {key} adicionado")
            content += f"\n{key}={value}\n"

    return content


def remove_production_overrides_section(content: str) -> str:
    """Remove a seção SOBRESCRITAS DE PRODUÇÃO para evitar duplicações"""
    print(f"🗑️ Removendo seção SOBRESCRITAS DE PRODUÇÃO...")

    # Remove toda a seção entre # PRODUCTION-START e # PRODUCTION-END
    pattern = r'# =============================================================================\n# 🔄 SOBRESCRITAS DE PRODUÇÃO.*?# PRODUCTION-END'
    content = re.sub(pattern, '', content, flags=re.DOTALL)

    # Remove linhas vazias excessivas que podem ter ficado
    content = re.sub(r'\n{3,}', '\n\n', content)

    return content


def apply_environment_specific_settings(content: str, env_type: str) -> str:
    """Aplica configurações específicas do ambiente"""
    if env_type == "dev":
        # Configurações de desenvolvimento
        dev_settings = {
            "QD_BACKEND_DEBUG": "True",
            "QUERIDO_DIARIO_DEBUG": "True",
            "DEBUG": "1",
            "DATA_PROCESSING_DEBUG": "1",
        }

        for key, value in dev_settings.items():
            pattern = rf"^(#\s*)?{re.escape(key)}=.*$"
            replacement = f"{key}={value}"
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    else:
        # Configurações de produção
        prod_settings = {
            "QD_BACKEND_DEBUG": "False",
            "QUERIDO_DIARIO_DEBUG": "False",
            "DEBUG": "0",
            "DATA_PROCESSING_DEBUG": "0",
        }

        for key, value in prod_settings.items():
            pattern = rf"^(#\s*)?{re.escape(key)}=.*$"
            replacement = f"{key}={value}"
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

    return content


def add_environment_header(content: str, env_type: str, domain: str) -> str:
    """Adiciona cabeçalho específico do ambiente"""
    timestamp = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if env_type == "dev":
        header = f"""# Querido Diário - Development Environment
# ==========================================
#
# Auto-generated on {timestamp}
# Domain configured: {domain}
#
# URLs configuradas:
# • Frontend: http://localhost:4200 (development server)
# • API: http://localhost:8080 → api.{domain} (via Traefik)
# • Backend: http://localhost:8000 → backend-api.{domain} (via Traefik)
#
# Para regenerar: make setup-env-dev

"""
    else:  # prod
        header = f"""# Querido Diário - Production Environment
# =========================================
#
# Auto-generated on {timestamp}
# Domain configured: {domain}
#
# URLs configuradas:
# • Frontend: https://{domain}
# • API: https://api.{domain}
# • Backend/Admin: https://backend-api.{domain}
#
# Para regenerar: make setup-env-prod
#
# IMPORTANTE: Revise e configure antes de fazer deploy:
# - Strings de conexão de banco de dados externos
# - Endpoints e credenciais do OpenSearch
# - Endpoints e credenciais de storage
# - Credenciais do serviço de email
# - Chave secreta do Django (QD_BACKEND_SECRET_KEY)

"""

    return header + content


def generate_env_file(env_type: str, use_default: bool = False, override_file: Optional[str] = None) -> None:
    """Gera arquivo de environment específico com interação do usuário ou valor padrão"""
    if env_type not in ["dev", "prod"]:
        raise ValueError("env_type deve ser 'dev' ou 'prod'")

    # Solicita domínio do usuário ou usa padrão
    domain = get_domain_from_user(env_type, use_default)

    # Lê template
    print(f"📖 Lendo template completo...")
    content = read_template()

    # Compõe variáveis de domínio
    print(f"⚙️ Compondo variáveis de domínio...")
    domain_vars = compose_domain_variables(domain, env_type)

    # Aplica substituições
    content = apply_domain_substitutions(content, domain_vars)

    # Remove seção de sobrescritas de produção para evitar duplicações
    content = remove_production_overrides_section(content)

    # Aplica configurações específicas do ambiente
    print(f"🔧 Aplicando configurações de {env_type}...")
    content = apply_environment_specific_settings(content, env_type)

    # Aplica sobrescritas se arquivo fornecido
    if override_file:
        try:
            overrides = load_overrides(override_file)
            content = apply_overrides(content, overrides)
            if env_type == "dev":
                print(f"💡 Sobrescritas aplicadas ao ambiente de desenvolvimento")
        except FileNotFoundError as e:
            print(f"⚠️ {e}")
            print(f"💡 Continuando sem sobrescritas...")

    # Define arquivo de saída
    if env_type == "dev":
        output_file = ".env"
    else:
        output_file = ".env.production"

    # Adiciona cabeçalho
    print(f"📝 Adicionando cabeçalho...")
    content = add_environment_header(content, env_type, domain)

    # Limpa linhas vazias excessivas
    content = re.sub(r"\n{3,}", "\n\n", content)

    # Salva arquivo
    print(f"💾 Salvando {output_file}...")
    Path(output_file).write_text(content, encoding="utf-8")

    print(f"")
    print(f"✅ Arquivo {output_file} gerado com sucesso!")
    print(f"")
    print(f"📋 Resumo das configurações:")
    for key, value in domain_vars.items():
        print(f"   {key} = {value}")

    if env_type == "prod":
        print(f"")
        print(f"⚠️  Próximos passos para produção:")
        print(f"   1. Revise o arquivo {output_file}")
        print(f"   2. Configure strings de conexão de serviços externos")
        print(f"   3. Configure chave secreta do Django")
        print(f"   4. Faça deploy com: make prod")


def main():
    """Função principal"""
    if len(sys.argv) < 2 or len(sys.argv) > 4:
        print("Uso: python3 generate-env.py <dev|prod> [--default] [--override-file=ARQUIVO]")
        print("")
        print("Argumentos:")
        print("  dev|prod                    Tipo de ambiente a gerar")
        print("  --default                   Usa domínio padrão 'queridodiario.local' sem interação")
        print("  --override-file=ARQUIVO     Arquivo com valores de produção para sobrescrever")
        print("")
        print("Comportamento do override:")
        print("  • SEM --default: Interativo para domínio + override aplicado ao final")
        print("  • COM --default: Domínio padrão + override aplicado ao final")
        print("")
        print("Exemplos:")
        print(
           "  python3 generate-env.py prod --override-file=prod.env        # Interativo + override"
        )
        print(
            "  python3 generate-env.py prod --default --override-file=prod.env  # Padrão + override"
        )
        print(
            "  python3 generate-env.py prod                                 # Apenas interativo"
        )
        sys.exit(1)

    env_type = sys.argv[1]
    use_default = False
    override_file = None

    # Processa argumentos opcionais
    for arg in sys.argv[2:]:
        if arg == "--default":
            use_default = True
        elif arg.startswith("--override-file="):
            override_file = arg.split("=", 1)[1]
        else:
            print(f"❌ Erro: argumento desconhecido '{arg}'")
            sys.exit(1)

    if env_type not in ["dev", "prod"]:
        print("❌ Erro: tipo deve ser 'dev' ou 'prod'")
        sys.exit(1)

    try:
        if use_default:
            print("🎯 Querido Diário - Gerador de Ambiente (Modo Padrão)")
        else:
            print("🎯 Querido Diário - Gerador Interativo de Ambiente")

        if override_file:
            print(f"📂 Arquivo de sobrescritas: {override_file}")

        print("=" * 50)
        print("")
        generate_env_file(env_type, use_default, override_file)
    except KeyboardInterrupt:
        print("\n\n❌ Operação cancelada pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
