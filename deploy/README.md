# CyberCraft production deployment

Target: a Linux VPS with **one** host Daphne backend, nginx TLS, PostgreSQL 16
and Redis 7 in Docker. The Website's `deploy/README.md` adds Node22 standalone.
Sample domains `api.cybercraft.uz` and `cybercraft.uz` require owned DNS records;
replace them before deployment. Archived Workspace is not a deployment source.

## Prerequisites and persistence

Use Ubuntu 22.04+ (or equivalent), Python 3.13 with venv support, Java 21, Docker
Compose, nginx/certbot, and a non-root `cybercraft` service user. Django6 needs
Python 3.12+. Keep backend at `/srv/cybercraft/backend` and website at
`/srv/cybercraft/website`. Protect the service environment files with mode 0600.

Daphne owns Minecraft child processes and stdin pipes, so use **one process**;
multiple workers cannot share that state. Restarting backend stops game servers:
schedule maintenance and save worlds before releases. Existing systemd shutdown
settings allow graceful stop, then kill remaining children after 90 seconds.

Preserve PostgreSQL/Redis named volumes and backend `media/`, `servers/`,
`config/yggdrasil_keys/`, `logs/` and backups across code releases. Set
`SERVERS_ROOT` to persistent host storage if releases replace the code directory.
Public media upload directories must be nginx-readable (production storage
creates them with 0755 and files with 0644). Keep the backend/media/static
parent directories traversable by nginx; preserve private permissions on
secrets, logs, worlds and signing keys. Never expose server archives/worlds
as nginx static directories. Never run
`docker compose down -v` on production storage.

## Configure and start infrastructure

```sh
# Create the service account and owned /srv/cybercraft directory first.
sudo -u cybercraft git clone https://github.com/CyberCraft-Team/CyberCraft-Backend.git /srv/cybercraft/backend
cd /srv/cybercraft/backend
sudo -u cybercraft python3.13 -m venv env
sudo -u cybercraft env/bin/python -m pip install -r requirements.txt
sudo -u cybercraft cp deploy/production.env.example .env
sudo chmod 600 .env
# Edit .env: use real domain names and newly generated, independent secrets.
```

Required: `PRODUCTION=1`, long random `SECRET_KEY`, `MOD_API_KEY`,
`ALLOWED_HOSTS`, `REDIS_URL`, and PostgreSQL configuration (`DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_HOST`, `DB_PORT`, or `DATABASE_URL`). The mod server's
`X-CyberCraft-Key` must match `MOD_API_KEY`; never include this server secret in
public client builds. Backend `BACKEND_URL` is the public origin **without**
`/api/v1`; Website `BACKEND_URL` includes that prefix. Configure SMTP before
public registration/reset; console email is only suitable for development.

```sh
docker compose --env-file .env -f deploy/docker-compose.yml config --quiet
docker compose --env-file .env -f deploy/docker-compose.yml up -d --wait
sudo -u cybercraft mkdir -p media logs servers
sudo -u cybercraft env PRODUCTION=1 env/bin/python manage.py check
sudo -u cybercraft env PRODUCTION=1 env/bin/python manage.py check --deploy --tag security --fail-level WARNING
sudo -u cybercraft env PRODUCTION=1 env/bin/python manage.py migrate --noinput
sudo -u cybercraft env PRODUCTION=1 env/bin/python manage.py collectstatic --noinput
sudo -u cybercraft env PRODUCTION=1 env/bin/python manage.py createsuperuser
```

The settings selector reads `PRODUCTION` from the process environment before
loading `.env`; keep the explicit `env PRODUCTION=1` on every management command.
Systemd supplies it itself. Compose ports bind only to loopback. Configuration applies to
both Compose and Django; passing `--env-file .env` is essential. `config --quiet`
validates without printing secret-containing expanded configuration.

## Backend service, nginx and HTTPS

```sh
sudo cp deploy/cybercraft-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cybercraft-web
sudo cp deploy/nginx.conf /etc/nginx/sites-available/cybercraft-api
# Edit server_name to the actual API domain.
sudo ln -s /etc/nginx/sites-available/cybercraft-api /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d api.cybercraft.uz
```

Production defaults to HTTPS (`USE_SSL=1`). Keep it enabled when exposing real
accounts. HTTP may redirect during initial certificate bootstrap; Certbot's
nginx challenge handler serves verification independently. `USE_SSL=0` is only
an explicit temporary bootstrap/local-test override; turn it on before use.
nginx supplies trusted `X-Forwarded-Proto`, serves `/media/` and `/static/`, and
proxies `/ws/` with upgrade headers. Do not expose Daphne directly publicly.

## Verify release

```sh
curl -fsS https://api.cybercraft.uz/api/v1/health/
sudo journalctl -u cybercraft-web -n 50
sudo -u cybercraft env PRODUCTION=1 env/bin/python manage.py shell -c 'from django.conf import settings as s; print(s.DEBUG, s.DATABASES["default"]["ENGINE"], s.CHANNEL_LAYERS["default"]["BACKEND"])'
```

Expect `False`, PostgreSQL and Redis-backed channels. Readiness returns 503 for
DB, Redis or media storage failures. Confirm Website HTTPS login, account/admin
permissions, live WebSocket console, uploaded skins/news, and actual Minecraft
login with the configured server key. Builds/checks alone do not certify these
external integrations. API docs may still emit existing schema warnings; strict
security checks are intentionally separate from schema quality checks.

## Backup, restore and updates

Before migrations and on a daily schedule, as an operator with Docker access:

```sh
bash deploy/backup-postgres.sh /srv/cybercraft/backups
```

The script uses the configured database/user, writes a private compressed
snapshot, detects pipeline failures, and never claims a partial dump succeeded.
Also back up media, game worlds/server configs and Yggdrasil signing keys.
Schedule with your server's timer/backup system, retain daily/weekly snapshots,
and copy encrypted backups off-host. Avoid including plaintext environment
files in an unencrypted backup. `manage.py backup_db` remains SQLite-only.

Test restore into a **separate** database before relying on a backup:

```sh
# Create/configure a disposable restore database first. This is not production.
gzip -dc /path/to/db.sql.gz | docker compose --env-file .env -f deploy/docker-compose.yml exec -T postgres sh -c 'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d cybercraft_restore_check'
```

Enable shell `set -o pipefail` for restore pipelines, verify data/login against
the restore database, and document recovery time. Record immutable Backend and
Website commit IDs. Build the new Website separately, save worlds and stop
services during replacement, preserve persistent data, apply migrations and
collectstatic, then restart and run smoke checks. Keep the last tested Website
build and Backend revision. Rollback must account for schema changes; restore a
tested snapshot when old code is incompatible with applied migrations.

## Operational limits

- One backend process until Minecraft supervision is moved out of web memory.
- Hard kills/power loss can orphan game state; graceful shutdown is required.
- Console lines are database rows; monitor storage and establish retention.
- WebSocket credentials are checked at connect; existing sockets are not
  continuously reauthenticated. Disconnect sessions when responding to abuse.
- TLS, SMTP, OAuth, installer signing and actual game/mod compatibility require
  checks on the target server and supported client platforms.

## Dependency audit scope

Runtime and installed-graph audits currently report zero findings. However,
Twisted 26.4.0 still contains the IMAP wildcard regex described by
[GHSA-8pqf-f4m5-798g](https://github.com/advisories/GHSA-8pqf-f4m5-798g),
despite metadata excluding that version. CyberCraft does not run an IMAP
service; do not introduce one with this implementation. No audit exemptions
were added. Full local validation is recorded in the Website
`deploy/VALIDATION.md`; actual target TLS/SMTP/game verification remains required.
