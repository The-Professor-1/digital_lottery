"""
Debug and setup script
Run: python debug_setup.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo.settings')
django.setup()

from api.models import Game, User
from django.contrib.auth import get_user_model

User = get_user_model()

print("=" * 50)
print("GEEZ BINGO - DEBUG & SETUP")
print("=" * 50)

# Check if database is connected
try:
    user_count = User.objects.count()
    game_count = Game.objects.count()
    print(f"\n✅ Database connected!")
    print(f"   Users: {user_count}")
    print(f"   Games: {game_count}")
except Exception as e:
    print(f"\n❌ Database error: {e}")
    exit(1)

# Check for active/waiting games
active_games = Game.objects.filter(status__in=['waiting', 'active'])
if active_games.exists():
    print(f"\n📊 Active/Waiting Games:")
    for game in active_games:
        print(f"   Game {game.id}: {game.status} - Bet: {game.bet_amount} ETB")
else:
    print(f"\n⚠️  No active or waiting games found!")
    create = input("   Create a test game? (y/n): ")
    if create.lower() == 'y':
        game = Game.objects.create(
            status='waiting',
            bet_amount=10.00,
            derash_amount=0
        )
        print(f"   ✅ Created Game {game.id} (status: waiting)")

# Check for users
users = User.objects.all()[:5]
if users.exists():
    print(f"\n👥 Users (showing first 5):")
    for user in users:
        print(f"   {user.username} (ID: {user.id}, Balance: {user.balance} ETB)")
else:
    print(f"\n⚠️  No users found. Users will be created when they register via Telegram bot.")

print("\n" + "=" * 50)
print("SETUP COMPLETE!")
print("=" * 50)
print("\nNext steps:")
print("1. Make sure Django server is running: python manage.py runserver")
print("2. Make sure Telegram bot is running: python manage.py runbot")
print("3. Make sure frontend is running: cd frontend && npm run dev")
print("4. Access admin at: http://localhost:8000/admin/")
print("5. Create a game via admin or use the API")

