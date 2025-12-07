"""
Script to create .env file with your database credentials
Run this: python create_env.py
"""
import secrets
from django.core.management.utils import get_random_secret_key

# Generate secret key
secret_key = get_random_secret_key()

# Database connection string (Neon PostgreSQL)
DATABASE_URL=postgresql://neondb_owner:npg_7KyNdcolwH3X@ep-small-bird-a4fsod31-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require

env_content = f"""# Django Settings
SECRET_KEY={secret_key}
DEBUG=True

# Database Configuration (using DATABASE_URL - preferred by settings.py)
DATABASE_URL={DATABASE_URL}

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=8271818999:AAEaiKyeze_B5Af_FoCi43kecf3X__dDEQw
TELEGRAM_WEB_APP_URL=https://markos-bingo.fly.dev

# JWT Configuration
JWT_SECRET_KEY={secret_key}
"""

# Write to .env file
with open('.env', 'w') as f:
    f.write(env_content)

print("✅ .env file created successfully!")
print("\n📝 Next steps:")
print("1. Get your Telegram bot token from @BotFather")
print("2. Replace 'your-telegram-bot-token-here' in .env with your actual token")
print("3. Run: python manage.py makemigrations")
print("4. Run: python manage.py migrate")

