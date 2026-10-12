# Restaurar um backup do Securo

Os backups são criptografados com [age](https://github.com/FiloSottile/age). O servidor guarda só a chave **pública**;
para restaurar é preciso a chave **privada** (`age-key.txt`), que deve estar guardada **fora** do servidor (gerenciador de senhas).
Sem ela os backups **não podem ser abertos**.

Nomes dos arquivos: `securo-db-<data>.dump.age`, `securo-attachments-<data>.tar.gz.age` e `securo-<data>.sha256`.
Onde estão: na pasta definida por `BACKUP_DIR` (padrão `~/securo-backup-files`) e, se configurado, no seu bucket R2, em `securo-backup-AAAA-MM-DD/`, na raiz do bucket (um backup por dia; backups anteriores à v0.16.3-selfhost.3 ficam soltos em `securo/`).

> Convenções: rode os comandos a partir da raiz do repositório. Troque `<data>` pelo carimbo do backup
> (ex.: `20260101-031500`). Os comandos assumem o projeto Compose `securo-prod` e o arquivo de ambiente
> `deploy/public/.env`, ambos embutidos no atalho `./deploy/public/securo-compose` (veja o README).

## 1. Verificar a integridade
```bash
cd <pasta-dos-backups> && shasum -a 256 -c securo-<data>.sha256
```

## 2. Testar a restauração sem tocar na produção (faça de tempos em tempos)
```bash
age -d -i ~/.config/securo-backup/age-key.txt -o /tmp/restore.dump securo-db-<data>.dump.age
docker run -d --name securo-restore-test -e POSTGRES_PASSWORD=teste -e POSTGRES_DB=securo docker.io/pgvector/pgvector:pg16
docker exec securo-restore-test psql -U postgres securo -c "create extension if not exists vector;"
docker cp /tmp/restore.dump securo-restore-test:/tmp/restore.dump
docker exec securo-restore-test pg_restore -U postgres -d securo --no-owner /tmp/restore.dump
docker exec securo-restore-test psql -U postgres securo -c "select count(*) from users;"
docker rm -f securo-restore-test && rm /tmp/restore.dump
```
O dump em claro contém dados financeiros: apague `/tmp/restore.dump` ao terminar. Compare o resultado
(número de tabelas, usuários, versão da migration) com a produção para confirmar que o backup é utilizável.

## 3. Restaurar na produção (DESTRUTIVO: substitui o banco atual)
Pare o backend e os workers para não gravarem durante a restauração, e faça um backup novo antes.
```bash
C="./deploy/public/securo-compose"
./deploy/public/backup/backup.sh                   # backup de segurança do estado atual
$C stop backend celery-worker celery-beat frontend
age -d -i ~/.config/securo-backup/age-key.txt -o /tmp/restore.dump securo-db-<data>.dump.age
docker cp /tmp/restore.dump securo-prod-db-1:/tmp/restore.dump
docker exec securo-prod-db-1 psql -U postgres -c "drop database securo;" -c "create database securo;"
docker exec securo-prod-db-1 psql -U postgres securo -c "create extension if not exists vector;"
docker exec securo-prod-db-1 pg_restore -U postgres -d securo --no-owner /tmp/restore.dump
$C up -d
rm /tmp/restore.dump
```

## 4. Restaurar os anexos
```bash
age -d -i ~/.config/securo-backup/age-key.txt securo-attachments-<data>.tar.gz.age \
  | docker run --rm -i --entrypoint tar -v securo-prod_attachments:/data docker.io/library/redis:8-alpine xzf - -C /data
```

## 5. Restaurar em outra máquina
O banco guarda, **criptografadas com uma chave derivada do `SECRET_KEY`**, as sessões de conexão bancária e as chaves de API dos
agents. Restaure usando o **mesmo `SECRET_KEY`** do servidor original; com outro valor o banco volta íntegro, mas essas
credenciais ficam ilegíveis e as conexões precisam ser refeitas. O backup **não inclui** o arquivo `.env`: guarde `SECRET_KEY`
e a chave privada age no gerenciador de senhas.

## 6. Restaurar o backup de produção no ambiente de DEV (para testar mudanças)
O script `deploy/public/backup/restore-to-dev.sh` restaura o dump no banco do projeto de dev (`securo`), sem tocar na produção
(`securo-prod`). Ele descriptografa direto para o `pg_restore` (nada em claro em disco), confere o `.sha256` quando está ao lado
do arquivo, recria o banco de dev, deixa o backend aplicar as migrations novas da branch e mantém os workers do Celery parados,
para o dev não sincronizar contas bancárias reais.
```bash
./deploy/public/backup/restore-to-dev.sh ~/securo-backup-files/securo-db-<data>.dump.age --dry-run   # só valida
./deploy/public/backup/restore-to-dev.sh ~/securo-backup-files/securo-db-<data>.dump.age             # restaura (pede confirmação)
# opcionais: --attachments <securo-attachments-<data>.tar.gz.age>  --with-workers  --yes
```
Use o mesmo `SECRET_KEY` da produção para que conexões bancárias e chaves de agents continuem legíveis. O banco de dev passa a ter
dados financeiros reais: não o exporte nem o compartilhe.
