"""
Test card selection directly
Run: python test_card_selection.py
"""
import os
import django
import requests

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bingo.settings')
django.setup()

from api.models import Game, User

# Get the current game
game = Game.objects.filter(status='waiting').first()

if not game:
    print("❌ No waiting game found. Create one first with: python create_test_game.py")
    exit(1)

print(f"Testing card selection for Game {game.id}")
print(f"Game status: {game.status}")
print(f"Bet amount: {game.bet_amount}")

# Test API call
url = f"http://localhost:8000/api/games/{game.id}/select-card/"
data = {"card_number": 1}

print(f"\nMaking POST request to: {url}")
print(f"Data: {data}")

try:
    response = requests.post(url, json=data)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 201:
        print("\n✅ Card selection successful!")
    else:
        print(f"\n❌ Error: {response.json()}")
except Exception as e:
    print(f"\n❌ Exception: {e}")

