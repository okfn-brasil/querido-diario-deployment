# Configurações Customizadas

> 📅 **Última atualização**: Setembro 2025 (Pós-refatoração)

Este documento explica como customizar configurações específicas para sua instalação do Querido Diário.

## Visão Geral da Nova Estrutura

Após a refatoração, o sistema foi drasticamente simplificado:

- **Desenvolvimento**: `make dev` gera automaticamente um `.env` funcional
- **Produção**: `make setup-env-prod` gera `.env` baseado em `templates/env.prod.sample`
- **Customização**: Edite diretamente o arquivo `.env` gerado

## Estrutura Simplificada

### 1. Template Base

O arquivo `templates/env.prod.sample` contém todas as variáveis necessárias com valores comentados ou padrão.

### 2. Geração Automática

```bash
# Para desenvolvimento (automático, funciona out-of-the-box)
make dev

# Para produção (requer edição manual após geração)
make setup-env-prod
```

### 3. Customização Manual

Após gerar o `.env`, edite diretamente com suas configurações:

```bash
# Editar configurações específicas
vim .env
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
DEBUG=1

# Produção - exemplo  
QD_BACKEND_SECRET_KEY=your-real-secret-key
POSTGRES_HOST=production-db.com
MAILJET_API_KEY=your-real-mailjet-key
```

### 3. Usar comandos normais

Os comandos aplicam automaticamente as sobrescritas:

```bash
# Desenvolvimento com domínio padrão
make setup-env-dev

# Desenvolvimento interativo  
make setup-env-dev-interactive

# Produção interativa
make setup-env-prod

# Produção com domínio padrão
make setup-env-prod-default
```

## Comandos simplificados

| Comando | Domínio | Override | Ambiente |
|---------|---------|----------|----------|
| `make setup-env-dev` | Padrão | Auto | .env |
| `make setup-env-dev-interactive` | Interativo | Auto | .env |
| `make setup-env-prod` | Interativo | Auto | .env.production |
| `make setup-env-prod-default` | Padrão | Auto | .env.production |

**🔍 "Auto"** = Aplicado automaticamente se `overrides.env` existir

## Vantagens do novo fluxo

- ✅ **Simplicidade**: Um único arquivo para todos os ambientes
- ✅ **Automático**: Detecta e aplica sobrescritas sem comandos especiais
- ✅ **Flexível**: Pode usar valores diferentes para dev/prod no mesmo arquivo
- ✅ **Opcional**: Se não existe `overrides.env`, funciona normalmente
- ✅ **Inteligente**: Não falha se arquivo não existir

## Exemplo prático

**1. Configuração inicial:**
```bash
cp templates/overrides.example overrides.env
```

**2. Configurar overrides.env:**
```bash
# Para desenvolvimento
POSTGRES_HOST=localhost
DEBUG=1

# Para produção  
QD_BACKEND_SECRET_KEY=minha-chave-secreta
MAILJET_API_KEY=minha-chave-mailjet
```

**3. Usar normalmente:**
```bash
# Desenvolvimento - usa POSTGRES_HOST=localhost e DEBUG=1
make setup-env-dev

# Produção - usa a chave secreta e mailjet configurados
make setup-env-prod
```

## Migração do sistema anterior

Se você tinha `production-overrides.env`, simplesmente renomeie:

```bash
mv production-overrides.env overrides.env
```

## Formato do arquivo

- Uma variável por linha: `CHAVE=VALOR`
- Comentários com `#` são ignorados
- Aspas são removidas automaticamente
- Funciona para qualquer ambiente (dev/prod)

## Segurança

⚠️ **IMPORTANTE**:
- Adicione `overrides.env` ao `.gitignore`
- Nunca commite valores de produção no repositório
- Use gerenciamento seguro de secrets em produção