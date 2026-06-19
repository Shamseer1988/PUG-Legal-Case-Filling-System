# Deploy Runbook

There are two supported deployment paths. Pick one.

| Path | Use when |
|---|---|
| **Direct (PugFin-style)** | Single VM, simple ops, the team already runs PugFin this way. |
| **Docker compose (prod)** | Cloud VM, repeatable image builds, no local Python/Node on the host. |

---

## Direct deployment (Linux, systemd + nginx)

### 1. One-time host setup

```bash
sudo useradd -r -m -d /opt/pug-legal -s /bin/bash pug
sudo apt update
sudo apt install -y postgresql-16 redis-server nginx python3.12 python3.12-venv nodejs npm git
```

Generate the encryption secrets and store them in `/etc/pug-legal/.env`
(chmod 600, owner `pug`):

```bash
sudo install -d -o pug -g pug -m 700 /etc/pug-legal
APP_SECRET=$(openssl rand -hex 32)
BACKUP_KEY=$(python3 -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")
sudo -u pug tee /etc/pug-legal/.env >/dev/null <<EOF
APP_ENV=production
APP_SECRET_KEY=${APP_SECRET}
DATABASE_URL=postgresql+psycopg://pug_legal:CHANGE_ME@127.0.0.1:5432/pug_legal
REDIS_URL=redis://127.0.0.1:6379/0
STORAGE_LOCAL_PATH=/var/lib/pug-legal/storage
BACKUP_LOCAL_PATH=/var/lib/pug-legal/backups
CORS_ORIGINS=https://pug-legal.example.com
BACKUP_ENCRYPTION_KEY=${BACKUP_KEY}
BRAND_APP_URL=https://pug-legal.example.com
SECURITY_HEADERS_ENABLED=true
# Optional
SMTP_HOST=
SENTRY_DSN=
EOF
```

Create the data directories:

```bash
sudo install -d -o pug -g pug /var/lib/pug-legal/storage /var/lib/pug-legal/backups
```

### 2. Postgres

```bash
sudo -u postgres psql -c "CREATE USER pug_legal WITH PASSWORD 'CHANGE_ME';"
sudo -u postgres psql -c "CREATE DATABASE pug_legal OWNER pug_legal;"
```

### 3. Clone + build

```bash
sudo -u pug git clone https://github.com/Shamseer1988/PUG-Legal-Case-Filling-System.git /opt/pug-legal
cd /opt/pug-legal/backend
sudo -u pug python3.12 -m venv .venv
sudo -u pug .venv/bin/pip install -e ".[reports]"
sudo -u pug .venv/bin/alembic upgrade head
sudo -u pug .venv/bin/python -m app.services.seed
cd ../frontend
sudo -u pug npm ci
sudo -u pug npm run build
```

### 4. systemd + nginx

```bash
sudo cp /opt/pug-legal/infra/systemd/pug-backend.service /etc/systemd/system/
sudo cp /opt/pug-legal/infra/systemd/pug-frontend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pug-backend pug-frontend

sudo cp /opt/pug-legal/infra/nginx-prod.conf /etc/nginx/nginx.conf
sudo certbot --nginx -d pug-legal.example.com
sudo systemctl reload nginx
```

### 5. Smoke check

```bash
curl -fsSL https://pug-legal.example.com/api/v1/health | jq .
```

---

## Docker compose deployment

```bash
git clone https://github.com/Shamseer1988/PUG-Legal-Case-Filling-System.git
cd PUG-Legal-Case-Filling-System
sudo install -d -m 700 /etc/pug-legal
sudo cp infra/docker-compose.prod.yml /etc/pug-legal/docker-compose.yml
sudo cp backend/.env.example /etc/pug-legal/.env  # edit secrets!

# First boot
sudo docker compose -f /etc/pug-legal/docker-compose.yml --env-file /etc/pug-legal/.env up -d --build

# Migrations + seed
sudo docker compose -f /etc/pug-legal/docker-compose.yml exec backend alembic upgrade head
sudo docker compose -f /etc/pug-legal/docker-compose.yml exec backend python -m app.services.seed
```

TLS certificates are mounted from `/etc/letsencrypt`. Use `certbot` on
the host with `--webroot` against `infra/certbot/`.

---

## Upgrades (zero data loss)

```bash
# 1. Take a fresh backup from the UI: Admin -> Backup & Restore -> Create Backup
# 2. Pull
cd /opt/pug-legal
sudo -u pug git pull --ff-only
# 3. Backend
cd backend
sudo -u pug .venv/bin/pip install -e ".[reports]"
sudo -u pug .venv/bin/alembic upgrade head
# 4. Frontend
cd ../frontend
sudo -u pug npm ci
sudo -u pug npm run build
# 5. Restart
sudo systemctl restart pug-backend pug-frontend
```

For Docker: `docker compose pull && docker compose up -d`.

---

## Post-deploy checklist

- [ ] Sign in as `admin@pug.local` and **change the password immediately**.
- [ ] Enable 2FA for the admin account (Profile -> Set up 2FA).
- [ ] Configure SMTP in **Admin -> System Settings -> Email (SMTP)** and click **Test Send**.
- [ ] Confirm a backup runs cleanly (Admin -> Backup & Restore).
- [ ] Verify the audit chain (Admin -> Audit Log -> Verify Chain).
- [ ] Confirm `https://...` resolves with a valid certificate and the security headers (use `curl -I`).
