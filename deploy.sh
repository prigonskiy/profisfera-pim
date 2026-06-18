#!/usr/bin/env bash
# Скрипт деплоя: запускается на сервере (вручную или из GitHub Actions).
set -euo pipefail
cd /srv/pim

echo "==> Забираем изменения из main"
git pull --ff-only origin main

echo "==> Зависимости"
source venv/bin/activate
pip install -r requirements-prod.txt

echo "==> Бэкап БД перед миграциями"
set -a; source .env 2>/dev/null || true; set +a
if [ "${DB_ENGINE:-}" = "postgres" ]; then
  BACKUP_DIR=/srv/pim-backups
  mkdir -p "$BACKUP_DIR"
  PGPASSWORD="${DB_PASSWORD:-}" pg_dump -Fc \
    -h "${DB_HOST:-127.0.0.1}" -p "${DB_PORT:-5432}" \
    -U "${DB_USER:-pim}" "${DB_NAME:-pim}" \
    > "$BACKUP_DIR/pim-$(date +%Y%m%d-%H%M%S).dump"
  echo "    бэкап сохранён в $BACKUP_DIR (храним последние 10)"
  ls -1t "$BACKUP_DIR"/*.dump 2>/dev/null | tail -n +11 | xargs -r rm -f
else
  echo "    (БД не postgres — бэкап пропущен)"
fi

echo "==> Миграции БД"
python manage.py migrate --noinput

echo "==> Сборка статики"
python manage.py collectstatic --noinput

echo "==> Перезапуск gunicorn"
sudo systemctl restart pim

echo "==> Готово"
