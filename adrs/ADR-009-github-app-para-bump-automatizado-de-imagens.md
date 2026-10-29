# ADR-009: GitHub App da org para bump automatizado de imagens em produção

**Data:** 2026-10-29
**Status:** Proposto

## Contexto

Em produção, a versão de cada imagem é fixada em
`k8s/overlays/production/kustomization.yaml`, em `images[].newTag`. Um push na
`main` deste repositório dispara `.github/workflows/deploy.yml`, que aplica o
overlay no Revoada; o job `deploy` usa `environment: production`, que deve ter
*required reviewers* habilitado.

Hoje o bump dessas tags é manual: alguém abre um commit/PR aqui depois que a
imagem do serviço foi publicada no GHCR (ex.: `release: atualiza imagem da API
para v0.22.10 em produção`). Isso gera atraso entre o merge no repositório do
serviço e o que roda em produção, e depende de alguém lembrar de fazer o bump.

Os serviços já publicam imagens a cada push/release em seus próprios repositórios.
Falta o último passo: propor a mudança de tag aqui. Como o repositório é separado,
esse passo exige uma credencial que o `GITHUB_TOKEN` do workflow **não** oferece:
ele só tem acesso ao repositório onde o workflow roda.

Há ainda uma segunda limitação do `GITHUB_TOKEN`: PRs e pushes feitos com ele não
disparam outros workflows. Um PR de bump aberto assim não rodaria `checks.yml`
(validações do overlay), e o revisor aprovaria sem os checks.

## Decisão

1. **Criar um GitHub App na organização `okfn-brasil`** (ex.: `qd-deployment-bot`),
   usado exclusivamente para que os repositórios de serviço abram PRs de bump
   neste repositório.
2. **Estabelecer o seguinte fluxo como padrão para atualizações automatizadas de
   deployment**, nos repositórios em que fizer sentido (ver "Escopo"):

   ```
   merge/release no repo do serviço
     → build & push da imagem no GHCR (já existe)
     → job `bump-deployment` (needs: build, só em push na main/release)
         → gera token curto do App, escopado a querido-diario-deployment
         → altera apenas `images[].newTag` do serviço no overlay de produção
         → abre/atualiza PR no querido-diario-deployment
     → checks.yml roda no PR
     → revisor humano aprova e faz merge
     → deploy.yml (environment: production) aplica no cluster
   ```

3. **O merge do PR de bump continua humano.** Não há auto-merge: a aprovação do PR
   (e a dos *required reviewers* do environment `production`) é o portão de
   produção.

### Configuração do App

- **Permissões de repositório:** `Contents: write`, `Pull requests: write`,
  `Metadata: read`. Nada além disso — em particular, sem `Workflows`, `Secrets`
  ou `Administration`.
- **Instalação:** somente em `querido-diario-deployment`.
- **Credenciais:** `APP_ID` e a chave privada guardadas como secrets **da
  organização**, com visibilidade restrita aos repositórios de serviço
  participantes. Os workflows geram o token com
  [`actions/create-github-app-token`](https://github.com/actions/create-github-app-token)
  (fixado por SHA, como as demais actions), com `owner` e `repositories`
  apontando para este repositório, de modo que o token expire em ~1h e valha só
  aqui.
- **Branch por serviço**, p. ex. `bump/frontend-prod`, usando
  `peter-evans/create-pull-request`: um novo merge antes da aprovação atualiza o
  PR aberto em vez de criar outro.
- **Proteção de branch na `main` deste repositório:** exigir PR com ao menos uma
  aprovação e os checks de `checks.yml`; o App **não** entra na lista de bypass.

### Escopo (onde faz sentido)

| Repositório | Tag usada em produção | Participa do fluxo? |
|---|---|---|
| `querido-diario-frontend` | sha curto (publicado a cada push na `main`) | Sim — bump a cada merge na `main` |
| `querido-diario-api` | tag de versão `vX.Y.Z` | Sim — bump disparado pela publicação da release/tag |
| `querido-diario-backend` | hoje `latest` | Depois de passar a publicar e fixar tags imutáveis (pré-requisito) |
| `querido-diario-data-processing` (+ Tika) | hoje `latest` | Idem |
| `querido-diario` (raspadores) | não é imagem do cluster (Zyte, ADR-005) | Não |

Fixar tag imutável em produção já é a orientação do próprio overlay ("evite
`:latest`"); trazer backend e data-processing para o fluxo é consequência
natural de adotá-la, mas fica como trabalho posterior a esta decisão.

## Alternativas consideradas

| Alternativa | Descartada por |
|---|---|
| PAT de uma pessoa | Amarrado a um usuário (some se a pessoa sai da org), escopo largo (acesso a todos os repos dela), não expira sozinho e o PR fica atribuído a uma pessoa |
| PAT fine-grained de uma conta de bot | Resolve o escopo, mas consome uma conta/licença, expira em no máximo 1 ano e exige rotação manual em cada repositório |
| Deploy key SSH no repositório de deployment | Permite push, mas não abre PR; e uma chave por repositório de serviço dá mais superfície de segredo |
| `GITHUB_TOKEN` + `workflow_dispatch`/`repository_dispatch` no deployment | O dispatch entre repositórios também exige credencial própria — não elimina o problema |
| Renovate/Dependabot observando o GHCR | Ferramenta nova a manter, e com sha curto como tag não há ordenação semver para ela decidir qual é a imagem mais recente |
| Pull em vez de push (GitOps: Argo CD/Flux Image Automation) | Mudança arquitetural bem maior (novo controlador no cluster) que foge do escopo deste problema; pode ser reavaliada depois |
| Manter o bump manual | É o estado atual, com o atraso e o risco de esquecimento descritos acima |

## Consequências

- Passa a existir uma identidade de automação própria e auditável (os PRs e
  commits aparecem como o App, não como uma pessoa), com tokens de curta duração
  e sem rotação manual de credenciais.
- A chave privada do App é o segredo sensível: o escopo de instalação (só o
  deployment) e a ausência de bypass de proteção de branch limitam o dano de um
  vazamento a "abrir PRs", que ainda precisam de aprovação humana.
- `checks.yml` passa a rodar nos PRs de bump (diferente do que ocorreria com
  `GITHUB_TOKEN`).
- Cada repositório participante ganha um job `bump-deployment` e acesso aos
  secrets de org do App; é preciso manter esse acesso restrito à lista de
  repositórios participantes.
- O histórico de `main` deste repositório passa a ter mais commits de `release:`
  automatizados, em linha com o padrão já usado manualmente.
- Rollback continua sendo reverter o PR de bump (ou apontar a tag anterior).
- Mudar uma tag em `main` aqui dispara deploy; o volume de PRs aprovados vira,
  portanto, volume de deploys. Se ficar excessivo, dá para agrupar bumps ou
  restringir o frontend a releases em vez de todo merge.

## Próximos passos

1. Um administrador da org cria o App e os secrets de org (`APP_ID`,
   chave privada), restritos aos repositórios participantes.
2. Habilitar a proteção de branch descrita acima neste repositório.
3. Implementar o job `bump-deployment` em `querido-diario-frontend` (primeiro
   caso, ao lado de `docker.yml`) e validar o fluxo de ponta a ponta.
4. Replicar em `querido-diario-api`, usando a tag de release.
5. Avaliar backend e data-processing após fixarem tags imutáveis.
