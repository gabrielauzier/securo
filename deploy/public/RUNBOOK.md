# Guia de operação: Securo em produção

Como verificar, parar e retomar o serviço, e o que fazer depois de reiniciar o Mac.
Visão geral e decisões: [README.md](README.md). Backup e restauração: [backup/restore.md](backup/restore.md).
Os comandos de parar e retomar abaixo foram validados num ciclo real (túnel e aplicação), com os dados preservados.

```
Internet → Cloudflare → túnel (cloudflared, LaunchAgent) → 127.0.0.1:3100 → containers "securo-prod"
```

| Peça | O que é | Como é gerenciada |
|---|---|---|
| Aplicação | 6 containers do projeto Compose **`securo-prod`** (frontend, backend, celery-worker, celery-beat, redis, db) | `docker compose -p securo-prod ...` |
| Exposição | Túnel Cloudflare `securo` (4 conexões com a Cloudflare) | LaunchAgent `com.cloudflare.cloudflared` |
| Backup | Job diário 03:15, envia ao R2 | LaunchAgent `com.securo.backup` |

> ## ⚠️ Leia antes de mexer
> - **Sempre use `-p securo-prod` e `--env-file deploy/public/.env`.** Se o ambiente de **desenvolvimento** rodar na mesma máquina, ele usa o projeto `securo` (containers `securo-*-1`, portas 3000/8000), e os dois arquivos compose declaram `name: securo`. Rodar o compose de produção sem `-p securo-prod` **substitui os containers de dev e reaproveita o banco de dev**.
> - **Nunca use `down -v`, `docker volume rm` nem `docker system prune --volumes`** em produção: apagam o banco e os anexos (`securo-prod_pgdata`, `securo-prod_attachments`). O `down` sem `-v` remove só os containers (os dados ficam), mas prefira `stop`.
> - Faça um **backup antes** de qualquer operação arriscada: `./deploy/public/backup/backup.sh`.

## 0. Atalho (opcional)
Para não repetir as flags, no `~/.zshrc`:
```bash
securo-prod() { (cd /caminho/para/o/repositorio/securo && docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml "$@"); }
```
Depois: `securo-prod ps`, `securo-prod stop`, `securo-prod logs -f backend`. Abaixo uso os comandos completos.

Todos os comandos assumem que você está na raiz do repositório:
```bash
cd /caminho/para/o/repositorio/securo
```

## 1. Ver o estado
```bash
docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml ps
```
```bash
curl -s http://127.0.0.1:3100/api/health        # local: deve responder {"status":"healthy"}
```
```bash
curl -s https://securo.example.com/api/health   # público, pela Cloudflare
```
```bash
launchctl list | grep -E "cloudflared|securo"   # PID na 1ª coluna = rodando; 2ª coluna = último código de saída (0 = ok)
```

## 2. Parar e retomar

### 2.1 Tirar do ar sem parar a aplicação (emergência, ou "desligar o acesso de fora")
Só derruba o túnel. A aplicação continua rodando e acessível em `http://127.0.0.1:3100`; os jobs do Celery continuam.
```bash
launchctl bootout gui/$(id -u)/com.cloudflare.cloudflared
```
Resultado público: **HTTP 530** (Cloudflare sem túnel ativo).

**Retomar:**
```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
```
Em ~10 segundos o `/api/health` público volta a responder 200.

### 2.2 Parar a aplicação (manutenção; preserva todos os dados)
```bash
docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml stop
```
Para os 6 containers sem removê-los; **volumes e dados ficam intactos**. Se o túnel estiver ativo, o público passa a responder **HTTP 502** (túnel sem origem). Para uma manutenção limpa, derrube antes o túnel (2.1) e o público verá 530 em vez de 502.

**Retomar:**
```bash
docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml start
```
O banco e o Redis ficam saudáveis em ~10 s; em seguida sobem backend, workers e frontend. Se os containers tiverem sido removidos (por exemplo, após um `down`), use `up -d` no lugar de `start`.

### 2.3 Parada completa e retomada, na ordem certa
```bash
# parar
launchctl bootout gui/$(id -u)/com.cloudflare.cloudflared
docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml stop
```
```bash
# retomar
docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml start
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.cloudflare.cloudflared.plist
```
Confira com a seção 1. `stop` e `start` não removem containers nem volumes, então os dados ficam intactos.

### 2.4 Reiniciar só um serviço (ex.: depois de mudar o `.env`)
```bash
docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml up -d backend celery-worker celery-beat
```
Mudanças no `deploy/public/.env` só valem depois de recriar os containers afetados (`up -d`); `restart` não relê o `.env`.

### 2.5 Pausar o backup noturno
```bash
launchctl bootout gui/$(id -u)/com.securo.backup
```
Retomar:
```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.securo.backup.plist
```
Se a aplicação estiver **parada** às 03:15, o backup falha (o script exige o banco saudável), o que aparece em `~/Library/Logs/securo-backup.log`. Faça um backup manual antes de parar por muito tempo.

## 3. Depois de reiniciar o Mac ou de uma queda de energia
Com `autorestart` ligado o Mac religa sozinho. **Se o FileVault estiver ativo** (o login automático não funciona com ele), o Mac para na tela de senha e nada sobe até alguém digitar a senha.
1. **Digite a senha de login** na tela de boot (presencial; não há como fazer remotamente).
2. O **túnel** (LaunchAgent) sobe com a sessão. O **Docker Desktop só sobe sozinho se "Start Docker Desktop when you sign in" estiver ligado** (Settings → General). Se não estiver, abra o Docker Desktop manualmente.
3. Os containers têm `restart: unless-stopped` e voltam quando o Docker inicia. Se algum não voltar:
   ```bash
   docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml up -d
   ```
4. Confirme com a seção 1. Enquanto isso não for feito, o público responde 530 ou 502.

Atualizações do macOS que reiniciam o Mac derrubam o serviço até o desbloqueio. Se você desligou a instalação automática (passo opcional do `hardening/harden-mac.sh`), instale manualmente numa janela de manutenção: faça backup, atualize, digite a senha no reinício e confira a seção 1.

## 4. Atualizar a versão do Securo
```bash
./deploy/public/backup/backup.sh                       # 1. backup (grava em BACKUP_DIR e envia ao R2, se configurado)
```
```bash
docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml pull
docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml up -d
```
As migrations rodam sozinhas no start do backend (`alembic upgrade head`). Veja as notas da versão antes. Para voltar atrás é preciso restaurar o backup (ver [backup/restore.md](backup/restore.md)), porque as migrations não são revertidas automaticamente.

## 5. Logs e diagnóstico
```bash
docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml logs --tail 100 backend
```
```bash
docker compose -p securo-prod --env-file deploy/public/.env -f docker-compose.prod.yml logs -f      # todos, ao vivo
```
```bash
tail -n 30 ~/Library/Logs/com.cloudflare.cloudflared.err.log    # túnel
```
```bash
tail -n 30 ~/Library/Logs/securo-backup.log                     # backup
```

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Público **530** | Túnel parado ou sem conexão | `launchctl list | grep cloudflared` (sem PID = parado): seção 2.1 (retomar) e log do túnel |
| Público **502** | Túnel ok, aplicação parada ou reiniciando | Seção 2.2 (retomar); `ps` e logs do backend |
| Público **404** com a página de outra plataforma (ex.: "deployment not found") | DNS antigo em cache no seu resolver, ainda apontando para o servidor anterior do domínio | Aguardar (até 24–48 h após trocar nameservers) ou usar DNS `1.1.1.1`; ver "Armadilhas" no README |
| **403** em `/api/auth/register` | Cadastro de novos usuários desativado (intencional) | Reabrir: ver "Cadastro de novos usuários" no README |
| Login bloqueado por excesso de tentativas | Rate limit (5 por minuto por IP) | Aguardar 1 minuto |
| Backup noturno com erro | App parada, credenciais do R2 ou volume cheio | Log do backup; `deploy/public/backup/setup-r2.sh` |
| Containers não sobem após reinício | Docker Desktop não iniciou | Seção 3 |

## 6. Arquivos importantes (nada disso vai para o git)
| Caminho | Conteúdo |
|---|---|
| `deploy/public/.env` | Segredos da aplicação (`SECRET_KEY` etc.) |
| `~/.cloudflared/` | `cert.pem`, credenciais do túnel (`<id>.json`) e `config.yml` |
| `~/.config/securo-backup/` | `age-key.txt` (**chave privada dos backups**), `age-recipient.txt`, `r2.env`, cópias dos scripts, backups diários |
| `~/Library/LaunchAgents/` | `com.cloudflare.cloudflared.plist`, `com.securo.backup.plist` |
| `~/Library/Logs/` | Logs do túnel e do backup |

### Segredos que NÃO estão no backup (guarde uma cópia fora do Mac)
O backup cobre só o banco e os anexos. **Não inclui `deploy/public/.env` nem a chave `age-key.txt`.**
- **`SECRET_KEY` (em `deploy/public/.env`):** além de assinar logins, ela deriva a chave que **criptografa dentro do banco** as sessões de conexão bancária (Enable Banking, SimpleFIN) e as chaves de API dos agents (`backend/app/agents/services/crypto.py`). Se for perdida, o banco restaurado continua íntegro, mas essas credenciais ficam **ilegíveis** e as conexões bancárias precisam ser refeitas; todos os logins ativos também caem. Restaurar o banco num ambiente novo **com o mesmo `SECRET_KEY`** evita isso.
- **`age-key.txt`:** sem ela, nenhum backup (local ou no R2) abre.
- **`~/.cloudflared/*.json`:** credenciais do túnel; se forem perdidas, crie um novo túnel (`cloudflared tunnel create`) e rode `cloudflared tunnel route dns` de novo.

Guarde `SECRET_KEY`, `AGENTS_MCP_JWT_SECRET` e a chave privada age no gerenciador de senhas.
