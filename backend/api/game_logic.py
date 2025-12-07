import random
from typing import List, Dict, Tuple, Optional
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import Game, GameCard, CalledNumber, User, Transaction
from .redis_utils import (
    try_acquire_bingo_window, add_bingo_winner,
    get_bingo_winners, cleanup_game_redis_keys
)


def generate_bingo_card() -> Dict:
    """
    Generate a unique 5x5 Bingo card following standard Bingo rules:
    - B column: 1-15
    - I column: 16-30
    - N column: 31-45 (center is FREE)
    - G column: 46-60
    - O column: 61-75
    """
    card = {
        'B': sorted(random.sample(range(1, 16), 5)),
        'I': sorted(random.sample(range(16, 31), 5)),
        'N': sorted(random.sample(range(31, 46), 4)),  # 4 numbers + FREE center
        'G': sorted(random.sample(range(46, 61), 5)),
        'O': sorted(random.sample(range(61, 76), 5)),
    }
    
    # Create 5x5 grid layout
    layout = []
    for row in range(5):
        layout_row = []
        for col_idx, letter in enumerate(['B', 'I', 'N', 'G', 'O']):
            if letter == 'N' and row == 2 and col_idx == 2:
                # Center is FREE
                layout_row.append({
                    'number': None,
                    'letter': 'FREE',
                    'marked': True,  # FREE is always marked
                    'row': row,
                    'col': col_idx
                })
            else:
                if letter == 'N':
                    # N column has 4 numbers, skip center
                    num_idx = row if row < 2 else row - 1
                    number = card[letter][num_idx]
                else:
                    number = card[letter][row]
                
                layout_row.append({
                    'number': number,
                    'letter': letter,
                    'marked': False,
                    'row': row,
                    'col': col_idx
                })
        layout.append(layout_row)
    
    return {
        'layout': layout,
        'numbers': card
    }


def create_game_card(game: Game, user: User, card_number: int) -> GameCard:
    """Create a new game card for a user in a game"""
    # Check if user already has a card for this game
    existing_card = GameCard.objects.filter(game=game, user=user).first()
    user_already_paid = existing_card is not None
    
    if existing_card:
        # If user tries to select a different card, allow it only if the new card is available
        if existing_card.card_number != card_number:
            # Check if the new card number is available
            if GameCard.objects.filter(game=game, card_number=card_number).exists():
                raise ValueError(f"Card {card_number} is already taken by another user")
            # Allow changing card - delete old one and create new
            # User already paid for this game, just change the card number without additional charge
            old_card_number = existing_card.card_number
            existing_card.delete()
            # Continue to create new card but skip payment (user already paid)
        else:
            # Same card, just return it (user already has this card, no charge)
            return existing_card
    
    # Check if card number is already taken
    if GameCard.objects.filter(game=game, card_number=card_number).exists():
        raise ValueError(f"Card {card_number} is already taken for this game")
    
    # Generate card layout
    card_data = generate_bingo_card()
    
    # Only deduct payment if user hasn't paid yet (first time selecting a card for this game)
    if not user_already_paid:
        # Ensure this is a real authenticated user (has telegram_id) - no anonymous users allowed
        if not user.telegram_id:
            raise ValueError("Only authenticated users can purchase cards. Please login through Telegram.")
        
        # Refresh user from database to get latest balance
        user.refresh_from_db()
        
        # Deduct bet amount from user balance
        from decimal import Decimal
        bet_amount = Decimal(str(game.bet_amount))
        
        # Check if user has sufficient balance (using fresh data from DB)
        current_balance = Decimal(str(user.balance))
        if current_balance < bet_amount:
            raise ValueError(f"በቂ ሂሳብ የሎትም።\nያለዎት ሂሳብ: {current_balance} ብር\nየሚያስፈልገው: {bet_amount} ብር\n\nእባክዎ ገንዘብ ያስገቡ።")
        
        # Deduct bet amount from user balance
        user.balance = Decimal(str(user.balance)) - bet_amount
        user.save()
        
        # Add to game derash (this is the total collected, not per player)
        # Note: derash_amount stores the total collected amount
        # Only add derash for real authenticated users (already verified above)
        from django.core.cache import cache
        
        game.derash_amount = Decimal(str(game.derash_amount)) + bet_amount
        game.save()
        
        # Invalidate game cache when derash changes
        from django.core.cache import cache as django_cache
        if django_cache:
            django_cache.delete('game:current')
        
        # Create transaction
        Transaction.objects.create(
            user=user,
            transaction_type='bet',
            amount=game.bet_amount,
            game=game,
            description=f'Purchased card {card_number} for game {game.id}'
        )
    
    # Create game card
    card = GameCard.objects.create(
        game=game,
        user=user,
        card_number=card_number,
        card_layout=card_data['layout'],
        selected_numbers=[]
    )
    
    # Invalidate card cache for this user and game cache (player count changed)
    from django.core.cache import cache as django_cache
    if django_cache:
        django_cache.delete(f'card:{game.id}:{user.id}')
        django_cache.delete('game:current')  # Game player count/derash changed
    
    return card


def call_number(game: Game, number: int) -> CalledNumber:
    """Call a number in a game"""
    from django.core.cache import cache
    
    # Validate number range
    if not (1 <= number <= 75):
        raise ValueError("Number must be between 1 and 75")
    
    # Check if number already called
    if CalledNumber.objects.filter(game=game, number=number).exists():
        raise ValueError(f"Number {number} has already been called")
    
    # Get letter for number
    letter = CalledNumber.get_letter_for_number(number)
    if not letter:
        raise ValueError(f"Invalid number: {number}")
    
    # Create called number
    called_number = CalledNumber.objects.create(
        game=game,
        number=number,
        letter=letter
    )
    
    # Update game call count
    game.current_call_count += 1
    game.save()
    
    # Invalidate caches when a new number is called
    cache.delete(f'called_numbers:{game.id}')
    cache.delete('game:current')
    
    return called_number


def mark_number_on_card(card: GameCard, number: int) -> bool:
    """Mark a number on a user's card when it's called"""
    from django.core.cache import cache
    
    # Check if number is on the card
    layout = card.card_layout
    number_found = False
    
    for row in layout:
        for cell in row:
            if cell.get('number') == number:
                cell['marked'] = True
                number_found = True
                break
        if number_found:
            break
    
    if number_found:
        card.mark_number(number)
        card.card_layout = layout
        card.save(update_fields=['card_layout', 'selected_numbers'])
        
        # Invalidate card cache when card is updated
        cache.delete(f'card:{card.game.id}:{card.user.id}')
        
        return True
    
    return False


def check_bingo(card: GameCard, game: Game) -> Tuple[bool, str]:
    """Check if a card has a winning BINGO pattern. Returns (has_bingo, pattern_type)
    
    Optimized: Early exit for cards with < 5 marked numbers. No database queries needed.
    Pattern checking only uses card layout (already in memory).
    """
    # Early exit optimization: if card has less than 5 numbers marked, it can't have bingo
    # Minimum bingo requires 5 numbers in a line (row, column, or diagonal)
    if len(card.selected_numbers) < 5:
        return (False, None)
    
    # Check if card has winning pattern (no DB query needed - uses card layout in memory)
    layout = card.card_layout
    if not layout:
        return (False, None)
    
    # Helper function to check if a cell is marked (including FREE space)
    def is_cell_marked(cell):
        if cell.get('letter') == 'FREE':
            return True  # FREE is always considered marked
        return cell.get('marked', False)
    
    # Check horizontal lines (any row)
    for row_idx, row in enumerate(layout):
        if all(is_cell_marked(cell) for cell in row):
            return (True, f'row_{row_idx}')
    
    # Check vertical lines (any column)
    for col_idx in range(5):
        if all(is_cell_marked(layout[row_idx][col_idx]) for row_idx in range(5)):
            return (True, f'col_{col_idx}')
    
    # Check diagonal (top-left to bottom-right)
    if all(is_cell_marked(layout[i][i]) for i in range(5)):
        return (True, 'diagonal_1')
    
    # Check diagonal (top-right to bottom-left)
    if all(is_cell_marked(layout[i][4-i]) for i in range(5)):
        return (True, 'diagonal_2')
    
    # Check full card
    if all(is_cell_marked(cell) for row in layout for cell in row):
        return (True, 'full_card')
    
    return (False, None)


def claim_bingo(card: GameCard, game: Game) -> Tuple[bool, Optional[str]]:
    """Process a BINGO claim. Returns (success, winning_pattern)
    
    Uses Redis for 1-second winner window to handle multiple winners properly.
    """
    # Check if card already won
    if card.is_winner:
        raise ValueError('This card has already won')
    
    # Check if game is active - Redis will handle the window timing
    if game.status != 'active':
        # Allow completed games only if within Redis window
        from .redis_utils import get_bingo_window_key, get_redis_client
        r = get_redis_client()
        if r:
            window_key = get_bingo_window_key(game.id)
            if r.exists(window_key):
                # Window still open, allow claim
                pass
            elif game.status == 'completed':
                raise ValueError('በሌላ ተጫዋች ተቀድመዋል!')
        elif game.status == 'completed':
            raise ValueError('በሌላ ተጫዋች ተቀድመዋል!')
        else:
            raise ValueError('Game is not active')
    
    # Verify all marked numbers on card were actually called
    from django.core.cache import cache as django_cache
    
    # Try to get called numbers from cache first
    called_numbers = None
    if django_cache:
        cache_key = f'called_numbers:{game.id}'
        called_numbers = django_cache.get(cache_key)
    
    if called_numbers is None:
        # Cache miss - fetch from database
        called_numbers = list(CalledNumber.objects.filter(game=game).values_list('number', flat=True))
        # Cache for 10 seconds
        if django_cache:
            cache_key = f'called_numbers:{game.id}'
            django_cache.set(cache_key, called_numbers, 10)
    
    called_numbers = set(called_numbers)
    layout = card.card_layout
    
    if layout:
        for row in layout:
            for cell in row:
                if cell.get('marked', False) and cell.get('number') is not None:
                    if cell['number'] not in called_numbers:
                        raise ValueError(f"Number {cell['number']} is marked but was not called")
    
    # Check if card has BINGO pattern
    has_bingo, winning_pattern = check_bingo(card, game)
    if not has_bingo:
        raise ValueError('BINGO pattern not complete. Make sure you have a complete line marked.')
    
    # Use Redis for 1-second winner window (race-condition safe)
    success, is_first_winner = try_acquire_bingo_window(game.id)
    if not success:
        raise ValueError('በሌላ ተጫዋች ተቀድመዋል!')
    
    # Mark card as winner and record claim time
    claim_time = timezone.now()
    card.is_winner = True
    card.claimed_at = claim_time
    card.save()
    
    # Add this winner to Redis set
    add_bingo_winner(game.id, card.id, card.user.id)
    
    # Get all current winners from Redis (for synchronous processing)
    redis_winners = get_bingo_winners(game.id)
    
    # Get winner cards from database
    winner_card_ids = [w['card_id'] for w in redis_winners]
    all_winner_cards = list(GameCard.objects.filter(
        id__in=winner_card_ids,
        game=game,
        is_winner=True
    ).select_related('user'))
    
    # If this is the first winner, mark game as completed
    if is_first_winner and game.status == 'active':
        from django.core.cache import cache as django_cache
        
        game.status = 'completed'
        game.completed_at = claim_time
        game.winner = card.user  # Set primary winner
        game.save()
        
        # Invalidate game cache when game completes
        if django_cache:
            django_cache.delete('game:current')
        
        # Trigger async task to finalize all winners after 1 second window
        # This ensures all winners within the 1-second window are properly processed
        from .tasks import task_process_bingo_winners
        task_process_bingo_winners.apply_async(
            args=[game.id],
            countdown=1  # Wait 1 second for all winners to claim
        )
    elif game.status != 'completed':
        # Not first winner but game should be completed by now
        game.refresh_from_db()
    
    # Add all winners to ManyToMany field
    for winner_card in all_winner_cards:
        game.winners.add(winner_card.user)
    
    # Prize distribution happens in async task after 1-second window
    # This ensures all winners within the window are included in prize split
    return (True, winning_pattern)


def start_game(game: Game) -> bool:
    """Start a game - requires at least 2 players"""
    from django.core.cache import cache
    
    if game.status != 'waiting':
        return False
    
    # Require at least 2 players to start the game
    player_count = game.gamecards.count()
    if player_count < 2:
        return False
    
    game.status = 'active'
    game.started_at = timezone.now()
    game.save()
    
    # Invalidate game cache when game starts
    cache.delete('game:current')
    
    return True


def get_available_card_numbers(game: Game) -> List[int]:
    """Get list of available card numbers for a game"""
    from .models import GameSettings
    # Get total_cards from settings
    settings = GameSettings.get_settings()
    total_cards = settings.total_cards
    taken_numbers = set(GameCard.objects.filter(game=game).values_list('card_number', flat=True))
    all_numbers = list(range(1, total_cards + 1))
    return [num for num in all_numbers if num not in taken_numbers]

