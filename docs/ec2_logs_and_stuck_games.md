# EC2 logs and stuck games

## Viewing logs

All services log to **systemd journal**. Use `journalctl` (you may need `sudo`).

### 1. API / Gunicorn (Django, WebSockets, end-game, admin)

```bash
journalctl -u bingo-gunicorn.service -f
```

- **-f** = follow (live tail). Omit to see recent lines only.
- Use this to see API errors (e.g. 400/500 when clicking "End" or "Force end"), WebSocket and request logs.

### 2. Telegram bot

```bash
journalctl -u bingo-telegram-bot.service -f
```

### 3. Celery worker (number calling, game tasks, registration rewards)

Find the exact service name (often `celery.service` or similar):

```bash
systemctl list-units --type=service | grep -i celery
```

Then tail logs, for example:

```bash
journalctl -u celery.service -f
```

- If the **game is stuck** and numbers are not being called, Celery is the first place to check (worker down or task errors).

### Useful journalctl options

| Option | Effect |
|--------|--------|
| `-f` | Follow (live tail) |
| `-n 200` | Last 200 lines |
| `-u bingo-gunicorn.service` | Only that unit |
| `--since "10 min ago"` | Last 10 minutes |
| `--no-pager` | No pager (e.g. in scripts) |

Example: last 100 lines of Gunicorn, then exit:

```bash
journalctl -u bingo-gunicorn.service -n 100 --no-pager
```

---

## Game stuck on ActiveGameView

### Why it happens

- The **game stays "active"** until either:
  - All 75 numbers are called and someone wins (or no winner), or
  - The game is ended manually (admin).
- If the **Celery worker** that calls numbers is down or failing, numbers stop and the game never completes.
- The normal **"End"** button in the admin dashboard only works when **all 75 numbers** have been called. If the game is stuck with fewer numbers, "End" returns an error and does nothing.

### What to do

1. **Check Celery is running**
   ```bash
   systemctl status celery.service   # or your Celery unit name
   ```
   If it’s down, fix and restart:
   ```bash
   sudo systemctl start celery.service
   ```

2. **Force-end the stuck game (admin only)**
   - In **Admin Dashboard** → **Active Games**, find the stuck game.
   - Click **"Force end"** (not "End").
   - Confirm. This ends the game even if fewer than 75 numbers were called, so players can leave the stuck screen and start a new round.

3. **Restart services if needed**
   ```bash
   sudo systemctl restart bingo-gunicorn.service
   sudo systemctl restart celery.service
   sudo systemctl restart bingo-telegram-bot.service
   ```

4. **Inspect API errors**
   - Tail Gunicorn logs while you click "End" or "Force end":
     ```bash
     journalctl -u bingo-gunicorn.service -f
     ```
   - You’ll see the request and any 400/500 response or traceback.

---

## Summary

| Problem | Where to look | Action |
|--------|----------------|--------|
| "End" does nothing / error | Gunicorn logs | Use **"Force end"** for stuck games (admin only). |
| Numbers not calling / game stuck | Celery logs + status | Restart Celery; then Force end the game. |
| Registration / bot issues | Telegram bot logs | `journalctl -u bingo-telegram-bot.service -f` |
| API/WebSocket errors | Gunicorn logs | `journalctl -u bingo-gunicorn.service -f` |
