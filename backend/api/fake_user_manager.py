"""
Fake User Management System
Handles fake user accounts for simulating players in games
"""
import random
import asyncio
from typing import List, Dict, Optional, Tuple
from django.utils import timezone
from decimal import Decimal
from .models import FakeUser, FakeUserGameCard, Game, GameSettings, GameCard
from .game_logic import generate_bingo_card


# Predefined list of 30 fake user names
FAKE_USER_NAMES = [
    'abel_xo', 'yaredo', 'tekle', 'seesy', 'daniel', 'sinamaw', 'great', 'abathun',
    'likinaw', 'abrsh', 'abrham', 'dani_boy', 'aman', 'amanuel', 'ayu_091', 'ayenew',
    'yohanes', 'yoni', 'beki', 'user_1085371232', 'user_1085371388', 'user_9823892323',
    'user_2223989876', 'ተሾመ', 'ዘላለም', 'ተክሉ', 'ሰለሞን', 'አንቴ', 'ዮሴፍ', 'ብሩክ'
]


def initialize_fake_users():
    """Initialize all fake users in the database"""
    for name in FAKE_USER_NAMES:
        FakeUser.objects.get_or_create(name=name, defaults={'is_active': True})


def get_random_fake_users(count: int) -> List[FakeUser]:
    """Get random fake users (between 20-30)"""
    active_users = list(FakeUser.objects.filter(is_active=True))
    if not active_users:
        initialize_fake_users()
        active_users = list(FakeUser.objects.filter(is_active=True))
    
    # Select random count (between 20-30)
    count = min(count, len(active_users))
    return random.sample(active_users, count)


def create_fake_user_card(game: Game, fake_user: FakeUser, card_number: int) -> FakeUserGameCard:
    """Create a game card for a fake user"""
    # Check if fake user already has a card for this game
    existing_card = FakeUserGameCard.objects.filter(game=game, fake_user=fake_user).first()
    if existing_card:
        return existing_card
    
    # Check if card number is already taken (by real or fake user)
    if GameCard.objects.filter(game=game, card_number=card_number).exists():
        raise ValueError(f"Card {card_number} is already taken")
    if FakeUserGameCard.objects.filter(game=game, card_number=card_number).exists():
        raise ValueError(f"Card {card_number} is already taken by fake user")
    
    # Generate card layout
    card_data = generate_bingo_card()
    
    # Create fake user card (no payment needed - fake users have unlimited balance)
    card = FakeUserGameCard.objects.create(
        game=game,
        fake_user=fake_user,
        card_number=card_number,
        card_layout=card_data['layout'],
        selected_numbers=[]
    )
    
    # Don't add to derash here - let recalculate_derash handle it
    # This ensures consistent calculation including percentage_cut
    # Invalidate cache
    from django.core.cache import cache
    if cache:
        cache.delete('game:current')
    
    # Invalidate cache
    from django.core.cache import cache
    if cache:
        cache.delete('game:current')
    
    return card


def get_available_card_numbers_for_fake(game: Game) -> List[int]:
    """Get available card numbers for fake users (excluding real user cards)
    Prefers cards from 1-100 range for more realistic selection"""
    from .models import GameSettings
    settings = GameSettings.get_settings()
    total_cards = settings.total_cards
    
    # Get all taken card numbers (real and fake)
    real_taken = set(GameCard.objects.filter(game=game).values_list('card_number', flat=True))
    fake_taken = set(FakeUserGameCard.objects.filter(game=game).values_list('card_number', flat=True))
    all_taken = real_taken | fake_taken
    
    # Prefer cards from 1-100 range (more realistic)
    preferred_range = list(range(1, min(101, total_cards + 1)))
    other_range = list(range(101, total_cards + 1)) if total_cards > 100 else []
    
    # Get available cards in preferred range first
    preferred_available = [num for num in preferred_range if num not in all_taken]
    other_available = [num for num in other_range if num not in all_taken]
    
    # Return preferred range first, then others (70% chance to pick from preferred)
    # But if preferred is empty, return others
    if preferred_available:
        return preferred_available + other_available
    else:
        return other_available


def select_fake_user_cards(game: Game, fake_users: List[FakeUser], delay_range: tuple = (0.5, 2.0)):
    """
    Select cards for fake users with random delays to simulate real behavior
    delay_range: (min_seconds, max_seconds) between each selection
    """
    available_cards = get_available_card_numbers_for_fake(game)
    
    if not available_cards:
        return []  # No cards available
    
    selected_cards = []
    for i, fake_user in enumerate(fake_users):
        if not available_cards:
            break  # No more cards available
        
        # Randomly select a card number
        card_number = random.choice(available_cards)
        available_cards.remove(card_number)
        
        try:
            card = create_fake_user_card(game, fake_user, card_number)
            selected_cards.append(card)
        except ValueError as e:
            # Card might have been taken by real user, try another
            if available_cards:
                card_number = random.choice(available_cards)
                available_cards.remove(card_number)
                try:
                    card = create_fake_user_card(game, fake_user, card_number)
                    selected_cards.append(card)
                except:
                    pass  # Skip this fake user if no cards available
    
    return selected_cards


def reduce_fake_users_for_real_joins(game: Game, real_user_count: int):
    """
    Reduce fake user cards when real users join
    For every n real users, remove n fake user cards
    """
    fake_cards = list(FakeUserGameCard.objects.filter(game=game).order_by('created_at'))
    
    if len(fake_cards) <= real_user_count:
        # Remove all fake cards if real users >= fake cards
        for card in fake_cards:
            card.delete()
    else:
        # Remove only the count of real users
        cards_to_remove = fake_cards[:real_user_count]
        for card in cards_to_remove:
            card.delete()
    
    # Recalculate derash to ensure correct calculation (includes percentage_cut)
    # Don't manually adjust derash_amount - let recalculate_derash handle it
    game.recalculate_derash()
    
    # Invalidate cache
    from django.core.cache import cache
    if cache:
        cache.delete('game:current')


def get_fake_user_count_for_game(game: Game) -> int:
    """Get count of fake users in a game"""
    return FakeUserGameCard.objects.filter(game=game).count()


def get_total_player_count(game: Game) -> int:
    """Get total player count including both real and fake users"""
    real_count = GameCard.objects.filter(game=game).count()
    fake_count = FakeUserGameCard.objects.filter(game=game).count()
    return real_count + fake_count


def check_fake_user_bingo(card: FakeUserGameCard, called_numbers: set, game=None) -> tuple:
    """
    Check if a fake user card has a winning BINGO pattern
    Returns (has_bingo, pattern_type)
    Only checks patterns enabled in game settings.
    """
    if len(card.selected_numbers) < 5:
        return (False, None)
    
    layout = card.card_layout
    if not layout:
        return (False, None)
    
    # Get enabled winning patterns from settings
    from .models import GameSettings
    settings = GameSettings.get_settings(game_id=game.id if game else None)
    enabled_patterns = getattr(settings, 'winning_patterns', [])
    
    # If no patterns specified, default to all patterns (backward compatibility)
    if not enabled_patterns:
        enabled_patterns = ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']
    
    # Convert to set for faster lookup
    enabled_patterns_set = set(enabled_patterns)
    
    # Helper function to check if a cell is marked (including FREE space)
    def is_cell_marked(cell):
        if cell.get('letter') == 'FREE':
            return True
        number = cell.get('number')
        if number is None:
            return False
        return number in called_numbers
    
    # IMPORTANT: If only 'full_card' is enabled, skip all other pattern checks
    # This ensures full_card only wins when ALL cells are marked, not when other patterns are complete
    only_full_card = enabled_patterns_set == {'full_card'}
    
    # Check horizontal lines - skip if only full_card is enabled
    if not only_full_card and 'horizontal' in enabled_patterns_set:
        for row_idx, row in enumerate(layout):
            if all(is_cell_marked(cell) for cell in row):
                return (True, f'row_{row_idx}')
    
    # Check vertical lines - skip if only full_card is enabled
    if not only_full_card and 'vertical' in enabled_patterns_set:
        for col_idx in range(5):
            if all(is_cell_marked(layout[row_idx][col_idx]) for row_idx in range(5)):
                return (True, f'col_{col_idx}')
    
    # Check diagonal (top-left to bottom-right) - skip if only full_card is enabled
    if not only_full_card and 'diagonal' in enabled_patterns_set:
        if all(is_cell_marked(layout[i][i]) for i in range(5)):
            return (True, 'diagonal_1')
        
        # Check diagonal (top-right to bottom-left)
        if all(is_cell_marked(layout[i][4-i]) for i in range(5)):
            return (True, 'diagonal_2')
    
    # Check corner bingo (4 corners + FREE cell) - skip if only full_card is enabled
    if not only_full_card and 'corner' in enabled_patterns_set:
        corners = [
            layout[0][0],  # Top-left
            layout[0][4],  # Top-right
            layout[4][0],  # Bottom-left
            layout[4][4],  # Bottom-right
            layout[2][2]   # FREE cell (center) - included for visual appeal
        ]
        if all(is_cell_marked(cell) for cell in corners):
            return (True, 'corner')
    
    # Check full card - ONLY wins if ALL cells are marked
    if 'full_card' in enabled_patterns_set:
        if all(is_cell_marked(cell) for row in layout for cell in row):
            return (True, 'full_card')
    
    return (False, None)


def mark_number_on_fake_card(card: FakeUserGameCard, number: int):
    """Mark a number on a fake user's card when it's called"""
    layout = card.card_layout
    number_found = False
    
    # Find and mark the number in the layout
    for row in layout:
        for cell in row:
            if cell.get('number') == number:
                # Mark the cell as marked (for display purposes)
                cell['marked'] = True
                number_found = True
                break
        if number_found:
            break
    
    if number_found:
        if number not in card.selected_numbers:
            card.selected_numbers.append(number)
        # Update the layout with marked cells
        card.card_layout = layout
        card.save(update_fields=['card_layout', 'selected_numbers'])
        return True
    
    return False


def get_fake_user_winning_numbers(card: FakeUserGameCard, called_numbers: set) -> List[int]:
    """
    Get the numbers that would make this fake user card win
    Returns list of numbers that, if called, would complete a bingo pattern
    """
    layout = card.card_layout
    if not layout:
        return []
    
    winning_numbers = []
    
    # Helper to check if cell is marked
    def is_cell_marked(cell):
        if cell.get('letter') == 'FREE':
            return True
        number = cell.get('number')
        if number is None:
            return False
        return number in called_numbers
    
    # Check each pattern and find missing numbers
    # Horizontal lines
    for row in layout:
        missing = [cell.get('number') for cell in row if not is_cell_marked(cell) and cell.get('number') is not None]
        if len(missing) == 1:
            winning_numbers.append(missing[0])
    
    # Vertical lines
    for col_idx in range(5):
        missing = [layout[row_idx][col_idx].get('number') for row_idx in range(5) 
                   if not is_cell_marked(layout[row_idx][col_idx]) and layout[row_idx][col_idx].get('number') is not None]
        if len(missing) == 1:
            winning_numbers.append(missing[0])
    
    # Diagonal 1
    missing = [layout[i][i].get('number') for i in range(5) 
               if not is_cell_marked(layout[i][i]) and layout[i][i].get('number') is not None]
    if len(missing) == 1:
        winning_numbers.append(missing[0])
    
    # Diagonal 2
    missing = [layout[i][4-i].get('number') for i in range(5) 
               if not is_cell_marked(layout[i][4-i]) and layout[i][4-i].get('number') is not None]
    if len(missing) == 1:
        winning_numbers.append(missing[0])
    
    return list(set(winning_numbers))  # Remove duplicates


def adjust_fake_users_for_real_player_change(game: Game, is_selection: bool):
    """
    Adjust fake users in real-time when a real player selects or unselects a card
    - When real player SELECTS card: Remove one fake user
    - When real player UNSELECTS card: Add one fake user back
    
    This ensures the total player count stays consistent
    """
    from .models import FakeUserGameCard, GameCard
    from .game_logic import get_available_card_numbers
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    
    # Only adjust if game is waiting and system accounts are enabled
    if game.status != 'waiting':
        return {'skipped': True, 'reason': 'Game is not in waiting status'}
    
    from .models import GameSettings
    settings = GameSettings.get_settings()
    if not settings.allow_system_account:
        return {'skipped': True, 'reason': 'System accounts not enabled'}
    
    # Count real players (only those who have selected cards)
    real_player_count = GameCard.objects.filter(game=game).count()
    
    # Count current fake users
    fake_user_count = get_fake_user_count_for_game(game)
    
    # Get minimum system accounts from settings
    min_system_accounts = getattr(settings, 'system_accounts_min', 15)
    
    if is_selection:
        # Real player selected a card - remove one fake user
        # BUT only if we won't drop below the minimum
        if fake_user_count > min_system_accounts:
            # Get a random fake user card to remove
            fake_cards = list(FakeUserGameCard.objects.filter(game=game))
            if fake_cards:
                import random
                card_to_remove = random.choice(fake_cards)
                fake_user_name = card_to_remove.fake_user.name
                card_to_remove.delete()
                
                # Broadcast card unselection for removed fake user
                try:
                    channel_layer = get_channel_layer()
                    available_cards = get_available_card_numbers(game)
                    async_to_sync(channel_layer.group_send)(
                        f'game_{game.id}',
                        {
                            'type': 'card_selected',
                            'data': {
                                'card_number': None,  # None means unselected
                                'user_id': None,
                                'username': fake_user_name,
                                'is_fake': True,
                                'available_cards': available_cards
                            }
                        }
                    )
                except Exception as e:
                    print(f"Error broadcasting fake user removal: {e}")
                
                # Invalidate cache
                from django.core.cache import cache
                if cache:
                    cache.delete('game:current')
                    cache.delete(f'game:{game.id}')
                
                print(f"Real player selected card - removed fake user {fake_user_name} (real: {real_player_count}, fake: {fake_user_count - 1})")
                return {
                    'success': True,
                    'action': 'removed',
                    'fake_user_name': fake_user_name,
                    'real_players': real_player_count,
                    'remaining_fake': fake_user_count - 1
                }
        else:
            # Cannot remove fake user - would drop below minimum
            print(f"Cannot remove fake user - would drop below minimum of {min_system_accounts} (current: {fake_user_count})")
            return {
                'success': False,
                'action': 'skipped',
                'reason': f'Would drop below minimum of {min_system_accounts}',
                'real_players': real_player_count,
                'current_fake': fake_user_count,
                'min_required': min_system_accounts
            }
    else:
        # Real player unselected a card - add one fake user back
        # Check if we can add a fake user (don't exceed original count)
        from .auto_game_manager import add_fake_users_to_game_immediately
        from .models import FakeUser
        
        # Get available fake users (those not currently in the game)
        active_fake_users = list(FakeUser.objects.filter(is_active=True))
        current_fake_user_ids = set(FakeUserGameCard.objects.filter(game=game).values_list('fake_user_id', flat=True))
        available_fake_users = [fu for fu in active_fake_users if fu.id not in current_fake_user_ids]
        
        if available_fake_users:
            import random
            fake_user_to_add = random.choice(available_fake_users)
            
            # Get available card numbers for fake users
            available_cards = get_available_card_numbers_for_fake(game)
            if available_cards:
                try:
                    card_number = random.choice(available_cards)
                    fake_card = create_fake_user_card(game, fake_user_to_add, card_number)
                    
                    # Broadcast card selection for added fake user
                    try:
                        channel_layer = get_channel_layer()
                        available_cards_updated = get_available_card_numbers(game)
                        async_to_sync(channel_layer.group_send)(
                            f'game_{game.id}',
                            {
                                'type': 'card_selected',
                                'data': {
                                    'card_number': card_number,
                                    'user_id': None,
                                    'username': fake_user_to_add.name,
                                    'is_fake': True,
                                    'available_cards': available_cards_updated
                                }
                            }
                        )
                    except Exception as e:
                        print(f"Error broadcasting fake user addition: {e}")
                    
                    # Invalidate cache
                    from django.core.cache import cache
                    if cache:
                        cache.delete('game:current')
                        cache.delete(f'game:{game.id}')
                    
                    print(f"Real player unselected card - added fake user {fake_user_to_add.name} (real: {real_player_count}, fake: {fake_user_count + 1})")
                    return {
                        'success': True,
                        'action': 'added',
                        'fake_user_name': fake_user_to_add.name,
                        'card_number': card_number,
                        'real_players': real_player_count,
                        'remaining_fake': fake_user_count + 1
                    }
                except Exception as e:
                    print(f"Error adding fake user back: {e}")
                    return {'error': str(e)}
        
        return {'skipped': True, 'reason': 'No available fake users or cards to add'}
    
    return {'skipped': True, 'reason': 'No adjustment needed'}


def get_real_user_winning_numbers(game: Game, called_numbers: set) -> List[int]:
    """
    Get numbers that would make real users win (one number away from bingo)
    Returns list of numbers that should NOT be called if we want fake users to win
    """
    from .game_logic import check_bingo
    from .models import GameCard
    
    blocking_numbers = []
    real_cards = GameCard.objects.filter(game=game, is_winner=False)
    
    for card in real_cards:
        # Get numbers on card that haven't been called
        layout = card.card_layout
        if not layout:
            continue
        
        # Check each pattern
        # Horizontal
        for row in layout:
            missing = [cell.get('number') for cell in row 
                      if not cell.get('marked', False) and cell.get('number') is not None and cell.get('letter') != 'FREE']
            if len(missing) == 1:
                blocking_numbers.append(missing[0])
        
        # Vertical
        for col_idx in range(5):
            missing = [layout[row_idx][col_idx].get('number') for row_idx in range(5)
                      if not layout[row_idx][col_idx].get('marked', False) and layout[row_idx][col_idx].get('number') is not None and layout[row_idx][col_idx].get('letter') != 'FREE']
            if len(missing) == 1:
                blocking_numbers.append(missing[0])
        
        # Diagonals
        missing = [layout[i][i].get('number') for i in range(5)
                  if not layout[i][i].get('marked', False) and layout[i][i].get('number') is not None and layout[i][i].get('letter') != 'FREE']
        if len(missing) == 1:
            blocking_numbers.append(missing[0])
        
        missing = [layout[i][4-i].get('number') for i in range(5)
                  if not layout[i][4-i].get('marked', False) and layout[i][4-i].get('number') is not None and layout[i][4-i].get('letter') != 'FREE']
        if len(missing) == 1:
            blocking_numbers.append(missing[0])
    
    return list(set(blocking_numbers))


def get_safe_number_to_call(game: Game, called_numbers: set, free_play: bool) -> Optional[int]:
    """
    Get a number that can be called safely
    If free_play is False, ensure the number won't let real users win
    Returns a number between 1-75 that hasn't been called yet
    """
    from .models import GameSettings
    
    all_numbers = set(range(1, 76))
    available = all_numbers - called_numbers
    
    if not available:
        return None
    
    if free_play:
        # Free play: any number is fine
        return random.choice(list(available))
    
    # Not free play: must ensure fake users can win
    # Get numbers that would make real users win (block these)
    blocking_numbers = get_real_user_winning_numbers(game, called_numbers)
    safe_numbers = available - set(blocking_numbers)
    
    if safe_numbers:
        # Prefer numbers that would make fake users win
        fake_cards = FakeUserGameCard.objects.filter(game=game, is_winner=False)
        fake_winning_numbers = []
        for card in fake_cards:
            fake_winning_numbers.extend(get_fake_user_winning_numbers(card, called_numbers))
        
        # Prioritize numbers that help fake users win
        preferred = set(fake_winning_numbers) & safe_numbers
        if preferred:
            return random.choice(list(preferred))
        
        # Otherwise, return any safe number
        return random.choice(list(safe_numbers))
    else:
        # All numbers would let real users win - call a random one anyway
        # (This shouldn't happen in normal gameplay)
        return random.choice(list(available))

