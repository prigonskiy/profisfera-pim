# Деплой на VPS (этап 5)

Развёртывание на чистом Ubuntu 24. Сейчас: доступ по IP, HTTP, PostgreSQL,
gunicorn за nginx, автодеплой из GitHub Actions. HTTPS добавим, когда будет
домен (раздел в конце).

> **Безопасность.** Пока без HTTPS вход в админку и токены идут по открытому
> HTTP. Для первичного запуска это терпимо, но до выхода на реальных
> пользователей заведите домен и включите HTTPS. Файл `.env` с паролями и
> ключом в репозиторий не коммитится (он в `.gitignore`).

Подставьте свои значения вместо `<IP-сервера>`, `<логин-на-github>`,
`<пароль-БД>`, `<секретный-ключ>`.

---

## Часть 1. Разовая настройка сервера (под root)

### 1.1. Системные пакеты

```bash
apt update && apt upgrade -y
apt install -y python3-venv python3-pip postgresql nginx git
```

### 1.2. Отдельный пользователь для приложения

```bash
adduser --disabled-password --gecos "" pim
mkdir -p /srv/pim
chown pim:pim /srv/pim
```

### 1.3. База данных PostgreSQL

```bash
sudo -u postgres psql -c "CREATE USER pim WITH PASSWORD '<пароль-БД>';"
sudo -u postgres psql -c "CREATE DATABASE pim OWNER pim;"
```

### 1.4. Доступ к репозиторию

**Если репозиторий публичный** — пропустите этот шаг, будем клонировать по https.

**Если приватный** — заведём read-only deploy key. От имени пользователя `pim`:

```bash
su - pim
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub        # скопируйте вывод
```

Вставьте этот ключ на GitHub: репозиторий → Settings → Deploy keys → Add key
(права только на чтение). Затем настройте git использовать его:

```bash
cat >> ~/.ssh/config << 'CFG'
Host github.com
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
CFG
chmod 600 ~/.ssh/config
exit                                  # вернуться в root
```

### 1.5. Код, окружение, .env

От имени `pim`:

```bash
su - pim

# публичный репозиторий:
git clone https://github.com/<логин-на-github>/profisfera-pim.git /srv/pim
# или приватный (после шага 1.4):
# git clone git@github.com:<логин-на-github>/profisfera-pim.git /srv/pim

cd /srv/pim
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-prod.txt
```

Сгенерируйте секретный ключ:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Создайте `/srv/pim/.env` (например, `nano .env`):

```
SECRET_KEY=<секретный-ключ>
DEBUG=0
ALLOWED_HOSTS=<IP-сервера>
CSRF_TRUSTED_ORIGINS=http://<IP-сервера>
COOKIE_SECURE=0

DB_ENGINE=postgres
DB_NAME=pim
DB_USER=pim
DB_PASSWORD=<пароль-БД>
DB_HOST=localhost
DB_PORT=5432
```

Примените миграции, соберите статику, создайте администратора:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
exit                                  # вернуться в root
```

### 1.6. Сервис gunicorn (systemd)

```bash
cp /srv/pim/deploy/pim.service /etc/systemd/system/pim.service
systemctl daemon-reload
systemctl enable --now pim
systemctl status pim --no-pager       # должно быть active (running)
```

### 1.7. nginx

```bash
cp /srv/pim/deploy/nginx-pim.conf /etc/nginx/sites-available/pim
ln -s /etc/nginx/sites-available/pim /etc/nginx/sites-enabled/pim
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
```

### 1.8. Файрвол

```bash
ufw allow OpenSSH
ufw allow 'Nginx HTTP'
ufw --force enable
```

### 1.9. Проверка

Откройте в браузере:
- `http://<IP-сервера>/admin/` — вход в админку.
- `http://<IP-сервера>/api/` — браузерный интерфейс API.

---

## Часть 2. Автодеплой через GitHub Actions

Идея: `git push` в `main` → Actions заходит на сервер по SSH под `pim` и
запускает `deploy.sh` (pull, зависимости, миграции, статика, перезапуск).

### 2.1. Право перезапускать сервис без пароля

Чтобы `deploy.sh` мог перезапускать gunicorn. Под root:

```bash
echo 'pim ALL=(root) NOPASSWD: /usr/bin/systemctl restart pim' > /etc/sudoers.d/pim-deploy
chmod 440 /etc/sudoers.d/pim-deploy
visudo -c                             # проверка синтаксиса sudoers
```

### 2.2. SSH-ключ для Actions

Сгенерируйте **отдельную** пару ключей у себя на компьютере (Git Bash):

```bash
ssh-keygen -t ed25519 -f gha_deploy -N ""
```

- Содержимое `gha_deploy.pub` — добавьте на сервер пользователю `pim`. Под root:

```bash
su - pim
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "ВСТАВЬТЕ_СОДЕРЖИМОЕ_gha_deploy.pub" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

- Содержимое приватного `gha_deploy` (целиком) — в секрет GitHub. Приватный
  ключ никому не пересылайте, кроме как в секреты вашего репозитория.

### 2.3. Секреты репозитория

GitHub → репозиторий → Settings → Secrets and variables → Actions → New secret:

- `SSH_HOST` = `<IP-сервера>`
- `SSH_USER` = `pim`
- `SSH_PRIVATE_KEY` = содержимое файла `gha_deploy` (приватный ключ)

### 2.4. Запуск

Файлы `.github/workflows/deploy.yml` и `deploy.sh` уже в репозитории. После
любого `push` в `main` деплой пойдёт сам. Прогресс — во вкладке **Actions** на
GitHub. Можно проверить, поправив что-нибудь и запушив.

---

## HTTPS (когда появится домен)

1. Заведите домен и пропишите A-запись на `<IP-сервера>`.
2. В `/etc/nginx/sites-available/pim` замените `server_name _;` на ваш домен.
3. Установите certbot и получите сертификат:

   ```bash
   apt install -y certbot python3-certbot-nginx
   certbot --nginx -d ваш-домен.ru
   ```

4. В `/srv/pim/.env` обновите:

   ```
   ALLOWED_HOSTS=ваш-домен.ru
   CSRF_TRUSTED_ORIGINS=https://ваш-домен.ru
   COOKIE_SECURE=1
   BEHIND_TLS_PROXY=1
   ```

5. Перезапустите: `systemctl restart pim && systemctl restart nginx`.
