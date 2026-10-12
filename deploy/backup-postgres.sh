#!/usr/bin/env bash
# Creates a database snapshot; game worlds/media require a separate backup.
set -euo pipefail
umask 077
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
backup_dir=${1:-/srv/cybercraft/backups}
mkdir -p -- "$backup_dir"
archive="$backup_dir/db-$(date -u +%Y%m%dT%H%M%S)-$$.sql.gz"
partial="$archive.partial"
trap 'rm -f -- "$partial"' EXIT
docker compose --env-file "$root/.env" -f "$root/deploy/docker-compose.yml" \
  exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  | gzip > "$partial"
gzip -t "$partial"
mv -- "$partial" "$archive"
trap - EXIT
printf 'Backup created: %s\n' "$archive"
