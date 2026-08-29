# Migração de bancos: ambiente antigo (VPS Docker Compose) → Revoada (k8s/CNPG)

Automação para migrar os dados do ambiente de produção antigo
(`queridodiario.ok.org.br`, Postgres 12 + OpenSearch em Docker Compose numa
VPS) para o cluster Revoada (CCSL/IME-USP), onde o Postgres é gerenciado pelo
CloudNativePG e o OpenSearch roda como StatefulSet in-cluster.

Ver plano completo de contexto/decisões em
`docs/plano-migracao-bancos.md` (se existir) ou no histórico de conversa que
gerou este diretório.

**Escopo:** PostgreSQL (3 bancos, renomeados no destino) + índice OpenSearch.
Arquivos em S3 ficam de fora (já tratados via `docs/storage-migration-cloudfront.md`).

**Onde rodar:** todos os scripts assumem execução **de dentro da VPS antiga**
(os containers Postgres/OpenSearch ficam lá; o cluster novo é acessado via
WireGuard + kubectl a partir da VPS).

## Mapeamento de bancos

| Origem (container) | DB antigo | DB novo (CNPG) |
|---|---|---|
| `postgres_queridodiario` | `queridodiariodb` | `queridodiario` |
| `postgres_queridodiariobackend` | `queridodiariobackend` | `backend` |
| `postgres_receita` | `qd_receita` | `companies` |

Índice OpenSearch: `queridodiario` → `queridodiario` (mesmo nome, hosts e auth diferentes).

## Ordem de execução

### Fase 0 — Preparo (uma vez)
Siga `00-setup-vps.md`: WireGuard, kubectl, `opensearch-py`, variáveis de ambiente.

### Fase 1 — Ensaio a quente (ambiente antigo continua no ar)

```bash
# Postgres — primeira passada, só para medir tempo/tamanho e validar credenciais
./01-dump-postgres.sh

# OpenSearch — pode rodar a quente, é só leitura na origem
python3 opensearch-migrate.py --dry-run   # confere contagens
python3 opensearch-migrate.py             # migração real (idempotente por _id)
```

Recomendado: testar o fluxo de restore contra o overlay `dev` local
(`make k8s-local-up`) antes de tocar no Revoada real.

### Fase 2 — Janela de manutenção

Pausar o que escreve no Postgres antigo (celery-worker/celery-beat, cron dos
raspadores, tráfego de API com escrita). Confirmar com `docker exec <container>
psql ... -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"`
que não há transações de escrita em andamento.

### Fase 3 — Dump/restore final

```bash
./01-dump-postgres.sh          # dump final, pós-freeze (sobrescreve os *-latest.dump)
./02-restore-postgres.sh       # restaura no Revoada (recusa sobrescrever banco não-vazio;
                                # use --force só se souber o que está fazendo)
./03-verify-postgres.sh        # gate: contagens origem vs destino
python3 opensearch-migrate.py  # reexecuta — delta pequeno, idempotente por _id
```

`03-verify-postgres.sh` e a comparação final de contagem do
`opensearch-migrate.py` são o **gate formal**: só prosseguir para o cutover se
ambos passarem sem divergência.

### Fase 4 — Cutover

1. Confirmar que os secrets/env vars da aplicação nova (`app-secret`,
   `postgres-app`) já apontam para os serviços do cluster (`postgres-rw`,
   `opensearch`) — não é feito por estes scripts, é a configuração normal do
   `k8s/overlays/production-local/`.
2. Smoke test manual: abrir a API/frontend novos e conferir dados recentes.
3. Trocar DNS de `queridodiario.ok.org.br` (ou apontar o domínio definitivo)
   para o Revoada.
4. **Rollback**: manter o ambiente antigo intacto e no ar (sem aceitar novas
   escritas) por alguns dias após o corte, como plano B.

## Variáveis de ambiente usadas pelos scripts

| Variável | Usado em | Descrição |
|---|---|---|
| `OLD_PG_QD_USER` / `OLD_PG_QD_PASSWORD` | 01, 03 | Credenciais do container `postgres_queridodiario` |
| `OLD_PG_BACKEND_USER` / `OLD_PG_BACKEND_PASSWORD` | 01, 03 | Credenciais do container `postgres_queridodiariobackend` |
| `OLD_PG_RECEITA_USER` / `OLD_PG_RECEITA_PASSWORD` | 01, 03 | Credenciais do container `postgres_receita` |
| `OLD_PG_USER` | 01, 03 | Fallback se as variáveis específicas acima não estiverem definidas |
| `KUBECONFIG` | 02, 03 | Aponta para o kubeconfig do Revoada |
| `QD_NAMESPACE` | 02, 03 | Default: `querido-diario` |
| `QD_PG_SERVICE` | 02, 03 | Default: `postgres-rw` |
| `QD_RESTORE_HELPER_POD` / `QD_RESTORE_HELPER_IMAGE` | 02, 03 | Nome/imagem do pod auxiliar usado pro `pg_restore`/`psql` dentro do cluster (default: `pg-restore-helper`/`pg-verify-helper`, `postgres:15`) |
| `DRY_RUN=true` | 01, 02 | Mostra os comandos sem executar |
| `OLD_OPENSEARCH_HOST/USER/PASSWORD/INDEX` | opensearch-migrate.py | Origem |
| `NEW_OPENSEARCH_HOST/USER/PASSWORD/INDEX` | opensearch-migrate.py | Destino (via port-forward) |

## Segurança

- Nenhum script tem credencial hardcoded — tudo vem de variáveis de ambiente.
- Os dumps gerados em `./dumps/` **contêm dados reais de produção** — já estão
  cobertos por `scripts/db-migration/dumps/` no `.gitignore` raiz, mas
  confirme com `git status` antes de qualquer commit nesta pasta.
- Apague os dumps da VPS após confirmar o cutover (Fase 4) e o período de
  rollback ter passado.
