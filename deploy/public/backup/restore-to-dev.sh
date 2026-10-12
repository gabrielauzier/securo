#!/bin/bash
# Restaura um backup do banco de PRODUÇÃO no banco de DESENVOLVIMENTO (projeto Compose "securo"),
# para testar mudanças contra dados reais antes de subir uma versão.
#
# Uso:
#   ./deploy/public/backup/restore-to-dev.sh <securo-db-AAAAMMDD-HHMMSS.dump.age | arquivo.dump> [opções]
#
# Opções:
#   --attachments <arquivo.tar.gz.age|.tar.gz>  restaura também os anexos no volume de dev
#   --with-workers   sobe celery-worker e celery-beat no fim (padrão: ficam parados; veja abaixo)
#   --dry-run        só valida arquivo, chave e containers; não altera nada
#   -y, --yes        não pede confirmação
#   -h, --help
#
# Variáveis opcionais:
#   AGE_KEY_FILE    chave PRIVADA age (padrão: ~/.config/securo-backup/age-key.txt)
#   DEV_PROJECT     projeto Compose de dev (padrão: securo)
#   DEV_DB_CONTAINER container do banco de dev (padrão: ${DEV_PROJECT}-db-1)
#   DEV_ATT_VOLUME  volume de anexos de dev (padrão: ${DEV_PROJECT}_attachments)
#   SECRET_KEY      use o MESMO SECRET_KEY da produção para que as credenciais criptografadas
#                   no banco (conexões bancárias, chaves de API dos agents) continuem legíveis.
#
# Segurança:
#   * Só atua no projeto de dev. Recusa qualquer container/volume do projeto "securo-prod".
#   * O dump nunca é gravado em claro: a descriptografia é enviada direto ao pg_restore.
#   * Substitui TODO o banco "securo" de dev (drop + create). É destrutivo para o dev atual.
#   * Celery worker/beat ficam parados por padrão: com dados reais de produção eles poderiam
#     sincronizar contas bancárias de verdade (Pluggy, Enable Banking, SimpleFIN) a partir do dev.
#   * Depois da restauração o banco de dev contém dados financeiros reais. Trate-o como produção.
#
# Ao subir, o backend de dev roda `alembic upgrade head`: se a branch tiver migrations mais novas
# que o backup (ex.: 097), elas são aplicadas, que é justamente o teste de upgrade.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEV_PROJECT="${DEV_PROJECT:-securo}"
DEV_DB_CONTAINER="${DEV_DB_CONTAINER:-${DEV_PROJECT}-db-1}"
DEV_ATT_VOLUME="${DEV_ATT_VOLUME:-${DEV_PROJECT}_attachments}"
AGE_KEY_FILE="${AGE_KEY_FILE:-$HOME/.config/securo-backup/age-key.txt}"
TAR_IMAGE="${TAR_IMAGE:-docker.io/library/redis:8-alpine}"
DEV_COMPOSE=(docker compose -p "$DEV_PROJECT" -f "$ROOT/docker-compose.yml")

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"

log() { echo "$(date '+%H:%M:%S') $*"; }
die() { echo "ERRO: $*" >&2; exit 1; }
usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }

DB_FILE=""; ATT_FILE=""; WITH_WORKERS=0; DRY_RUN=0; ASSUME_YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --attachments) [ $# -ge 2 ] || die "--attachments exige um arquivo"; ATT_FILE="$2"; shift 2 ;;
    --with-workers) WITH_WORKERS=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) die "opção desconhecida: $1 (use --help)" ;;
    *) [ -z "$DB_FILE" ] || die "informe apenas um arquivo de banco"; DB_FILE="$1"; shift ;;
  esac
done
[ -n "$DB_FILE" ] || { usage; exit 1; }

# --- Proteções contra tocar na produção --------------------------------------
case "$DEV_PROJECT" in securo-prod*|*-prod) die "DEV_PROJECT='$DEV_PROJECT' parece ser a produção. Abortado." ;; esac
case "$DEV_DB_CONTAINER" in securo-prod*) die "DEV_DB_CONTAINER='$DEV_DB_CONTAINER' é da produção. Abortado." ;; esac
case "$DEV_ATT_VOLUME" in securo-prod*) die "DEV_ATT_VOLUME='$DEV_ATT_VOLUME' é da produção. Abortado." ;; esac

# --- Pré-requisitos -----------------------------------------------------------
command -v docker >/dev/null || die "docker não encontrado"
[ -f "$DB_FILE" ] || die "arquivo não encontrado: $DB_FILE"
if [ -n "$ATT_FILE" ]; then [ -f "$ATT_FILE" ] || die "arquivo de anexos não encontrado: $ATT_FILE"; fi

needs_age() { case "$1" in *.age) return 0 ;; *) return 1 ;; esac; }
if needs_age "$DB_FILE" || { [ -n "$ATT_FILE" ] && needs_age "$ATT_FILE"; }; then
  command -v age >/dev/null || die "age não encontrado (brew install age)"
  [ -r "$AGE_KEY_FILE" ] || die "chave privada não encontrada em $AGE_KEY_FILE (defina AGE_KEY_FILE)"
fi

# Descriptografa (ou apenas lê) para stdout, sem gravar texto em claro em disco.
emit() { if needs_age "$1"; then age -d -i "$AGE_KEY_FILE" "$1"; else cat "$1"; fi; }

# Integridade, quando o .sha256 do backup está ao lado do arquivo.
verify_sum() {
  local f="$1" dir base sum
  dir="$(cd "$(dirname "$f")" && pwd)"; base="$(basename "$f")"
  sum="$(ls "$dir"/securo-*.sha256 2>/dev/null | while read -r s; do grep -l " $base\$" "$s" 2>/dev/null; done | head -1 || true)"
  if [ -n "$sum" ]; then
    (cd "$dir" && grep " $base\$" "$sum" | shasum -a 256 -c -) >/dev/null 2>&1 \
      && log "integridade OK ($base)" || die "checksum de $base não confere com $(basename "$sum")"
  else
    log "aviso: .sha256 de $base não encontrado ao lado do arquivo; integridade não verificada"
  fi
}
verify_sum "$DB_FILE"
if [ -n "$ATT_FILE" ]; then verify_sum "$ATT_FILE"; fi

# O arquivo deve ser um pg_dump -Fc (começa com "PGDMP").
magic="$(emit "$DB_FILE" 2>/dev/null | head -c 5 || true)"
[ "$magic" = "PGDMP" ] || die "o conteúdo de $DB_FILE não é um dump do PostgreSQL (formato custom). Chave errada ou arquivo errado?"

# O container precisa ser mesmo do projeto de dev.
docker inspect "$DEV_DB_CONTAINER" >/dev/null 2>&1 || die "container $DEV_DB_CONTAINER não existe. Suba o dev: docker compose up -d db"
label="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' "$DEV_DB_CONTAINER")"
[ "$label" = "$DEV_PROJECT" ] || die "$DEV_DB_CONTAINER pertence ao projeto '$label', não a '$DEV_PROJECT'. Abortado."
[ "$(docker inspect -f '{{.State.Running}}' "$DEV_DB_CONTAINER")" = "true" ] || die "container $DEV_DB_CONTAINER não está rodando. Suba: docker compose up -d db"
if [ -n "$ATT_FILE" ]; then
  docker volume inspect "$DEV_ATT_VOLUME" >/dev/null 2>&1 || die "volume $DEV_ATT_VOLUME não existe (suba o dev uma vez para criá-lo)"
  vlabel="$(docker volume inspect -f '{{ index .Labels "com.docker.compose.project" }}' "$DEV_ATT_VOLUME")"
  [ "$vlabel" = "$DEV_PROJECT" ] || die "volume $DEV_ATT_VOLUME pertence ao projeto '$vlabel', não a '$DEV_PROJECT'. Abortado."
fi

log "backup:  $DB_FILE"
[ -z "$ATT_FILE" ] || log "anexos:  $ATT_FILE"
log "destino: container $DEV_DB_CONTAINER (projeto $DEV_PROJECT), banco 'securo' será SUBSTITUÍDO"

if [ "$DRY_RUN" = 1 ]; then log "dry-run: tudo validado, nada foi alterado."; exit 0; fi

if [ "$ASSUME_YES" != 1 ]; then
  printf 'Isto apaga o banco de DEV atual. Digite RESTAURAR para continuar: '
  read -r answer; [ "$answer" = "RESTAURAR" ] || { echo "cancelado." >&2; exit 1; }
fi

PSQL=(docker exec -i "$DEV_DB_CONTAINER" psql -U postgres -v ON_ERROR_STOP=1)

# --- 1. Parar a aplicação de dev ---------------------------------------------
log "parando backend, workers e frontend de dev..."
"${DEV_COMPOSE[@]}" stop backend celery-worker celery-beat frontend mcp-server >/dev/null 2>&1 || true

# --- 2. Recriar o banco -------------------------------------------------------
log "recriando o banco 'securo'..."
"${PSQL[@]}" -d postgres -c "drop database if exists securo with (force)" -c "create database securo" >/dev/null
"${PSQL[@]}" -d securo -c "create extension if not exists vector" >/dev/null

# --- 3. Restaurar (stream: sem arquivo em claro) ------------------------------
log "restaurando o dump..."
set +e
emit "$DB_FILE" | docker exec -i "$DEV_DB_CONTAINER" pg_restore -U postgres -d securo --no-owner --no-privileges
rc=("${PIPESTATUS[@]}")
set -e
[ "${rc[0]}" -eq 0 ] || die "falha ao ler/descriptografar o backup (código ${rc[0]})"
if [ "${rc[1]}" -ne 0 ]; then
  log "aviso: pg_restore terminou com código ${rc[1]} (avisos/erros não fatais, comuns com extensões). Confira os dados abaixo."
fi

users="$("${PSQL[@]}" -d securo -tA -c "select count(*) from users" 2>/dev/null || echo "?")"
rev="$("${PSQL[@]}" -d securo -tA -c "select version_num from alembic_version" 2>/dev/null || echo "?")"
log "banco restaurado: $users usuário(s), migration do backup = $rev"

# --- 4. Anexos (opcional) -----------------------------------------------------
if [ -n "$ATT_FILE" ]; then
  log "restaurando anexos em $DEV_ATT_VOLUME (conteúdo atual do volume de dev é apagado)..."
  emit "$ATT_FILE" | docker run --rm -i --entrypoint sh -v "$DEV_ATT_VOLUME":/data "$TAR_IMAGE" \
    -c 'find /data -mindepth 1 -delete && tar xzf - -C /data'
fi

# --- 5. Subir de novo ---------------------------------------------------------
log "subindo o dev (o backend aplica 'alembic upgrade head' ao iniciar)..."
"${DEV_COMPOSE[@]}" up -d db redis backend frontend >/dev/null
if [ "$WITH_WORKERS" = 1 ]; then
  "${DEV_COMPOSE[@]}" up -d celery-worker celery-beat >/dev/null
  log "AVISO: workers ligados com dados reais: syncs bancários de verdade podem rodar a partir do dev."
else
  log "celery-worker e celery-beat ficaram parados (use --with-workers para ligá-los)."
fi

cat <<EOF

Pronto. Próximos passos:
  * Acompanhe as migrations:  docker compose -p $DEV_PROJECT logs -f backend
  * Entre com um usuário de produção em http://localhost:\${FRONTEND_PORT:-3000}
  * Se conexões bancárias ou chaves de agents aparecerem ilegíveis, o SECRET_KEY de dev difere do de
    produção: exporte o mesmo SECRET_KEY e rode de novo (o backup não inclui o .env).
  * O banco de dev agora tem dados financeiros reais; não o exporte nem o compartilhe.
EOF
