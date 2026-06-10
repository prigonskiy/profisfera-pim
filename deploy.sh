#!/usr/bin/env bash
# Скрипт деплоя: запускается на сервере (вручную или из GitHub Actions).
set -euo pipefail
cd /srv/pim

echo "==> Забираем изменения из main"
git pull --ff-only origin main

echo "==> Зависимости"
source venv/bin/activate
pip install -r requirements-prod.txt

echo "==> Миграции БД"
python manage.py migrate --noinput

echo "==> Сборка статики"
python manage.py collectstatic --noinput

echo "==> Перезапуск gunicorn"
sudo systemctl restart pim

echo "==> Готово"
