#!/bin/bash
set -e

# Function to handle bot process with automatic restart
# Run in subshell with error handling to prevent failures from stopping main script
(
    set +e  # Don't exit on error in bot process
    while true; do
        echo "[$(date)] Starting Telegram bot..."
        python manage.py runbot 2>&1 || {
            EXIT_CODE=$?
            echo "[$(date)] Bot process exited with error code $EXIT_CODE. Restarting in 10 seconds..."
        }
        sleep 10
    done
) > /tmp/bot.log 2>&1 &

# Capture bot PID for potential cleanup (though exec will orphan it)
BOT_PID=$!
echo "[$(date)] Bot started in background (PID: $BOT_PID)"

# Give bot a moment to initialize (but continue even if it fails)
# Wait longer to ensure bot has time to connect to database and Telegram API
sleep 5 || true

# Run Django ASGI server (foreground with exec - this keeps container alive)
# This MUST run and will replace the shell process
echo "[$(date)] Starting Django ASGI server..."
exec daphne -b 0.0.0.0 -p 8000 bingo.asgi:application

