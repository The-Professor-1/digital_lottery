# Digital Lottery — Google Cloud deployment

This app can run beside CarLottery on the same VM, or on its own GCP VM.

| App | Folder | Gunicorn port | Systemd |
|-----|--------|---------------|---------|
| Car lottery | `~/apps/CarLottery` | `8000` | `carlottery-*` |
| **Digital Lottery** | `~/apps/DigitalLottery` | `8001` | `digitallottery-*` |

The VM needs **only Python**. It does **not** need Node/npm, PostgreSQL, Redis,
or Celery. SQLite and Django's file cache are used.

---

## GitHub Actions secrets

Create these in **GitHub → repository → Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|--------|-------|
| `GCP_VM_HOST` | VM external IP, for example `34.123.45.67`, or a DNS name |
| `GCP_VM_USER` | The SSH user shown by `whoami` on the VM |
| `GCP_VM_SSH_KEY` | Full private key used by GitHub Actions (OpenSSH format) |
| `GCP_VM_APP_DIR` | Optional: `/home/YOUR_USER/apps/DigitalLottery` |

If `GCP_VM_APP_DIR` is not set, the workflow uses `$HOME/apps/DigitalLottery`.

The public half of `GCP_VM_SSH_KEY` must be in the VM user's
`~/.ssh/authorized_keys`, or added as a GCP metadata SSH key.

---

## GCP firewall

GitHub-hosted runners connect from changing public IPs. Allow SSH:

```bash
gcloud compute firewall-rules create allow-github-ssh \
  --allow tcp:22 \
  --source-ranges 0.0.0.0/0 \
  --target-tags=http-server
```

For stricter security, use a self-hosted runner or Cloud IAP instead.

---

## First-time VM setup

SSH into the VM:

```bash
gcloud compute ssh YOUR_VM_NAME --zone YOUR_ZONE
```

Install system packages (Ubuntu/Debian):

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git nginx
```

Clone the repo:

```bash
mkdir -p "$HOME/apps"
cd "$HOME/apps"
git clone https://github.com/The-Professor-1/digital_lottery.git DigitalLottery
cd DigitalLottery
```

Create the Python environment:

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Create `.env` from `.env.example`:

```bash
cp .env.example .env
nano .env
```

Example:

```env
SECRET_KEY=<long random>
DEBUG=False
USE_HTTPS=True
ALLOWED_HOSTS=your-domain.com,YOUR_VM_PUBLIC_IP
CSRF_TRUSTED_ORIGINS=https://your-domain.com
DB_NAME=db.sqlite3
TELEGRAM_BOT_TOKEN=<new bot from BotFather>
TELEGRAM_WEB_APP_URL=https://your-domain.com
JWT_SECRET_KEY=<long random>
PUSH_VAPID_PUBLIC_KEY=
PUSH_VAPID_PRIVATE_KEY=
PUSH_VAPID_SUBJECT=mailto:admin@your-domain.com
```

VAPID keys can stay empty; the app generates a shared pair in
`backend/cache/vapid_keys.json` once and reuses it.

Run migrations and create the admin:

```bash
cd backend
../venv/bin/python manage.py migrate
../venv/bin/python manage.py createsuperuser
cd ..
```

Install systemd units. If your VM user is not `ubuntu`, edit only `User=` and
`Group=` first (paths use `%h`, the configured user's home):

```bash
sudo cp systemd/digitallottery-gunicorn.service /etc/systemd/system/
sudo cp systemd/digitallottery-telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now digitallottery-gunicorn digitallottery-telegram-bot
```

The deploy user needs **passwordless sudo** for service restarts. GCP users are
usually in `google-sudoers`; verify with:

```bash
sudo -n true && echo "passwordless sudo OK"
```

If that fails, grant the deploy user passwordless sudo:

```bash
sudo tee /etc/sudoers.d/digitallottery-deploy >/dev/null <<EOF
$(whoami) ALL=(ALL) NOPASSWD: ALL
EOF
sudo chmod 440 /etc/sudoers.d/digitallottery-deploy
sudo -n true && echo "passwordless sudo OK"
```

The deploy script installs the systemd units, runs `daemon-reload`, enables
the services, and restarts them. A narrow sudoers rule is possible, but it must
allow both `systemctl` and `cp` (used only for the first-time unit install).

Install nginx:

```bash
sudo cp nginx/nginx.conf /etc/nginx/sites-available/digitallottery
sudo ln -sf /etc/nginx/sites-available/digitallottery /etc/nginx/sites-enabled/digitallottery
sudo nginx -t && sudo systemctl reload nginx
```

---

## Frontend build

The Vue app is built on the development machine and committed to
`backend/frontend_dist`. The VM never runs npm.

On the dev machine:

```bash
cd frontend
npm ci
npm run build
git add backend/frontend_dist
git commit -m "build frontend"
git push
```

Or:

```bash
bash scripts/build_frontend.sh
```

---

## Deploy

Every push to `master` or `main` runs:

```text
GitHub Actions → SSH to GCP VM → bash scripts/deploy.sh
```

The script pulls the repo, installs Python deps, runs SQLite migrations,
collects static files, and restarts only `digitallottery-*`.

Manual deploy:

```bash
cd "$HOME/apps/DigitalLottery"
bash scripts/deploy.sh
```

---

## Git access on the VM

If the repository is private, the VM also needs pull access:

- **Deploy key:** add the VM's public key under GitHub → Settings → Deploy keys
  (read-only), or
- use a personal access token in the clone URL.

The GitHub Actions SSH key and the VM's Git pull key are separate.

---

## Admin browser notifications

Open the admin dashboard over **HTTPS**, log in, and click
**Enable notifications**. Allow the browser prompt. A notification is sent when
a new pending screenshot receipt is uploaded.

---

## Data note

Switching from Postgres to SQLite starts a new empty SQLite database. Back up
Postgres first if you need the existing users, settings, purchases, or winners.

```bash
pg_dump YOUR_DB_NAME > digitallottery-backup.sql
```

Do not point this deploy at `CarLottery`, and do not restart `carlottery-*`
services from this project.
