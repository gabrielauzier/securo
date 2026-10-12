#!/bin/bash
# Envio externo dos backups do Securo para o Cloudflare R2 (API compatível com S3), via rclone.
# Chamado por backup.sh com BACKUP_DIR e BACKUP_TS definidos. Os arquivos já chegam criptografados (age).
#
# Credenciais: arquivo ~/.config/securo-backup/r2.env (modo 600), criado por você a partir de
# deploy/public/backup/r2.env.example. Nunca commitar.
#
# Cada backup vai para a sua própria pasta, direto na raiz do bucket:
#   securo-backup-AAAA-MM-DD/  com os 3 arquivos (banco, anexos e .sha256)
# Backups do mesmo dia (ex.: um manual antes de atualizar e o noturno) dividem a pasta do dia; os
# nomes dos arquivos levam a hora, então não se sobrescrevem.
#
# OFFSITE_TARGET (opcional) substitui a raiz de destino (o bucket) por qualquer caminho aceito pelo rclone,
# inclusive uma pasta local; serve para testar o fluxo sem credenciais.
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [offsite] $*"; }
die() { log "ERRO: $*"; exit 1; }

command -v rclone >/dev/null || die "rclone não encontrado (brew install rclone)"
: "${BACKUP_DIR:?BACKUP_DIR não definido}"
: "${BACKUP_TS:?BACKUP_TS não definido}"
[[ "$BACKUP_TS" =~ ^[0-9]{8}-[0-9]{6}$ ]] || die "BACKUP_TS inválido: '$BACKUP_TS' (esperado AAAAMMDD-HHMMSS)"

ENV_FILE="${R2_ENV_FILE:-$HOME/.config/securo-backup/r2.env}"
if [ -z "${OFFSITE_TARGET:-}" ]; then
  [ -r "$ENV_FILE" ] || die "credenciais não encontradas em $ENV_FILE (ver deploy/public/backup/r2.env.example)"
  perm="$(stat -f '%Lp' "$ENV_FILE")"
  [ "$perm" = "600" ] || die "permissão de $ENV_FILE é $perm; use chmod 600"
  set -a; . "$ENV_FILE"; set +a
  : "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID ausente em $ENV_FILE}"
  : "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID ausente em $ENV_FILE}"
  : "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY ausente em $ENV_FILE}"
  : "${R2_BUCKET:?R2_BUCKET ausente em $ENV_FILE}"
  # Remote "r2" definido só por variáveis de ambiente: nada de segredo em disco além do r2.env.
  export RCLONE_CONFIG_R2_TYPE=s3
  export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
  export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
  export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
  export RCLONE_CONFIG_R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
  export RCLONE_CONFIG_R2_ACL=private
  # Token restrito a um bucket não pode criar/checar o bucket: não tentar.
  export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
  # Raiz do bucket. R2_PREFIX, de versões anteriores, não é mais usado.
  OFFSITE_TARGET="r2:${R2_BUCKET}"
  REMOTE_IS_R2=1
fi
KEEP_REMOTE_DAYS="${KEEP_REMOTE_DAYS:-90}"
export RCLONE_CONFIG=/dev/null   # ignora qualquer rclone.conf; só vale o que está acima

DB="securo-db-${BACKUP_TS}.dump.age"
ATT="securo-attachments-${BACKUP_TS}.tar.gz.age"
SUM="securo-${BACKUP_TS}.sha256"
# Pasta do backup: securo-backup-AAAA-MM-DD (data tirada do carimbo do próprio backup).
FOLDER="securo-backup-${BACKUP_TS:0:4}-${BACKUP_TS:4:2}-${BACKUP_TS:6:2}"
DEST_DIR="${OFFSITE_TARGET%/}/${FOLDER}"
for f in "$DB" "$ATT" "$SUM"; do [ -s "$BACKUP_DIR/$f" ] || die "arquivo local ausente: $BACKUP_DIR/$f"; done

LIST="$(mktemp)"; trap 'rm -f "$LIST"' EXIT
printf '%s\n' "$DB" "$ATT" "$SUM" > "$LIST"

log "enviando 3 arquivos para $DEST_DIR ..."
rclone copy "$BACKUP_DIR" "$DEST_DIR" --files-from "$LIST" --retries 3 --low-level-retries 5 --quiet

log "verificando no destino ..."
rclone check "$BACKUP_DIR" "$DEST_DIR" --files-from "$LIST" --one-way --quiet \
  || die "verificação falhou: o destino não confere com o backup local"

# Retenção remota: só os nomes deste esquema (nada mais no bucket é tocado). O padrão sem barra casa em
# qualquer profundidade, então vale tanto para as pastas por backup quanto para os arquivos soltos de
# versões anteriores (que ficam em securo/).
log "retenção remota (${KEEP_REMOTE_DAYS} dias) ..."
rclone delete "$OFFSITE_TARGET" --min-age "${KEEP_REMOTE_DAYS}d" \
  --include 'securo-db-*.dump.age' --include 'securo-attachments-*.tar.gz.age' --include 'securo-*.sha256' \
  --quiet || log "aviso: retenção remota falhou (não é fatal)"
# Pastas de backup que ficaram vazias, só em destino local (teste). No R2 elas somem sozinhas, e
# `rmdirs` apagaria também pastas vazias que você criou à mão na raiz do bucket.
if [ "${REMOTE_IS_R2:-0}" != 1 ]; then
  rclone rmdirs "$OFFSITE_TARGET" --leave-root --quiet || true
fi

log "ok: backup $BACKUP_TS enviado e verificado em $FOLDER"
