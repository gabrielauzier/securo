# Publicar as suas próprias releases (imagens do fork)

Como construir e publicar, a partir do **seu fork**, as imagens Docker do Securo que o seu servidor vai rodar, com uma versão
fixa que você controla. Faz sentido se você mantém mudanças suas por cima do projeto original, ou simplesmente quer decidir
quando e o quê atualizar. Se você só roda as releases oficiais, não precisa disto: fixe `SECURO_IMAGE_TAG` numa versão oficial.

## Como funciona
- O workflow `.github/workflows/release.yml` roda quando uma **release é publicada** (`release: published`), constrói
  `securo-backend` e `securo-frontend` (`linux/amd64` e `linux/arm64`) **a partir do commit da release** e publica no GHCR em
  `ghcr.io/<dono-do-repositório>/securo-*`, com a tag da versão e com `latest`. Como o prefixo usa o dono do repositório, **o
  seu fork publica nas suas imagens sem nenhuma alteração no workflow**.
- Ele também empacota um chart Helm em `ghcr.io/<dono>/charts`. Se você não usa Kubernetes, ignore (o job é independente das imagens).
- O workflow `prepare-release.yml` do projeto abre um PR de bump de versão **contra `main`**. **Não o use** num fork que mantém
  `main` como espelho do original: ele faria `main` divergir.

## Organização de branches
| Branch | Papel |
|---|---|
| `main` | Espelho exato do projeto original. Só fast-forward; nunca commite nela. |
| `prod` | O que roda no seu servidor: o espelho (ou uma tag do original) mais as suas mudanças. **Daqui saem as releases.** |
| `fix/…`, `feat/…`, `docs/…` | Trabalho para o projeto original: nascem de `main`, nunca de `prod`. |

Sincronizar o espelho (ou use o botão "Sync fork" do GitHub):
```bash
git fetch upstream && git switch main && git merge --ff-only upstream/main && git push origin main
```
Levar uma versão nova do original para a produção:
```bash
git switch prod && git merge v0.17.0        # ou: git rebase v0.17.0 (histórico linear; exige push com --force-with-lease)
```

## Esquema de versões
Use **a versão do projeto original + um sufixo seu e um contador**: `0.16.3-selfhost.1`, `0.16.3-selfhost.2`, depois `0.17.0-selfhost.1`.
Isso mostra de qual versão do original o build parte e nunca colide com as tags dele. É um pré-release em termos de semver (ele
ordena **antes** de `0.16.3`), o que não importa aqui, porque você sempre fixa a tag exata. O backend continua reportando a versão do
`pyproject.toml` (a do original); o frontend mostra a tag da release (`VITE_APP_VERSION`).

## Preparação única (no GitHub)
1. **Habilite o Actions no fork.** Forks vêm com os workflows desabilitados: abra a aba *Actions* do fork e confirme. (Sem isso o
   workflow nem aparece; `gh api repos/<dono>/securo/actions/workflows` retorna lista vazia.)
2. **Desative o workflow "Downloads Badge"** (`gh workflow disable "Downloads Badge" -R <dono>/securo`). Ele roda todo dia e falha
   no fork (precisa de um segredo `GIST_TOKEN` que só o projeto original tem), gerando e-mails de falha. Desativar não altera arquivos.
3. **Opcional:** deixe o CI como está (`ci.yml` roda em PRs e pushes para `main`; não roda para `prod`, então teste localmente antes de uma release).
4. Não é preciso criar segredos: o workflow usa o `GITHUB_TOKEN` com permissão de escrita de pacotes.

## Publicar uma release
1. Deixe a `prod` pronta e **enviada ao GitHub** (a release constrói o que está no remoto).
2. Confira sem criar nada:
   ```bash
   ./deploy/public/release.sh 0.16.3-selfhost.1 --dry-run
   ```
   Ele valida: está na `prod`, árvore limpa, `prod` igual a `origin/prod`, o remoto é o seu fork (recusa o repositório original) e a tag está livre.
3. Publique (pede confirmação). Ele cria a release `v0.16.3-selfhost.1` apontando para o **SHA exato** da `prod`:
   ```bash
   ./deploy/public/release.sh 0.16.3-selfhost.1
   ```
4. Acompanhe o workflow "Build and Push Docker Images" (o build `arm64` sob emulação é o trecho lento):
   ```bash
   gh run watch --repo <dono>/securo
   ```
5. Confira as imagens e as arquiteturas:
   ```bash
   docker buildx imagetools inspect ghcr.io/<dono>/securo-backend:0.16.3-selfhost.1 | grep Platform
   docker buildx imagetools inspect ghcr.io/<dono>/securo-frontend:0.16.3-selfhost.1 | grep Platform
   ```

## Visibilidade dos pacotes (decida antes de puxar no servidor)
Pacotes criados pelo workflow podem nascer **privados**. Duas opções:
- **Tornar públicos** (recomendado: o código já é open source e as imagens não contêm segredos): no GitHub, *Packages* do seu usuário →
  cada pacote → *Package settings* → *Change visibility*. Até onde sei, isso é feito pela interface do GitHub, **uma vez por pacote**.
  Verifique de uma máquina sem login: `docker logout ghcr.io; docker pull ghcr.io/<dono>/securo-backend:<versão>`.
- **Mantê-los privados:** no servidor, `docker login ghcr.io -u <usuário>` com um token de acesso pessoal que tenha **apenas** `read:packages`.
  O token fica guardado em `~/.docker/config.json` do servidor.

## Colocar a versão no servidor
1. Backup (é obrigatório, as migrations não são revertidas):
   ```bash
   ./deploy/public/backup/backup.sh
   ```
2. No `.env` de produção, aponte para o seu fork e para a versão:
   ```env
   SECURO_IMAGE_OWNER=<seu-usuario-do-github>
   SECURO_IMAGE_TAG=0.16.3-selfhost.1
   ```
3. Confira o que será usado (nada é alterado) e aplique:
   ```bash
   ./deploy/public/securo-compose config | grep image:
   ./deploy/public/securo-compose pull
   ./deploy/public/securo-compose up -d
   curl -s https://securo.example.com/api/health
   ```
4. **Reverter:** recoloque a tag anterior e repita o `pull` e o `up -d`. Se a versão nova aplicou migrations (veja os logs do backend), restaure
   também o backup do passo 1 (ver [backup/restore.md](backup/restore.md)).

## Armadilhas
- **Release criada pela interface do GitHub:** funciona igual, mas selecione como alvo a branch `prod` (ou o commit), **nunca `main`**.
- **A imagem contém o código do commit da `prod`, e não necessariamente o de uma release oficial.** Se a `prod` parte de `main`, ela pode estar **à frente** da última release do projeto original (correções e recursos ainda não lançados). Antes de publicar, veja o que muda e, principalmente, se há **migrations novas**, porque elas são de mão única: `git log --oneline <última-tag-oficial>..prod` e `git diff <última-tag-oficial> prod -- backend/alembic/versions`. Sem migration nova, voltar atrás é só trocar a tag; com migration, é preciso restaurar o backup. Para rodar exatamente uma release oficial, parta da tag dela (`git switch -c prod v0.16.3`) ou use direto as imagens oficiais com `SECURO_IMAGE_TAG`.
- **Apagar uma release não apaga as imagens** publicadas; apague os pacotes/versões à mão se for preciso.
- **`latest` do seu fork** sempre aponta para a release mais recente do **fork**, que é diferente do `latest` do projeto original.
  Por isso a produção usa uma tag fixa, nunca `latest`.
- **Falha só no job do Helm** não invalida as imagens (elas são publicadas antes). Confira os pacotes antes de refazer a release.
- **Refazer um build:** não reaproveite a mesma tag; publique `…-selfhost.2` (tags de imagem mutáveis dificultam saber o que está rodando).
- **Build do frontend travado no `arm64`:** o `frontend/Dockerfile` do projeto original compila o frontend dentro do estágio de cada plataforma, e no runner `amd64` o `arm64` roda sob QEMU. O empacotador do Vite 8 (Rolldown, binário nativo com várias threads) pode **travar** nessa emulação, normalmente depois de `rendering chunks...` e sem nenhuma saída (o job fica horas rodando; o `amd64` e o backend não são afetados). A correção é uma linha, `FROM --platform=$BUILDPLATFORM node:22-slim AS build`, porque o resultado do build é HTML, JS e CSS iguais em qualquer arquitetura; isso aplica-se à `prod`. Se um build travar: `gh run cancel <id>` e publique de novo. Ao levar versões novas do projeto original para a `prod`, essa linha pode gerar conflito de merge: mantenha-a.
- **Diferença de arquitetura:** o build é multiarquitetura (`amd64` e `arm64`), então a imagem roda tanto em Apple Silicon quanto em servidores x86.
