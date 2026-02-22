# EC2 cleanup cron (every 20 minutes)

This frees disk space by:
- Deleting **application log files** older than 7 days
- **Pruning the database**: keeping only the **last 20 records** in:
  - Games (also keeps all active/waiting games)
  - Transfers
  - Withdraw requests
  - Deposit requests
  - Broadcast messages (Telegram sent messages)

**Never deletes:** users, transactions, transaction numbers, or any other user data.

## 1. On EC2, make the script executable

```bash
chmod +x /path/to/Markos\ Bingo/scripts/cleanup_ec2_space.sh
```

## 2. Optional: set project path and log retention

If the project is not at `../` relative to the script, set:

```bash
export CLEANUP_LOG_DIR=/home/ubuntu/markos-bingo/logs   # where to delete old .log files
export CLEANUP_LOG_MAX_DAYS=7                           # delete logs older than 7 days
```

## 3. Add cron job (every 20 minutes)

```bash
crontab -e
```

Add this line (replace `/home/ubuntu/markos-bingo` with your actual project path):

```cron
*/20 * * * * /home/ubuntu/markos-bingo/scripts/cleanup_ec2_space.sh >> /var/log/cleanup_ec2.log 2>&1
```

If you need Django env (e.g. DB URL), run from project dir and load env:

```cron
*/20 * * * * cd /home/ubuntu/markos-bingo/backend && set -a && [ -f .env ] && . .env && set +a && /home/ubuntu/markos-bingo/scripts/cleanup_ec2_space.sh >> /var/log/cleanup_ec2.log 2>&1
```

## 4. Test once by hand

```bash
cd /home/ubuntu/markos-bingo
./scripts/cleanup_ec2_space.sh
```

Dry-run (see what would be deleted, no changes):

```bash
cd /home/ubuntu/markos-bingo/backend
python3 manage.py prune_old_data --keep 20 --dry-run
```
