"""
Create a test game for development
Run: python create_test_game.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo.settings')
django.setup()

from api.models import Game

# Create a waiting game
game = Game.objects.create(
    status='waiting',
    bet_amount=10.00,
    derash_amount=0
)

print(f"✅ Test game created!")
print(f"   Game ID: {game.id}")
print(f"   Status: {game.status}")
print(f"   Bet Amount: {game.bet_amount} ETB")
print(f"\nYou can now test the app. The game will appear in the waiting view.")

