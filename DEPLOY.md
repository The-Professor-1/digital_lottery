# Digital Lottery — deployment

This app runs beside CarLottery on the same EC2 instance.

| App | Folder on EC2 | Gunicorn port | Systemd |
|-----|---------------|---------------|---------|
| Car lottery | `~/apps/CarLottery` | `8000` | `carlottery-*` |
| **Digital Lottery** | `~/apps/DigitalLottery` | `8001` | `digitallottery-*` |

The server needs **only Python**. It does **not** need Node/npm, PostgreSQL,
Redis, or Celery. SQLite and Django's file cache are used instead.

---

## Frontend build

The Vue app is built on the development machine and committed to
`backend/frontend_dist`. On the server, the deploy script only pulls that
folder and runs `collectstatic`.

On the dev machine:

```bash
cd frontend
npm ci
npm run build
# then commit backend/frontend_dist and push
```

Or use:

```bash
bash scripts/build_frontend.sh
```

---

## First-time server setup

```bash
ssh -i /path/to/your.pem ubuntu@YOUR_EC2_IP

mkdir -p /home/ubuntu/apps
cd /home/ubuntu/apps
git clone https://github.com/The-Professor-1/digital_lottery.git DigitalLottery
cd DigitalLottery

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env
```

Example `.env`:

```env
SECRET_KEY=<long random>
DEBUG=False
USE_HTTPS=True
ALLOWED_HOSTS=your-domain.com,YOUR_EC2_PUBLIC_IP
CSRF_TRUSTED_ORIGINS=https://your-domain.com
DB_NAME=db.sqlite3
TELEGRAM_BOT_TOKEN=<new bot from BotFather>
TELEGRAM_WEB_APP_URL=https://your-domain.com
JWT_SECRET_KEY=<long random>
PUSH_VAPID_PUBLIC_KEY=
PUSH_VAPID_PRIVATE_KEY=
PUSH_VAPID_SUBJECT=mailto:admin@your-domain.com
```

The VAPID keys can be left empty. The app generates a shared key pair once in
`backend/cache/vapid_keys.json` and reuses it across workers/restarts.

Then:

```bash
cd backend
../venv/bin/python manage.py migrate
../venv/bin/python manage.py createsuperuser
cd ..

sudo cp systemd/digitallottery-gunicorn.service /etc/systemd/system/
sudo cp systemd/digitallottery-telegram-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now digitallottery-gunicorn digitallottery-telegram-bot

# nginx site (replace YOUR_DOMAIN first, or use install_nginx.sh)
sudo cp nginx/nginx.conf /etc/nginx/sites-available/digitallottery
sudo ln -sf /etc/nginx/sites-available/digitallottery /etc/nginx/sites-enabled/digitallottery
sudo nginx -t && sudo systemctl reload nginx
```

---

## Every deploy

Pushing to `main` or `master` runs `.github/workflows/deploy.yml`, which SSHes
into the instance and runs:

```bash
cd ~/apps/DigitalLottery
bash scripts/deploy.sh
```

Manual deploy:

```bash
cd ~/apps/DigitalLottery
bash scripts/deploy.sh
```

The script:

1. pulls the latest code
2. installs Python dependencies
3. verifies `backend/frontend_dist/index.html` exists
4. runs SQLite migrations
5. runs `collectstatic`
6. restarts only `digitallottery-*`

It never touches CarLottery.

---

## Admin browser notifications

Open the admin dashboard over **HTTPS**, log in, and click
**Enable notifications**. Allow the browser permission prompt.

Notifications are sent when a new pending receipt is uploaded. If the button is
hidden, the site is not in a secure context (HTTPS) or the browser does not
support Web Push.

---

## Media / nginx

```bash
chmod -R a+rX ~/apps/DigitalLottery/backend/media
sudo nginx -t && sudo systemctl reload nginx
```

`nginx/nginx.conf` allows 25 MB uploads and proxies `/media/` to Gunicorn.

---

## Do not

- Point this repo's deploy at `CarLottery`.
- Restart `carlottery-*` services from this project.
- Install PostgreSQL/Redis/Celery for this app anymore.
