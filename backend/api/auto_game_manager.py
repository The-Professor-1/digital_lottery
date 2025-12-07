"""
Auto game manager - creates new games after completion
"""
from django.utils import timezone
from datetime import timedelta
from .models import Game, GameSettings
from .game_logic import start_game


def create_new_game_after_completion(completed_game):
    """Create a new waiting game after a game completes"""
    # Get settings from database
    settings = GameSettings.get_settings()
    # Create new game with bet amount from settings
    new_game = Game.objects.create(
        status='waiting',
        bet_amount=settings.bid_amount,
        derash_amount=0
    )
    return new_game


def check_and_create_new_game():
    """Check if we need to create a new game"""
    # Check if there's already a waiting or active game
    existing_game = Game.objects.filter(status__in=['waiting', 'active']).first()
    
    if existing_game:
        return existing_game
    
    # Get the most recent completed game
    last_completed = Game.objects.filter(status='completed').order_by('-completed_at').first()
    
    if last_completed:
        # Create new game with bet amount from settings
        return create_new_game_after_completion(last_completed)
    
    # If no games exist at all, create a new one with bet amount from settings
    settings = GameSettings.get_settings()
    new_game = Game.objects.create(
        status='waiting',
        bet_amount=settings.bid_amount,
        derash_amount=0
    )
    return new_game

