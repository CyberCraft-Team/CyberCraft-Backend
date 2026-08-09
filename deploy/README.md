# Deploying the CyberCraft backend

Target: a single Linux VPS. Postgres and Redis run in Docker; Django runs on
the host under systemd; nginx terminates HTTP and serves `/static/` and
`/media/` directly.

## Why Django is not containerised

Django spawns each Minecraft server as a child process and controls it
through that process's stdin pipe. Putting the web app in a container would
mean baking a JVM into the image, bind-mounting the entire `servers/` tree,
and accepting that a container restart kills every running game server.
P3 moves server supervision into a dedicated host process, which would undo
that work anyway.

Postgres and Redis have none of those constraints, so they get containers.

## Prerequisites

- Ubuntu 22.04 or newer, Docker with the compose plugin, nginx
- Python 3.13 with `python3.13-venv`
- A `cybercraft` service user
- Java 21 for the game servers

## Steps

**1. Lay out the tree**

```bash
sudo mkdir -p /srv/cybercraft
sudo chown cybercraft:cybercraft /srv/cybercraft
sudo -u cybercraft git clone https://github.com/CyberCraft-Team/CyberCraft-Backend.git /srv/cybercraft/backend
cd /srv/cybercraft/backend
sudo -u cybercraft python3.13 -m venv env
sudo -u cybercraft env/bin/pip install -r requirements.txt
```

**2. Configure**

```bash
sudo -u cybercraft cp .env.example .env
sudo -u cybercraft nano .env
```

Required in production — the app refuses to start without them:

| Variable | Note |
|---|---|
| `PRODUCTION` | `1`. Selects `config/settings/prod.py`. |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ALLOWED_HOSTS` | Comma-separated. Empty raises `ImproperlyConfigured`. |
| `REDIS_URL` | Required. The channel layer must be shared across processes. |
| `DATABASE_URL` | Or `DB_NAME`/`DB_USER`/`DB_PASSWORD`, or `USE_SQLITE=1`. |
| `BACKEND_URL` | Absolute public URL. Baked into every server's authlib-injector agent — a wrong value here silently breaks in-game login. |

**3. Start Postgres and Redis**

```bash
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml ps
```

Compose reads `DB_NAME`, `DB_USER` and `DB_PASSWORD` from the shell, so
export them or run with `--env-file .env`.

**4. Migrate and collect static**

```bash
sudo -u cybercraft PRODUCTION=1 env/bin/python manage.py migrate
sudo -u cybercraft PRODUCTION=1 env/bin/python manage.py collectstatic --no-input
sudo -u cybercraft PRODUCTION=1 env/bin/python manage.py createsuperuser
```

**5. Start the web process**

```bash
sudo cp deploy/cybercraft-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cybercraft-web
sudo systemctl status cybercraft-web
```

**6. nginx**

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/cybercraft
sudo nano /etc/nginx/sites-available/cybercraft     # set server_name
sudo ln -s /etc/nginx/sites-available/cybercraft /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

**7. TLS**

```bash
sudo certbot --nginx -d api.cybercraft.uz
```

Then set `USE_SSL=1` in `.env` and `sudo systemctl restart cybercraft-web`.
That turns on HSTS, secure cookies and the SSL redirect. Setting it before
a certificate exists locks you out with a redirect loop.

## Verifying

```bash
curl -fsS https://api.cybercraft.uz/api/v1/health/ && echo OK
curl -fsS https://api.cybercraft.uz/api/v1/yggdrasil/ | head -c 200
curl -fsSI https://api.cybercraft.uz/media/  # must be served by nginx, not Django
sudo journalctl -u cybercraft-web -n 50
```

Confirm the settings that were silently wrong before:

```bash
sudo -u cybercraft PRODUCTION=1 env/bin/python -c "
import django; django.setup()
from django.conf import settings as s
print('DEBUG', s.DEBUG)
print('DB', s.DATABASES['default']['ENGINE'])
print('channels', s.CHANNEL_LAYERS['default']['BACKEND'])
"
```

Expected: `False`, `django.db.backends.postgresql`, `channels_redis.core.RedisChannelLayer`.

## Backups

```bash
sudo -u cybercraft PRODUCTION=1 env/bin/python manage.py backup_db
```

`backup_db` is SQLite-only — it does `shutil.copy2` on `db.sqlite3`. Under
Postgres use `pg_dump` instead:

```bash
docker compose -f deploy/docker-compose.yml exec -T postgres \
  pg_dump -U cybercraft cybercraft | gzip > /srv/cybercraft/backups/db-$(date +%F).sql.gz
```

Teaching `backup_db` about Postgres is open work, tracked for a later phase.

## Known limits

- **One web process.** `MinecraftServerManager` keeps process state in class
  attributes, so a second worker would not see servers started by the first.
  The systemd unit runs a single Daphne. P3 fixes this.
- **`atexit` does not run on SIGKILL.** A hard kill orphans Java processes
  with stale `pid` and `status=running` rows. `KillMode=mixed` and a 90 s
  stop timeout give the handler room on a normal stop.
- **Server console lines are one DB row each.** Under Postgres this is far
  safer than SQLite, but a chatty server still writes steadily. P3 moves log
  tailing off the database.
