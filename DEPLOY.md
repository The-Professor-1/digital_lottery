# Digital Lottery — deploy checklist (same EC2 as CarLottery, separate app)

This project must live beside CarLottery, **not** replace it.

| App | Folder on EC2 | Gunicorn port | Systemd | Nginx site |
|-----|---------------|---------------|---------|------------|
| Car lottery | `~/apps/CarLottery` | `8000` | `carlottery-*` | `markosgo.online` |
| **This app** | `~/apps/DigitalLottery` | `8001` | `digitallottery-*` | your new domain |

---

## Security

`.env` is gitignored. Use `.env.example` as the template. Prefer a **new** Telegram bot token for this app (do not reuse the car lottery bot).

---

## Where the AWS `.pem` key goes

| Place | Purpose |
|-------|---------|
| **GitHub → Settings → Secrets → Actions → `EC2_SSH_KEY`** | Full contents of the `.pem` so Actions can SSH and deploy |
| **Your PC** e.g. `C:\Users\Hp\.ssh\digitallottery.pem` | Manual SSH: `ssh -i digitallottery.pem ubuntu@EC2_IP` |
| **EC2 disk** | Do **not** copy the AWS `.pem` onto EC2 for deploy |

Deploy flow: **GitHub Actions SSHs into EC2 → updates only `/home/ubuntu/apps/DigitalLottery`.**

If the GitHub repo is **private**, add a **deploy key** on EC2 for `git fetch`, or make the repo public.

---

## GitHub Actions secrets

Repo → **Settings → Secrets and variables → Actions**

| Secret | Value |
|--------|--------|
| `EC2_HOST` | EC2 public IP or DNS |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | Entire `.pem` file text |

`deploy.yml` uses `APP_DIR=$HOME/apps/DigitalLottery` and restarts only `digitallottery-*` services.

---

## EC2 first-time setup (does not touch CarLottery)

```bash
ssh -i /path/to/your.pem ubuntu@YOUR_EC2_IP

# 1) Clone into a NEW folder
mkdir -p /home/ubuntu/apps
cd /home/ubuntu/apps
git clone https://github.com/The-Professor-1/digital_lottery.git DigitalLottery
cd DigitalLottery

# 2) Python venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3) Env (separate DB + Redis index)
cp .env.example .env
nano .env

# 4) Postgres — NEW database (keep carlottery DB)
sudo -u postgres createuser digitallottery
sudo -u postgres createdb digitallottery -O digitallottery
sudo -u postgres psql -c "ALTER USER digitallottery PASSWORD 'YOUR_DB_PASSWORD';"

# 5) Migrate + frontend
cd backend && python manage.py migrate && python manage.py createsuperuser
cd .. && bash scripts/rebuild_frontend.sh

# 6) Systemd (port 8001)
sudo cp systemd/digitallottery-gunicorn.service /etc/systemd/system/
sudo cp systemd/digitallottery-telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now digitallottery-gunicorn digitallottery-telegram-bot

# 7) Nginx — NEW site only (leave carlottery enabled)
# Edit nginx/nginx.conf: replace YOUR_DOMAIN, then:
#   sudo certbot certonly --nginx -d your.domain.com
#   bash scripts/install_nginx.sh your.domain.com
```

### Variables in `/home/ubuntu/apps/DigitalLottery/.env`

```env
DJANGO_SECRET_KEY=<long random>
DEBUG=False
ALLOWED_HOSTS=your-domain.com,EC2_PUBLIC_IP
CSRF_TRUSTED_ORIGINS=https://your-domain.com
DB_NAME=digitallottery
DB_USER=digitallottery
DB_PASSWORD=YOUR_DB_PASSWORD
DB_HOST=localhost
DB_PORT=5432
REDIS_URL=redis://127.0.0.1:6379/1
TELEGRAM_BOT_TOKEN=<NEW bot from BotFather>
TELEGRAM_WEB_APP_URL=https://your-domain.com
JWT_SECRET_KEY=<long random>
```

After each push to `main`/`master`, Actions updates **only** `/home/ubuntu/apps/DigitalLottery`.

---

## Manual deploy

```bash
ssh -i your.pem ubuntu@YOUR_EC2_IP
cd ~/apps/DigitalLottery
git fetch origin && git reset --hard origin/master
bash scripts/rebuild_frontend.sh
```

---

## Media / admin issues

```bash
sudo cp ~/apps/DigitalLottery/nginx/nginx.conf /etc/nginx/sites-available/digitallottery
# replace YOUR_DOMAIN, or use: bash scripts/install_nginx.sh your.domain.com
sudo nginx -t && sudo systemctl reload nginx
chmod -R a+rX ~/apps/DigitalLottery/backend/media
```

---

## Do not

- Point this repo’s `APP_DIR` at `CarLottery`
- Restart `carlottery-gunicorn` / `carlottery-telegram-bot` from this project’s scripts
- Reuse the car lottery Postgres DB name or Telegram bot token
