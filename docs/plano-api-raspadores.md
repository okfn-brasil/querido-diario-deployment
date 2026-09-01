# Plano técnico — Eliminar acesso direto ao banco pelos raspadores via API

**Status:** proposta (investigação concluída)
**Data:** 2026-07-08
**Repositórios afetados:** `querido-diario-api`, `querido-diario` (raspadores), `querido-diario-deployment`

---

## 1. Contexto e objetivo

Hoje os raspadores rodando na Zyte (Scrapy Cloud) recebem a string de conexão
`QUERIDODIARIO_DATABASE_URL` como *job setting* e acessam o PostgreSQL de produção
diretamente pela internet. Isso implica:

- Expor o PostgreSQL publicamente (ou via túnel) para a Zyte;
- Credenciais completas de escrita no banco distribuídas em job settings da Zyte;
- Acoplamento do schema do banco ao código dos raspadores (SQLAlchemy models duplicados).

O objetivo é substituir esse acesso por dois endpoints na API (FastAPI), protegidos por
API Key, de modo que o banco só precise ser acessível de dentro do cluster.

---

## 2. Inventário do acesso atual ao banco pelos raspadores

A investigação encontrou **mais pontos de acesso** do que os dois citados inicialmente.
Todos em `querido-diario/querido_diario_raspadores/`:

| Arquivo | Operação | Tabela(s) |
|---|---|---|
| `gazette/utils/database.py` — `get_enabled_spiders()` | Leitura | `querido_diario_spiders` |
| `gazette/pipelines.py` — `SQLDatabasePipeline.process_item()` | Escrita (INSERT) | `gazettes` |
| `gazette/pipelines.py` — `SQLDatabasePipeline.open_spider()` → `initialize_database()` | Escrita (DDL + seed) | `territories`, `querido_diario_spiders`, `territory_spider_map` |
| `gazette/extensions.py` — `StatsPersist` (extensão Scrapy) | Escrita (INSERT + DDL) | `job_stats` |
| `gazette/monitors.py` — `ComparisonBetweenSpiderExecutionsMonitor` | Leitura | `job_stats` |
| `scheduler.py` — `schedule_enabled_spiders`, `enable_spider`, `disable_spider` | Leitura/Escrita | `querido_diario_spiders` |
| `gazette/commands/qd-list-enabled.py` | Leitura | `querido_diario_spiders` |

Pontos de atenção descobertos:

1. **`SQLDatabasePipeline.open_spider()` tem efeito colateral relevante**: a cada abertura
   de spider ele chama `initialize_database()`, que cria as tabelas (`create_all`), popula
   `territories` a partir do CSV embarcado e **registra spiders novos/modificados** em
   `querido_diario_spiders`. Ou seja, o cadastro de spiders no banco é feito hoje pelos
   próprios raspadores em produção. Esse fluxo precisa de um novo dono (ver §7.3).
2. **`job_stats` também é acesso direto ao banco** (extensão + monitor Spidermon). Se o
   objetivo é eliminar *todo* acesso direto, esses pontos precisam de endpoints próprios
   (proposto como fase 2, §7.4). Se ficarem de fora, a `QUERIDODIARIO_DATABASE_URL`
   continua tendo que ser distribuída à Zyte e o ganho de segurança é parcial.
3. **Idempotência já existe no schema**: `gazettes` tem
   `UniqueConstraint("territory_id", "date", "file_checksum")` — o pipeline atual trata
   `SQLAlchemyError` como aviso e segue. O endpoint POST pode explorar isso para ser
   idempotente (upsert / `ON CONFLICT DO NOTHING`).
4. **`source_text` viaja vazio na raspagem**: o texto é extraído depois pelo
   data-processing (que faz `UPDATE` na linha). O payload do POST é só metadado — pequeno.

---

## 3. Viabilidade: a API já acessa o banco `queridodiariodb`? **Sim.**

A API (FastAPI) mantém **duas conexões PostgreSQL** via `psycopg2`
(`querido-diario-api/database/postgresql.py`):

| Conexão | Env vars | Banco | Uso atual |
|---|---|---|---|
| Companies | `POSTGRES_COMPANIES_*` | `qd_receita` | `/company/*` |
| **Aggregates** | `POSTGRES_AGGREGATES_*` | **`queridodiariodb`** | `/aggregates/*` |

Confirmado nos manifestos deste repositório:

- `k8s/base/configmap-app.yaml`: `POSTGRES_AGGREGATES_DB: "queridodiariodb"`;
- `k8s/base/api/deployment.yaml` (linhas 56–70): `POSTGRES_AGGREGATES_HOST/USER/PASSWORD`
  vêm das chaves **`QD_DATA_DB_*`** do secret `app-secret` — as mesmas credenciais do
  banco de dados usado pelo data-processing e pelos raspadores.

Ou seja: **a API já conecta exatamente no banco onde vivem as tabelas `gazettes`,
`territories` e `querido_diario_spiders`**, com credenciais que hoje já permitem leitura.
É preciso apenas garantir que o usuário do banco tenha `INSERT` em `gazettes`
(em produção as credenciais `QD_DATA_DB_*` são as mesmas do owner do banco, então já tem).

Observações sobre a camada de dados da API:

- `PostgreSQLDatabase._select()` abre uma conexão nova por query e não faz `commit`
  (só leitura). Para os novos endpoints será preciso um método `_execute()`/`_insert()`
  com `commit` — mudança pequena e localizada.
- A API segue um padrão hexagonal informal (interface por domínio + gateway + wiring em
  `main/__main__.py`). Os novos endpoints devem seguir o mesmo padrão (novo módulo).

---

## 4. Endpoints propostos

Prefixo sugerido: `/api/scraper/*` (agrupa tudo que é interno/autenticado e facilita
regras de rate-limit/firewall no Traefik depois). Alternativa mais simples: rotas planas
`/spiders` e `/gazettes` (POST). O plano usa o prefixo.

### 4.1 `GET /api/scraper/spiders` — spiders habilitados

Substitui `get_enabled_spiders()`.

**Query params** (espelham a assinatura atual):

| Param | Tipo | Obrigatório | Semântica (igual à query SQL atual) |
|---|---|---|---|
| `start_date` | `date` | não | filtra `date_from <= start_date` |
| `end_date` | `date` | não | filtra `date_to >= end_date` |

**Response `200`:**

```json
{
  "total_spiders": 412,
  "spiders": [
    {"spider_name": "sp_campinas", "date_from": "2015-01-01", "date_to": null},
    {"spider_name": "ba_salvador", "date_from": "2010-06-14", "date_to": null}
  ]
}
```

Retornar objetos (e não só nomes) custa o mesmo e dá margem para o scheduler evoluir;
o cliente pode usar só `spider_name`.

**SQL na API** (novo gateway, mesma conexão aggregates):

```sql
SELECT spider_name, date_from, date_to
FROM querido_diario_spiders
WHERE enabled IS TRUE
  AND (%(start_date)s IS NULL OR date_from <= %(start_date)s)
  AND (%(end_date)s IS NULL OR date_to >= %(end_date)s)
ORDER BY spider_name;
```

### 4.2 `POST /api/scraper/gazettes` — persistir gazette raspada

Substitui o INSERT do `SQLDatabasePipeline`. Aceita **uma gazette por chamada**
(ver §6.2 sobre batch).

**Request body** (Pydantic, espelhando o model SQLAlchemy `Gazette`):

```python
class ScrapedGazetteBody(BaseModel):
    territory_id: str = Field(..., min_length=7, max_length=7, pattern=r"^\d{7}$")
    date: date
    scraped_at: datetime
    file_path: str
    file_url: str
    file_checksum: str
    edition_number: Optional[str] = None
    is_extra_edition: Optional[bool] = None
    power: Optional[str] = None          # "executive" | "legislative" | ...
    source_text: Optional[str] = None    # normalmente vazio; preenchido pelo data-processing
```

**Responses:**

| Código | Situação |
|---|---|
| `201` | inserida — `{"status": "created", "gazette_id": 123}` |
| `200` | duplicada (conflito na unique constraint) — `{"status": "duplicate"}` |
| `422` | payload inválido (validação Pydantic automática) |
| `404` | `territory_id` inexistente em `territories` (FK) |
| `401`/`403` | API Key ausente/inválida |

**SQL na API** — idempotente, aproveitando a unique constraint existente:

```sql
INSERT INTO gazettes (
    source_text, date, edition_number, is_extra_edition, power,
    file_checksum, file_path, file_url, scraped_at, created_at,
    territory_id, processed
) VALUES (
    %(source_text)s, %(date)s, %(edition_number)s, %(is_extra_edition)s, %(power)s,
    %(file_checksum)s, %(file_path)s, %(file_url)s, %(scraped_at)s, NOW(),
    %(territory_id)s, FALSE
)
ON CONFLICT (territory_id, date, file_checksum) DO NOTHING
RETURNING id;
```

`RETURNING id` vazio ⇒ duplicata ⇒ `200 duplicate`. `processed = FALSE` garante que o
data-processing (que consome `processed IS FALSE`) enxerga a nova gazette — comportamento
idêntico ao pipeline atual.

### 4.3 Wiring na API (padrão do projeto)

Estrutura proposta no repositório `querido-diario-api`:

```
scraper/                      # novo módulo de domínio
├── __init__.py               # create_scraper_interface(), ScraperAccessInterface
└── scraper_access.py         # regras (validações, mapeamentos)
database/postgresql.py        # + classe PostgreSQLDatabaseScraper (INSERT/SELECT acima)
api/api.py                    # + rotas, schemas Pydantic e dependência de API Key
main/__main__.py              # + create_scraper_database_interface(aggregates creds)
config/config.py              # + scraper_api_keys
```

A `PostgreSQLDatabaseScraper` reutiliza host/user/password/db das env vars
`POSTGRES_AGGREGATES_*` — **nenhuma variável nova de banco é necessária**.

---

## 5. Autenticação por API Key

### 5.1 Implementação na API (dependência por rota — não middleware)

Dependência FastAPI com `APIKeyHeader` é o mecanismo idiomático: fica documentado no
OpenAPI/Swagger (botão "Authorize"), aplica-se só às rotas do scraper e não interfere
nas rotas públicas.

```python
# api/auth.py (novo)
import secrets
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from config.config import load_configuration

config = load_configuration()
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def validate_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing API Key")
    for valid_key in config.scraper_api_keys:
        if valid_key and secrets.compare_digest(api_key, valid_key):
            return api_key
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid API Key")
```

```python
# api/api.py — uso nas rotas
@app.post(
    "/api/scraper/gazettes",
    status_code=201,
    dependencies=[Security(validate_api_key)],
    tags=["Scraper (internal)"],
)
async def create_scraped_gazette(body: ScrapedGazetteBody):
    ...
```

```python
# config/config.py — múltiplas chaves separadas por vírgula (permite rotação sem downtime)
self.scraper_api_keys = Configuration._load_list("QUERIDO_DIARIO_SCRAPER_API_KEYS", [])
```

Pontos de projeto:

- `secrets.compare_digest` evita timing attack;
- Lista de chaves (CSV na env var) permite **rotação**: adiciona chave nova → atualiza a
  Zyte → remove chave antiga;
- Se `QUERIDO_DIARIO_SCRAPER_API_KEYS` estiver vazia, as rotas devem responder `503`
  (feature desligada), nunca liberar sem autenticação;
- Geração da chave: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.

### 5.2 Mudanças neste repositório (deployment)

- `k8s/base/secret-app.yaml` (template): adicionar `QUERIDO_DIARIO_SCRAPER_API_KEYS: "<CHANGE_ME>"`;
- `k8s/base/api/deployment.yaml`: novo env var via `secretKeyRef`;
- `k8s/overlays/dev/patch-secret-dev.yaml`: chave fixa de dev (ex.: `"dev-scraper-key"`);
- Produção: acrescentar a chave ao secret `app-secret` existente (comando `kubectl create
  secret ... --from-literal=QUERIDO_DIARIO_SCRAPER_API_KEYS='...'`, documentado no CLAUDE.md/README);
- Opcional: `Middleware` de rate-limit do Traefik nas rotas `/api/scraper/*`
  (já há middlewares em `k8s/base/traefik-middlewares.yaml`) — defesa extra contra abuso
  de chave vazada.

---

## 6. Mudanças nos raspadores (`querido-diario/querido_diario_raspadores`)

### 6.1 Novo cliente HTTP

A dependência `requests` já está no `pyproject.toml` como dependência direta. Novo
módulo:

```python
# gazette/utils/api_client.py (novo)
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class QueridoDiarioAPIClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["X-API-Key"] = api_key
        retry = Retry(
            total=5,
            backoff_factor=2,                      # 2s, 4s, 8s, 16s, 32s
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],       # POST é idempotente (ON CONFLICT)
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def get_enabled_spiders(self, start_date=None, end_date=None):
        params = {}
        if start_date:
            params["start_date"] = str(start_date)
        if end_date:
            params["end_date"] = str(end_date)
        resp = self.session.get(
            f"{self.base_url}/api/scraper/spiders", params=params, timeout=self.timeout
        )
        resp.raise_for_status()
        return [s["spider_name"] for s in resp.json()["spiders"]]

    def post_gazette(self, gazette: dict) -> dict:
        resp = self.session.post(
            f"{self.base_url}/api/scraper/gazettes", json=gazette, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()
```

O retry com backoff **só é seguro porque o POST é idempotente** no servidor
(`ON CONFLICT DO NOTHING`) — um retry após timeout de resposta não duplica linha.

### 6.2 Arquivo a arquivo

| Arquivo | Mudança |
|---|---|
| `gazette/settings.py` | Novas settings: `QUERIDODIARIO_API_URL` e `QUERIDODIARIO_API_KEY` (via `decouple.config`). Manter `QUERIDODIARIO_DATABASE_URL` **apenas** enquanto job_stats (fase 2) não migrar. Trocar `SQLDatabasePipeline` por `ApiPipeline` em `ITEM_PIPELINES` (mesma posição 500, após a validação do Spidermon). |
| `gazette/pipelines.py` | Nova classe `ApiPipeline`: mesma lógica de montagem do item do `SQLDatabasePipeline.process_item()` (incl. pular arquivos `status == "uptodate"`), mas chamando `client.post_gazette()`. **Sem** o `initialize_database()` no `open_spider` (ver §7.3). Erros HTTP após esgotar retries: logar `warning` e seguir (comportamento atual) — o item continua recuperável pelo log da Zyte. |
| `gazette/utils/database.py` | `get_enabled_spiders()` passa a delegar ao `QueridoDiarioAPIClient` (mantendo a assinatura, para não quebrar `scheduler.py` e `qd-list-enabled.py`), ou é substituído e os chamadores atualizados. |
| `scheduler.py` | `schedule_enabled_spiders` / `last_month_schedule_enabled_spiders` / `schedule_all_spiders_by_date` usam o client. Job settings enviados à Zyte trocam `QUERIDODIARIO_DATABASE_URL` por `QUERIDODIARIO_API_URL` + `QUERIDODIARIO_API_KEY`. Os comandos `enable_spider`/`disable_spider` rodam fora da Zyte (máquina de operação) — podem continuar via banco, ou ganhar um `PATCH /api/scraper/spiders/{name}` (opcional, fase 2). |
| `gazette/commands/qd-list-enabled.py` | Passa a usar o client (via `get_enabled_spiders` mantido). |
| `gazette/extensions.py` (`StatsPersist`) e `gazette/monitors.py` | **Fase 2** (§7.4). Até lá continuam usando `QUERIDODIARIO_DATABASE_URL`; alternativa provisória: desabilitar `StatsPersist`/`ComparisonBetweenSpiderExecutionsMonitor` quando a URL do banco não estiver definida (ambos já toleram configuração parcial). |

### 6.3 Desenvolvimento local

Hoje o default é `sqlite:///querido-diario.db` — zero-config para contribuidores. Para
manter isso, o `ApiPipeline` deve ser **no-op quando `QUERIDODIARIO_API_URL` não estiver
definida** (como o `SQLDatabasePipeline` já faz com a URL do banco), e opcionalmente
manter o `SQLDatabasePipeline`+sqlite como fallback local durante a transição. No kind
local deste repositório, apontar para `http://api.queridodiario.local`.

---

## 7. Riscos e considerações

### 7.1 Volume e desempenho

- Ordem de grandeza: centenas de spiders habilitados, tipicamente 1 edição/dia por
  município na execução diária (`start=ontem`) ⇒ **centenas a poucos milhares de POSTs/dia**,
  diluídos ao longo das execuções. Trivial para FastAPI + PostgreSQL.
- Payload pequeno (`source_text` vazio na raspagem).
- **Batch não é necessário** para a carga diária. O cenário que muda a conta é o
  *full crawl* (recrawl histórico de um município: milhares de itens em uma execução).
  Ainda assim são POSTs sequenciais dentro do fluxo do Scrapy (I/O bound, ~10–50 ms cada
  em rede boa). Se virar gargalo, evoluir para `POST /api/scraper/gazettes/batch`
  (lista de até N itens, `execute_values` + `ON CONFLICT`) — a API pode nascer já com as
  duas rotas, custo marginal baixo.
- A conexão psycopg2 da API é criada por request (sem pool). Para esse volume está ok;
  se necessário, introduzir `psycopg2.pool.SimpleConnectionPool` depois.

### 7.2 Falhas e confiabilidade

- **Retry**: client com backoff exponencial (§6.1) cobre indisponibilidade curta da API.
- **Idempotência**: garantida pelo `ON CONFLICT DO NOTHING` sobre a unique constraint
  existente — retries e re-execuções de spiders não duplicam dados.
- **API fora do ar durante um job**: hoje, se o banco está fora, o item também se perde
  (o pipeline atual só loga warning). O comportamento proposto é equivalente. Mitigações:
  monitor do Spidermon já alerta no Discord; re-executar o spider do dia recupera tudo
  (raspagem + upload S3 são refeitos, inserts são idempotentes).
- **Nova dependência de disponibilidade**: raspadores passam a depender da API pública.
  A API já tem liveness/readiness probes e fica atrás do Traefik; vale acompanhar se as
  janelas de deploy da API colidem com o horário do scheduler.
- **Ordem dos middlewares**: manter `ApiPipeline` após `ItemValidationPipeline` (500),
  para só enviar itens válidos — igual hoje.

### 7.3 Registro de spiders/territories (efeito colateral do pipeline atual)

`initialize_database()` (chamado hoje em **todo** `open_spider` em produção) cria tabelas,
popula `territories` e registra spiders novos. Com a remoção do pipeline SQL, esse fluxo
precisa de novo dono. Opções:

1. **Recomendada**: mover para um passo administrativo fora da Zyte — comando/CI no repo
   dos raspadores (`scrapy qd-register-spiders`) executado no deploy dos raspadores, com
   acesso ao banco a partir de ambiente controlado (ou um endpoint autenticado
   `POST /api/scraper/spiders/sync` que recebe o mapa spider→territory→date_from);
2. Job k8s neste repositório (semelhante aos init-jobs de dev).

Sem isso, spiders novos nunca aparecem em `querido_diario_spiders` e não são agendados.
**Esse é o principal gotcha do projeto** — o INSERT de gazettes é a parte fácil.

### 7.4 Fase 2 — `job_stats` (para eliminar 100% do acesso direto)

- `POST /api/scraper/job-stats` (grava o JSON de stats ao fim do job — `StatsPersist`);
- `GET /api/scraper/job-stats?spider=X&since=YYYY-MM-DD` (para o monitor de "dias sem
  gazettes" do Spidermon).

Só depois disso a `QUERIDODIARIO_DATABASE_URL` pode sair dos job settings da Zyte e o
firewall do PostgreSQL pode fechar para a internet — que é o ganho de segurança final.

### 7.5 Segurança

- API Key em job setting da Zyte tem exposição similar à senha do banco hoje, **mas** o
  raio de dano é muito menor: a chave só permite listar spiders e inserir gazettes
  (idempotente, validado), não ler/alterar/apagar dados nem acessar outras tabelas;
- Rotação simples (lista de chaves, §5.1);
- Rate-limit Traefik em `/api/scraper/*` como defesa em profundidade;
- As rotas aparecem no Swagger público (`/docs`). Se preferir ocultar:
  `include_in_schema=False` nas rotas — trade-off com a documentação para contribuidores.

### 7.6 Compatibilidade / rollout

Sequência sem downtime:

1. Deploy da API com os novos endpoints (+ secret com a API Key) — nada muda para os
   raspadores;
2. Smoke test manual (`curl -H "X-API-Key: ..."`) em produção;
3. Deploy dos raspadores na Zyte com o client, mantendo pipeline SQL como fallback
   desligado; atualizar job settings do scheduler;
4. Acompanhar alguns dias (contagem diária de inserts em `gazettes` vs. relatório do
   Spidermon no Discord);
5. Remover código SQL de spiders/scheduler (fase 1) e depois job_stats (fase 2);
6. Fechar o acesso externo ao PostgreSQL.

---

## 8. Resumo executivo

| Pergunta | Resposta |
|---|---|
| A API acessa o banco certo? | **Sim** — a conexão "aggregates" já aponta para `queridodiariodb` (mesmas credenciais `QD_DATA_DB_*` usadas pelo data-processing). Nenhuma env var nova de banco é necessária. |
| É viável? | Sim, com esforço moderado: ~1 módulo novo + 2 rotas na API; ~3 arquivos alterados nos raspadores; 3 manifestos neste repositório. |
| Batch? | Desnecessário para a carga diária; opcionalmente criar rota `/batch` já na primeira versão para full crawls. |
| Maior risco | O efeito colateral de `initialize_database()` (registro de spiders/territories) precisa de novo dono antes de desligar o pipeline SQL (§7.3). |
| Elimina 100% do acesso direto? | Só após a fase 2 (`job_stats` — extensão StatsPersist e monitor Spidermon), sem a qual a URL do banco continua indo para a Zyte. |
