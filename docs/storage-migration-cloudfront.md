# Storage Migration & CloudFront Setup

> 📅 **Criado em**: Janeiro 2025  
> 🎯 **Objetivo**: Guia para migrar storage providers e implementar CloudFront/CDN

## Visão Geral

Este documento explica como migrar o storage de arquivos do Querido Diário e implementar um CDN (CloudFront) na frente do storage, **sem precisar reprocessar os dados existentes**.

## Contexto

Anteriormente, o sistema armazenava URLs completas no OpenSearch:
```json
{
  "file_raw_txt": "https://queridodiario.nyc3.digitaloceanspaces.com/path/file.txt"
}
```

Isso causava problemas:
- ❌ Impossível trocar de storage provider sem reprocessamento
- ❌ Impossível adicionar CDN sem reprocessamento
- ❌ Migração = dias reprocessando milhões de registros

## Solução Implementada

Agora o sistema suporta:
1. **Armazenar paths relativos** (dados novos)
2. **Substituir base URL dinamicamente** (dados antigos)
3. **Configurar endpoint via variável de ambiente**

## Variáveis de Ambiente

### `QUERIDO_DIARIO_FILES_ENDPOINT` (API)

Define o endpoint público para acesso aos arquivos.

**Exemplos:**
- CloudFront: `https://d1234567890.cloudfront.net`
- S3 direto: `https://bucket-name.s3.amazonaws.com`
- Digital Ocean: `https://bucket-name.nyc3.digitaloceanspaces.com`
- Dev local: `http://localhost:9000/queridodiariobucket`

### `USE_RELATIVE_FILE_PATHS` (Data Processing)

Controla como novos dados são armazenados.

**Valores:**
- `false` (padrão): URLs completas (legado)
- `true`: Paths relativos (recomendado)

### `REPLACE_FILE_URL_BASE` (API)

Habilita substituição automática de URLs antigas.

**Valores:**
- `false` (padrão): Retorna URLs como estão
- `true`: Extrai path e reconstrói com novo endpoint

**Suporta protocolos:**
- `http://`
- `https://`
- `s3://`

## Cenários de Migração

### Cenário 1: Migração Imediata (Digital Ocean → AWS + CloudFront)

**Objetivo:** Trocar para CloudFront sem reprocessamento.

**Passo 1:** Configure CloudFront apontando para S3

**Passo 2:** Configure API
```bash
# docker-compose.yml ou .env
QUERIDO_DIARIO_FILES_ENDPOINT=https://d1234567890.cloudfront.net
REPLACE_FILE_URL_BASE=true
```

**Passo 3:** Reinicie API
```bash
kubectl rollout restart deployment/api -n querido-diario
```

**Resultado:**
- ✅ URLs antigas automaticamente redirecionadas para CloudFront
- ✅ Zero downtime
- ✅ Zero reprocessamento
- ✅ Funciona imediatamente

---

### Cenário 2: Nova Instalação

**Objetivo:** Começar do jeito certo.

**Data Processing:**
```bash
USE_RELATIVE_FILE_PATHS=true
```

**API:**
```bash
QUERIDO_DIARIO_FILES_ENDPOINT=https://cdn.queridodiario.ok.org.br
REPLACE_FILE_URL_BASE=false
```

**Resultado:**
- ✅ Dados limpos desde o início
- ✅ Fácil trocar CDN no futuro
- ✅ Arquitetura correta

---

### Cenário 3: Migração Gradual

**Objetivo:** Migrar progressivamente.

**Fase 1:** API (imediato)
```bash
QUERIDO_DIARIO_FILES_ENDPOINT=https://cdn.example.com
REPLACE_FILE_URL_BASE=true
```

**Fase 2:** Data Processing (após validação)
```bash
USE_RELATIVE_FILE_PATHS=true
```

**Fase 3:** (Opcional) Bulk update no OpenSearch

Ver script de migração em: `FILE_URL_MIGRATION_GUIDE.md`

## Configuração do CloudFront

### Criar Distribution

```yaml
Origin:
  DomainName: querido-diario-bucket.s3.amazonaws.com
  OriginAccessIdentity: [criar OAI]
  
DefaultCacheBehavior:
  ViewerProtocolPolicy: redirect-to-https
  AllowedMethods: [GET, HEAD]
  CachedMethods: [GET, HEAD]
  Compress: true
  
  CachePolicyId: [use CachingOptimized]
  # Ou custom:
  MinTTL: 0
  DefaultTTL: 86400  # 1 dia
  MaxTTL: 31536000   # 1 ano (arquivos são imutáveis)

PriceClass: PriceClass_100  # Use All se precisar de edge locations globais

CustomErrorResponses:
  - ErrorCode: 403
    ResponseCode: 404
    # S3 retorna 403 para arquivos não encontrados
```

### Configurar S3 Bucket

1. **Criar OAI (Origin Access Identity)**
2. **Atualizar Bucket Policy:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontOAI",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::cloudfront:user/CloudFront Origin Access Identity [OAI-ID]"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::querido-diario-bucket/*"
    }
  ]
}
```

3. **Bloquear acesso público direto**

### Testar CloudFront

```bash
# Teste direto S3 (deve falhar se bucket estiver privado)
curl -I https://bucket-name.s3.amazonaws.com/path/file.txt

# Teste via CloudFront (deve funcionar)
curl -I https://d1234567890.cloudfront.net/path/file.txt
```

## Configuração no Kubernetes

As variáveis são definidas no `ConfigMap` (`k8s/base/configmap-app.yaml`) e no `Secret` (`app-secret`). Após alterar:

```bash
# Aplicar as mudanças
make k8s-apply-prod

# Ou forçar restart dos pods afetados
kubectl rollout restart deployment/api -n querido-diario
kubectl rollout restart deployment/data-processing -n querido-diario  # se aplicável
```

## Validação

### Teste 1: API retorna CloudFront URLs

```bash
curl -s "https://api.queridodiario.ok.org.br/gazettes?territory_ids=3304557" \
  | jq -r '.gazettes[0].txt_url'
```

**Esperado:** `https://d1234567890.cloudfront.net/...`

### Teste 2: Arquivo acessível

```bash
URL=$(curl -s "https://api.queridodiario.ok.org.br/gazettes?territory_ids=3304557" \
  | jq -r '.gazettes[0].txt_url')

curl -I "$URL"
```

**Esperado:** `HTTP/2 200`

### Teste 3: CloudFront Headers

```bash
curl -I "$URL" | grep -i "x-cache"
```

**Esperado após cache:** `X-Cache: Hit from cloudfront`

## Monitoramento

### Métricas CloudFront (CloudWatch)

```
Namespace: AWS/CloudFront
DistributionId: [seu-id]

Métricas importantes:
- CacheHitRate (alvo: > 90%)
- 4xxErrorRate (deve ser baixo)
- 5xxErrorRate (deve ser baixo)
- BytesDownloaded (economia vs S3 direto)
```

### Logs da API

Verificar erros de URL building:

```bash
kubectl logs -n querido-diario deploy/api -f | grep -i "file_url"
```

## Rollback

Se necessário reverter:

```bash
# Reverter ConfigMap/Secret e aplicar:
make k8s-apply-prod
kubectl rollout restart deployment/api -n querido-diario
```

## Custos Estimados

### Sem CloudFront (S3 Direto)

- Requests GET: $0.0004 por 1000 requests
- Data Transfer OUT: $0.09 por GB
- **Exemplo:** 1M requests/mês + 100GB = ~$409/mês

### Com CloudFront

- Requests: $0.0075 por 10000 requests (HIT no cache)
- Data Transfer: $0.085 por GB (primeiros 10TB)
- Cache Hit Rate: 95% típico
- **Exemplo:** 1M requests/mês + 100GB = ~$16/mês

**Economia:** ~95% 🎉

## Benefícios

### Performance
- ✅ Latência reduzida (~50%)
- ✅ Cache global (edge locations)
- ✅ Menos carga no origin

### Custos
- ✅ 70-95% de redução
- ✅ Menos requests ao S3
- ✅ Bandwidth mais barato

### Flexibilidade
- ✅ Trocar storage sem reprocessamento
- ✅ Migrar providers facilmente
- ✅ Testar novos CDNs

### Segurança
- ✅ Bucket S3 privado
- ✅ Acesso apenas via CloudFront
- ✅ HTTPS obrigatório

## Troubleshooting

### Problema: API retorna URLs antigas

**Solução:**
```bash
# Verificar configuração
kubectl exec -n querido-diario deploy/api -- env | grep FILES_ENDPOINT
kubectl exec -n querido-diario deploy/api -- env | grep REPLACE

# Após corrigir o ConfigMap/Secret, aplicar e reiniciar:
make k8s-apply-prod
kubectl rollout restart deployment/api -n querido-diario
```

### Problema: CloudFront retorna 403

**Causas possíveis:**
1. OAI não configurado
2. Bucket policy incorreto
3. Arquivo não existe

**Debug:**
```bash
# Verificar se arquivo existe no S3
aws s3 ls s3://bucket-name/path/to/file.txt

# Testar acesso direto (deve falhar se privado)
curl -I https://bucket-name.s3.amazonaws.com/path/to/file.txt

# Testar via CloudFront
curl -I https://d1234567890.cloudfront.net/path/to/file.txt
```

### Problema: Cache Hit Rate baixo

**Causas:**
- Query strings variáveis
- Headers dinâmicos
- Cache policy incorreto

**Solução:**
- Usar CachingOptimized policy
- Ignorar query strings desnecessárias
- Aumentar TTL

## Checklist de Implementação

### Preparação
- [ ] Backup dos dados atuais
- [ ] Documentar configuração atual
- [ ] Testar em ambiente staging

### CloudFront Setup
- [ ] Criar CloudFront Distribution
- [ ] Configurar OAI
- [ ] Atualizar S3 Bucket Policy
- [ ] Testar acesso a arquivo via CloudFront
- [ ] Configurar cache policy
- [ ] Configurar custom error responses

### Deployment
- [ ] Atualizar ConfigMap/Secret com novas variáveis
- [ ] `make k8s-apply-prod`
- [ ] `kubectl rollout restart deployment/api -n querido-diario`
- [ ] Monitorar logs: `kubectl logs -n querido-diario deploy/api -f`

### Validação
- [ ] Verificar URLs nas respostas da API
- [ ] Testar acesso aos arquivos
- [ ] Verificar CloudFront cache hit rate
- [ ] Comparar latência (antes/depois)
- [ ] Monitorar por 48h

### Otimização
- [ ] Habilitar `USE_RELATIVE_FILE_PATHS=true`
- [ ] Monitorar novos processamentos
- [ ] (Opcional) Bulk update dados antigos
- [ ] Documentar lições aprendidas

## Referências

- **Guia de migração completo:** `FILE_URL_MIGRATION_GUIDE.md`
- **Sumário da implementação:** `IMPLEMENTATION_SUMMARY.md`
- **Plano de refatoração:** `REFACTORING_PLAN_FILE_PATHS.md`
- **Documentação AWS CloudFront:** https://docs.aws.amazon.com/cloudfront/
- **Script de teste:** `test_file_url_building.py`

## Suporte

Para dúvidas ou problemas:

1. Verificar logs: `kubectl logs -n querido-diario deploy/api -f`
2. Testar com script: `python test_file_url_building.py`
3. Revisar variáveis de ambiente
4. Consultar troubleshooting acima
5. Verificar CloudFront metrics no CloudWatch

---

**Última atualização:** Janeiro 2025  
**Status:** ✅ Implementado e testado  
**Ambiente:** Desenvolvimento e Produção
