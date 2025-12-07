#!/bin/bash
# Fly.io Deployment Script for Markos Bingo
# Run this script after providing the required information

set -e

# Check if required parameters are provided
if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: ./deploy.sh <app-name> <telegram-bot-token> [secret-key] [jwt-secret-key]"
    echo "Example: ./deploy.sh markos-bingo YOUR_BOT_TOKEN"
    exit 1
fi

APP_NAME=$1
TELEGRAM_BOT_TOKEN=$2
SECRET_KEY=${3:-$(openssl rand -hex 32)}
JWT_SECRET_KEY=${4:-$(openssl rand -hex 32)}
WEB_APP_URL="https://${APP_NAME}.fly.dev"

echo "🚀 Starting deployment for app: $APP_NAME"

echo ""
echo "Step 1: Creating/updating Fly app..."
fly launch --no-deploy --name $APP_NAME

echo ""
echo "Step 2: Attaching PostgreSQL database..."
fly postgres attach --app $APP_NAME bingo_db

echo ""
echo "Step 3: Creating Redis instance..."
fly redis create --name "${APP_NAME}-redis" --region iad || echo "Redis might already exist"
fly redis attach --app $APP_NAME "${APP_NAME}-redis" || echo "Redis might already be attached"

echo ""
echo "Step 4: Setting environment variables..."
fly secrets set --app $APP_NAME \
    SECRET_KEY="$SECRET_KEY" \
    JWT_SECRET_KEY="$JWT_SECRET_KEY" \
    DEBUG="False" \
    TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
    TELEGRAM_WEB_APP_URL="$WEB_APP_URL" \
    ALLOWED_HOSTS="$APP_NAME.fly.dev,web.telegram.org" \
    CORS_ALLOWED_ORIGINS="$WEB_APP_URL,https://web.telegram.org"

echo ""
echo "Step 5: Deploying application..."
fly deploy --app $APP_NAME

echo ""
echo "Step 6: Running migrations..."
fly ssh console --app $APP_NAME -C "python manage.py migrate"

echo ""
echo "Step 7: Creating superuser (if needed)..."
echo "You can create a superuser by running:"
echo "  fly ssh console --app $APP_NAME -C 'python manage.py createsuperuser'"

echo ""
echo "Step 8: Starting Telegram bot..."
echo "The bot can be started with:"
echo "  fly ssh console --app $APP_NAME -C 'python manage.py runbot'"
echo "Or set up a separate worker process."

echo ""
echo "✅ Deployment complete!"
echo "Your app is available at: $WEB_APP_URL"
echo ""
echo "Next steps:"
echo "1. Update your Telegram bot's web app URL to: $WEB_APP_URL"
echo "2. Test the bot and web app"
echo "3. Set up the bot as a worker (optional)"

