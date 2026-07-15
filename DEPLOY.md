# Car Lottery — deploy checklist

## Security (important)

You pasted the Telegram bot token in chat. Prefer regenerating it in [@BotFather](https://t.me/BotFather) (`/revoke` or regenerate token), then put the **new** token only in GitHub Secrets / EC2 `.env` — never in source code.

`.env` is gitignored. Use `.env.example` as the template.

---

## Where the AWS `.pem` key goes

The `.pem` AWS gave you is for **SSH into EC2**. It is **not** for `git pull` on the server.

| Place | Purpose |
|-------|---------|
| **GitHub → Settings → Secrets → Actions → `EC2_SSH_KEY`** | Full contents of the `.pem` so Actions can SSH and deploy |
| **Your PC** e.g. `C:\Users\Hp\.ssh\carlottery.pem` | Manual SSH: `ssh -i carlottery.pem ubuntu@EC2_IP` |
| **EC2 disk** | Do **not** copy the AWS `.pem` onto EC2 for deploy |

Deploy flow: **GitHub Actions uses the `.pem` (as `EC2_SSH_KEY`) → SSHs into EC2 → runs `git pull` + restart services.**

If the GitHub repo is **private**, also add a **deploy key** on EC2 (separate SSH keypair; public key in GitHub Deploy Keys) so `git fetch` works on the server. Or make the repo public.

---

## GitHub Actions secrets

Repo → **Settings → Secrets and variables → Actions**

| Secret | Value |
|--------|--------|
| `EC2_HOST` | EC2 public IP or DNS |
| `EC2_USER` | `ubuntu` (Amazon Linux often `ec2-user`) |
| `EC2_SSH_KEY` | Entire `.pem` file text including `-----BEGIN ... KEY-----` |

Optional later: `TELEGRAM_BOT_TOKEN` only if you inject secrets from Actions; currently the bot reads **EC2 `.env`**, not GitHub secrets.

---

## EC2 first-time setup (SSH console)

```bash
# 1) SSH from your PC
ssh -i /path/to/carlottery.pem ubuntu@YOUR_EC2_IP

# 2) Packages
sudo apt update && sudo apt install -y python3-venv python3-pip nginx redis-server postgresql postgresql-contrib git nodejs npm

# 3) App directory
mkdir -p /home/ubuntu/apps
cd /home/ubuntu/apps
git clone https://github.com/The-Professor-1/CarLottery.git
cd CarLottery

# 4) Python venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5) Env file (create once; never commit)
cp .env.example .env
nano .env
# set TELEGRAM_BOT_TOKEN, DATABASE_URL, DJANGO_SECRET_KEY, TELEGRAM_WEB_APP_URL, ALLOWED_HOSTS, etc.

# 6) Postgres DB
sudo -u postgres createuser carlottery
sudo -u postgres createdb carlottery -O carlottery
sudo -u postgres psql -c "ALTER USER carlottery PASSWORD 'YOUR_DB_PASSWORD';"

# 7) Migrate + frontend build
cd backend && python manage.py migrate && python manage.py createsuperuser
cd ../frontend && npm ci && npm run build && cd ..

# 8) Systemd units
sudo cp systemd/carlottery-gunicorn.service /etc/systemd/system/
sudo cp systemd/carlottery-telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now carlottery-gunicorn carlottery-telegram-bot redis-server

# 9) Nginx — copy/adapt nginx/nginx.conf for your domain, then:
# sudo ln -s ... && sudo systemctl reload nginx
```

### Variables to set in `/home/ubuntu/apps/CarLottery/.env` on EC2

```env
DJANGO_SECRET_KEY=<long random>
DEBUG=False
ALLOWED_HOSTS=your-domain.com,EC2_PUBLIC_IP
CSRF_TRUSTED_ORIGINS=https://your-domain.com
DATABASE_URL=postgres://carlottery:YOUR_DB_PASSWORD@localhost:5432/carlottery
REDIS_URL=redis://127.0.0.1:6379/0
TELEGRAM_BOT_TOKEN=<from BotFather>
TELEGRAM_WEB_APP_URL=https://your-domain.com
JWT_SECRET_KEY=<long random>
```

After each push to `main`/`master`, GitHub Actions SSHs in and pulls this path: `/home/ubuntu/apps/CarLottery`.

---

## GitHub Actions SSH timeout (`dial tcp :22: i/o timeout`)

GitHub runners use **dynamic IPs**. If EC2 Security Group SSH is limited to **My IP**, Actions will always fail.

**Fix:** EC2 → Security groups → Inbound → add **SSH 22** from `0.0.0.0/0` (or deploy manually below).

**Manual deploy** (from your PC, while SSH works for you):

```bash
ssh -i your.pem ubuntu@YOUR_EC2_IP
cd ~/apps/CarLottery
git fetch origin && git reset --hard origin/master
bash scripts/rebuild_frontend.sh
```

Also verify GitHub secret **`EC2_HOST`** is the current **Elastic IP** (not an old IP).

---

## Admin panel “HTML instead of JSON”

Usually means the **backend on EC2 is older than the frontend** (Actions deploy failed, only `npm run build` was run). Run `bash scripts/rebuild_frontend.sh` on EC2 — it pulls code, migrates, rebuilds, and restarts gunicorn.

Ensure nginx serves media from `backend/media/` (see `nginx/nginx.conf`).

---

## Kept vs removed

**Kept:** payment verify (`telebirr_verify`, CBE receipt APIs), Telegram bot + lottery handlers, gunicorn/bot systemd units, nginx, celery scripts, admin/second-admin APIs.

**Removed:** old bingo Vue game screens/components, bingo docs, AWS scale scripts, unrelated proposal files.
