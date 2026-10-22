# Querido Diário — Kubernetes

Manifestos Kubernetes para a plataforma Querido Diário, gerenciados via [Kustomize](https://kustomize.io/) (embutido no `kubectl`).

## Estrutura

```
k8s/
├── base/                        # Recursos compartilhados entre overlays
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── configmap-app.yaml       # Variáveis não-sensíveis
│   ├── secret-app.yaml          # TEMPLATE — não versionar com valores reais
│   ├── traefik-middlewares.yaml # Middlewares Traefik (CORS, rate-limit, headers...)
│   ├── postgres/
│   │   ├── cluster.yaml         # CloudNativePG Cluster (PostgreSQL 15)
│   │   └── credentials-secret.yaml  # TEMPLATE — não versionar
│   ├── frontend/                # nginx servindo o app Angular
│   ├── api/
│   ├── backend/
│   ├── redis/
│   ├── apache-tika/
│   ├── celery-beat/
│   ├── celery-worker/
│   └── data-processing/
├── overlays/
│   ├── production/              # 2+ réplicas, 250Gi postgres, imagens fixas
│   └── dev/                     # kind local: infra embutida, limites menores
│       └── infra/
│           ├── postgres-credentials-dev.yaml
│           ├── opensearch.yaml  # StatefulSet single-node (índice criado pelo data-processing)
│           ├── garage.yaml      # Storage S3-compatível (Garage v2)
│           └── garage-webui.yaml
└── local/
    ├── kind-config.yaml
    └── traefik-values.yaml
```

Os scripts que orquestram o cluster local (`k8s_local_up.py`, `k8s_local_down.py`, `k8s_local_hosts.py`,
`k8s_local_data_processing.py`) ficam em `scripts/` na raiz do repositório — são invocados pelo
`Makefile` e rodam em Linux, macOS e Windows (Python puro, sem dependências externas).

## O que roda no cluster

| Serviço | Dev | Prod |
|---|---|---|
| Frontend (nginx/Angular) | ✓ | ✓ |
| API (FastAPI) | ✓ | ✓ |
| Backend (Django) | ✓ | ✓ |
| Celery Beat + Worker | ✓ | ✓ |
| Apache Tika | ✓ | ✓ |
| Redis | ✓ | ✓ |
| PostgreSQL (CloudNativePG) | ✓ (1 instância) | ✓ (3 instâncias) |
| OpenSearch | ✓ | ✓ (single-node, sem HA) |
| Garage (S3) | ✓ | externo (AWS S3) |

---

## Desenvolvimento local (kind)

### Pré-requisitos

- `docker`
- `kubectl` ≥ 1.24
- `python3` ≥ 3.9
- `kubectl`, `helm` e `kind` são instalados automaticamente pelos scripts Python se ausentes

### Subir o ambiente

```bash
make k8s-local-up
```

O script `scripts/k8s_local_up.py` (chamado por `make k8s-local-up`) é **idempotente** — pode ser executado múltiplas vezes. Ele:

1. Verifica/instala `kind` e `helm`
2. Cria o cluster kind `querido-diario-dev` (k8s 1.31)
3. Instala Traefik via Helm (DaemonSet + hostPort 80)
4. Pré-carrega imagens no nó kind (evita timeout)
5. Instala o CloudNativePG operator
6. Aplica `k8s/overlays/dev`
7. Aguarda todos os serviços ficarem prontos

### Configurar /etc/hosts

```bash
make k8s-local-hosts   # Linux/Mac: pede sudo; Windows: rode o terminal como Administrador
```

Ou manualmente:
```
127.0.0.1  queridodiario.local
127.0.0.1  api.queridodiario.local
127.0.0.1  backend-api.queridodiario.local
```

### Buildar o frontend

A imagem do frontend não é baixada do registry — é construída localmente a partir do código.

**Opção 1 — build com cache remoto (recomendado):**
```bash
make build-frontend              # buildx + cache do GHCR → :local no daemon Docker
kind load docker-image ghcr.io/okfn-brasil/querido-diario-frontend:local \
    --name querido-diario-dev    # carrega no cluster kind
kubectl rollout restart deployment/frontend -n querido-diario
```

**Opção 2 — build simples + kind load em um passo:**
```bash
make k8s-local-frontend-build   # docker build + kind load (~5min no primeiro run)
kubectl rollout restart deployment/frontend -n querido-diario
```

Por padrão busca o código em `../querido-diario-frontend`. Para outro caminho:
```bash
make build-frontend FRONTEND_DIR=/outro/caminho
make k8s-local-frontend-build FRONTEND_DIR=/outro/caminho
```

### Governos estaduais no `/cities` da API

O `censo.csv` embutido na imagem da API só lista municípios, então um território
de governo estadual (ex.: `3299999`, Espírito Santo) não aparece em `/cities` nem
na busca por nome do frontend, mesmo com diários indexados. No overlay dev, as
linhas de `k8s/overlays/dev/censo-estados.csv` são acrescentadas ao `censo.csv`
por um initContainer da API (`patch-api-censo-estados.yaml`).

Para incluir outro estado, adicione a linha no CSV (mesmas colunas do `censo.csv`)
e rode `make k8s-apply-dev`: o ConfigMap muda de nome e a API reinicia sozinha.

```bash
curl "http://api.queridodiario.local/cities?city_name=Espírito"
curl "http://api.queridodiario.local/cities/3299999"
```

Isso vale só para o ambiente local. Em produção o estado só aparece quando a
linha entrar no `censo.csv` publicado em `data.queridodiario.ok.org.br`.
### Rodar API, Backend e Data Processing com o código local

Por padrão o overlay dev usa as imagens `:latest` do GHCR para esses três serviços.
Para testar alterações locais (a partir do que estiver em checkout nos repositórios irmãos):

```bash
make k8s-local-api-build               # build + kind load + troca para :local + restart
make k8s-local-backend-build           # idem, para backend, celery-beat e celery-worker
make k8s-local-data-processing-build   # build + kind load; vale para o próximo job
make k8s-local-data-processing         # dispara um job já com a imagem local
```

Rode o target de novo a cada alteração no código. `make k8s-apply-dev` e
`make k8s-local-up` reaplicam o overlay e voltam os serviços para `:latest` —
basta rodar o target novamente para reapontar para `:local`.

Se o `requirements.txt` do Data Processing mudar, a imagem base também precisa
ser reconstruída (`make build-data-processing-base`).

### URLs locais

| URL | Serviço |
|---|---|
| http://queridodiario.local | Frontend |
| http://api.queridodiario.local | API |
| http://backend-api.queridodiario.local | Backend |
| http://queridodiario.local/queridodiariobucket/... | Arquivos dos diários (PDF/TXT), servidos pelo endpoint web do Garage |
| http://localhost:3909 | Garage Web UI (`make k8s-local-garage-ui`) |
| http://localhost:3000 | Grafana (`make k8s-local-monitoring` + `make k8s-local-grafana`, admin/admin) |

Os arquivos dos diários só abrem no navegador depois que o `make k8s-local-up`
habilita a leitura pública do bucket (`garage bucket website --allow`). Em um
cluster criado antes dessa rota, rode `make k8s-local-up` de novo; os diários
que já estavam indexados continuam com a URL antiga (`http://garage:3900/...`)
até serem reprocessados.

### Comandos úteis

```bash
make k8s-local-status            # status dos pods
make k8s-local-garage-ui         # port-forward para o Garage Web UI
make k8s-local-data-processing   # executa data-processing manualmente
make k8s-local-monitoring        # sobe Prometheus + Grafana + Pushgateway (namespace monitoring)
make k8s-local-grafana           # port-forward para o Grafana
make k8s-local-down              # destroi o cluster
```

### Monitoramento (Prometheus + Grafana)

Opcional, fora do `make k8s-local-up` porque pesa ~1 GB de RAM. Com o cluster
de pé:

```bash
make k8s-local-monitoring   # kube-prometheus-stack + Pushgateway no namespace monitoring
make k8s-local-grafana      # http://localhost:3000 (admin / admin)
```

Se a porta 3000 já estiver em uso, rode `make k8s-local-grafana GRAFANA_PORT=3001`.

O dashboard *Querido Diário / Pipeline* mostra a vazão (`qd_gazettes_processed_total`
por `mode` e `status`), o p50/p95 do tempo por diário e da latência coleta →
indexado, a profundidade da fila e da DLQ (Parte C), as réplicas do
`extraction-worker` e CPU/memória por pod. A primeira linha traz os números da
última execução do CronJob: o Pushgateway substitui os valores a cada push, então
nos gráficos baseados em `rate()` cada execução aparece só como um pico. O JSON
fica em `k8s/local/dashboards/qd-pipeline.json` e vira um ConfigMap com a label
`grafana_dashboard: "1"`; depois de editar no Grafana, exporte o JSON por cima do
arquivo e rode `make k8s-local-dashboards`. Os painéis da fila esperam que o
`redis_exporter` do `redis-queue` exporte o tamanho das listas com
`REDIS_EXPORTER_CHECK_SINGLE_KEYS=db0=extraction,db0=qd:extraction:dead`.

Os values ficam em
`k8s/local/monitoring-values.yaml`: o Prometheus coleta todos os
`ServiceMonitor`/`PodMonitor` do cluster e o Grafana carrega dashboards de
ConfigMaps com a label `grafana_dashboard`. O Pushgateway
(`pushgateway-prometheus-pushgateway.monitoring:9091`) recebe métricas de
processos batch, como o CronJob `data-processing`: no overlay dev o
`PUSHGATEWAY_URL` do `app-config` já aponta para ele, e cada execução
(`make k8s-local-data-processing`) envia as séries `qd_*` ao fim do pipeline.

### Fila de extração (KEDA)

Alternativa ao CronJob `data-processing` (ADR-0009/0010 do
`querido-diario-estados`): um Redis dedicado (`redis-queue`) recebe o id de
cada diário não processado e workers (`extraction-worker`, cada um com o Tika
como sidecar) processam um diário por vez. O KEDA escala os workers pelo
tamanho da fila, de 0 até o teto (2 no overlay `dev-queue`, para caber no
Docker de um notebook). Os manifests ficam no componente
`k8s/components/queue-pipeline`, incluído pelo overlay `k8s/overlays/dev-queue`;
o overlay `dev` continua sendo o baseline.

A imagem `:tcc-fila` não é publicada no GHCR. No `querido-diario-data-processing`:

```bash
make -C ../querido-diario-deployment build-data-processing-base   # base:local
docker buildx build --load --build-arg BASE_TAG=local \
  -t ghcr.io/okfn-brasil/querido-diario-data-processing:tcc-fila .
```

Com o cluster de pé:

```bash
make k8s-local-queue        # instala o KEDA, carrega a imagem e aplica o dev-queue
kubectl create job --from=cronjob/enqueue-extraction enqueue-manual -n querido-diario
kubectl get scaledobject,deployment/extraction-worker -n querido-diario -w
make k8s-local-queue-down   # remove a fila e volta ao CronJob (overlay dev)
```

O `enqueue-extraction` roda a cada 5 min e o `themes-from-queue` (excertos
temáticos) a cada hora. Os PodMonitors da fila ficam em
`k8s/components/queue-pipeline/monitoring`: o `make k8s-local-queue` só os
aplica se o monitoramento já estiver instalado. Fora do kind, inclua também o
componente `queue-pipeline-opensearch-ca` (CA interna do OpenSearch).

### Troubleshooting

**`ctr: content digest sha256:... not found` ao carregar imagens no kind (Mac/Windows)**

Bug conhecido do `kind` com o Docker Desktop quando a opção **"Use containerd for
pulling and storing images"** está habilitada (Settings > General). Com ela ativa,
um `docker pull` sem `--platform` explícito guarda a manifest-list completa
(referências a *todas* as plataformas de uma imagem multi-arch), mas só baixa os
blobs da plataforma local. O `kind load docker-image` usa
`ctr images import --all-platforms` e falha tentando importar blobs que nunca
foram baixados.

`scripts/k8s_local_up.py` já tenta se recuperar sozinho (descarta a imagem em
cache local e repuxa fixando `--platform`) e não trava o `make k8s-local-up` por
causa disso — os pods conseguem puxar a imagem diretamente da internet como
fallback, só um pouco mais lento. Se o aviso persistir, desabilite a opção acima
em Docker Desktop e reinicie o Docker.

---

## Deploy de produção

### Pré-requisitos no cluster

1. **Traefik v3** instalado via Helm com suporte a CRDs (`IngressRoute`, `Middleware`):
   ```bash
   helm repo add traefik https://traefik.github.io/charts
   helm upgrade --install traefik traefik/traefik \
     -n traefik --create-namespace \
     --set providers.kubernetesCRD.enabled=true \
     --set providers.kubernetesCRD.allowCrossNamespace=true
   ```

2. **CloudNativePG operator** instalado:
   ```bash
   kubectl apply --server-side \
     -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.24/releases/cnpg-1.24.0.yaml
   ```

### 1. Criar os Secrets

Os secrets nunca devem ser versionados com valores reais.

**Secret da aplicação:**
```bash
kubectl create secret generic app-secret \
  -n querido-diario \
  --from-literal=QD_BACKEND_SECRET_KEY='...' \
  --from-literal=QD_BACKEND_DB_URL='postgres://user:pass@postgres/backend' \
  --from-literal=QD_DATA_DB_USER='...' \
  --from-literal=QD_DATA_DB_PASSWORD='...' \
  --from-literal=QD_BACKEND_DB_USER='...' \
  --from-literal=QD_BACKEND_DB_PASSWORD='...' \
  --from-literal=POSTGRES_COMPANIES_USER='...' \
  --from-literal=POSTGRES_COMPANIES_PASSWORD='...' \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_HOST='https://...' \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_USER='...' \
  --from-literal=QUERIDO_DIARIO_OPENSEARCH_PASSWORD='...' \
  --from-literal=STORAGE_ACCESS_KEY='...' \
  --from-literal=STORAGE_ACCESS_SECRET='...' \
  --from-literal=STORAGE_BUCKET='...' \
  --from-literal=MAILJET_API_KEY='...' \
  --from-literal=MAILJET_SECRET_KEY='...' \
  --from-literal=QUERIDO_DIARIO_SUGGESTION_RECIPIENT_EMAIL='...'
```

**Secret de credenciais do PostgreSQL (usado pelo CloudNativePG no initdb):**
```bash
kubectl create secret generic postgres-credentials \
  -n querido-diario \
  --from-literal=username='...' \
  --from-literal=password='...'
```

Alternativas mais seguras: [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) ou [External Secrets Operator](https://external-secrets.io/).

### 2. Ajustar configurações

Edite `k8s/base/configmap-app.yaml` com os valores do ambiente de produção (domínio, URLs, etc.).

Edite `k8s/overlays/production/kustomization.yaml` para fixar as tags de imagem:
```yaml
images:
  - name: ghcr.io/okfn-brasil/querido-diario-api
    newTag: "v1.2.3"   # substitua pelo release desejado
```

### 3. Ver diff antes de aplicar

```bash
make k8s-diff-prod
```

### 4. Aplicar

```bash
make k8s-apply-prod
```

---

## Referência rápida

```bash
# Gerar YAML sem aplicar (dry-run)
make k8s-build-dev
make k8s-build-prod

# Ver diff entre cluster e manifests
make k8s-diff-dev
make k8s-diff-prod

# Aplicar
make k8s-apply-dev
make k8s-apply-prod
```

## data-processing (CronJob)

Roda automaticamente a cada hora (`0 * * * *`). Em dev o CronJob está suspenso.

Para executar manualmente:
```bash
make k8s-local-data-processing   # dev (kind)

# ou em qualquer cluster:
kubectl create job --from=cronjob/data-processing data-processing-manual-$(date +%s) \
  -n querido-diario
kubectl logs -n querido-diario -l job-name=data-processing-manual -f
```

## Notas

**static files (backend):** O PVC `static-files` usa `ReadWriteOnce` (1 réplica). Para escalar o backend, migre para `ReadWriteMany` (NFS/EFS) ou sirva os estáticos via S3/CDN.

**PostgreSQL:** Gerenciado pelo [CloudNativePG](https://cloudnative-pg.io/). Em prod roda com 3 instâncias (primary + 2 replicas). Os bancos `queridodiario`, `backend` e `companies` são criados automaticamente no primeiro boot via `postInitSQL`.

**OpenSearch:** Em produção roda como `StatefulSet` single-node dentro do cluster k8s, em `k8s/overlays/production/opensearch/` (ver ADR-008). Em dev, o overlay inclui OpenSearch como `Deployment` local (plugin de segurança desabilitado).

**Storage:** Em produção é um serviço externo (AWS S3, não provisionado neste repositório). Em dev, o overlay inclui Garage (S3-compatível) como `Deployment` local.
