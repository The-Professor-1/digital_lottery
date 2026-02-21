import random
from typing import List, Dict, Tuple, Optional
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import Game, GameCard, CalledNumber, User, Transaction
from .redis_utils import (
    try_acquire_bingo_window, add_bingo_winner,
    get_bingo_winners, cleanup_game_redis_keys,
    acquire_bingo_claim_lock, release_bingo_claim_lock
)


def generate_bingo_card() -> Dict:
    """
    Generate a unique 5x5 Bingo card following standard Bingo rules:
    - B column: 1-15 (randomly shuffled)
    - I column: 16-30 (randomly shuffled)
    - N column: 31-45 (randomly shuffled, center is FREE)
    - G column: 46-60 (randomly shuffled)
    - O column: 61-75 (randomly shuffled)
    
    Numbers are randomly arranged within each column (traditional bingo style).
    """
    # Sample numbers for each column and shuffle them (don't sort - keep random order)
    card = {
        'B': random.sample(range(1, 16), 5),  # 5 random numbers from 1-15, shuffled
        'I': random.sample(range(16, 31), 5),  # 5 random numbers from 16-30, shuffled
        'N': random.sample(range(31, 46), 4),  # 4 random numbers from 31-45, shuffled (center is FREE)
        'G': random.sample(range(46, 61), 5),  # 5 random numbers from 46-60, shuffled
        'O': random.sample(range(61, 76), 5),  # 5 random numbers from 61-75, shuffled
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
    
    # PHASE 3 OPTIMIZATION: Initialize Redis tracking for faster bingo checking
    from .redis_utils import initialize_card_redis
    initialize_card_redis(card.id, selected_numbers=[])
    
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
    
    # PHASE 2 OPTIMIZATION: Add to Redis cache for faster access
    from .redis_utils import add_called_number_to_redis
    add_called_number_to_redis(game.id, number)
    
    # PHASE 4 OPTIMIZATION: Sync game state to Redis (status, call_count)
    from .redis_utils import sync_game_state_to_redis
    sync_game_state_to_redis(game)
    
    # Invalidate Django cache (for backward compatibility)
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
        
        # PHASE 3 OPTIMIZATION: Update Redis tracking for faster bingo checking
        from .redis_utils import mark_number_on_card_redis
        mark_number_on_card_redis(card.id, number)
        
        # Invalidate card cache when card is updated
        cache.delete(f'card:{card.game.id}:{card.user.id}')
        
        return True
    
    return False


def check_bingo(card: GameCard, game: Game) -> Tuple[bool, str]:
    """Check if a card has a winning BINGO pattern. Returns (has_bingo, pattern_type)
    
    Optimized: Early exit for cards with < 5 marked numbers. No database queries needed.
    Pattern checking only uses card layout (already in memory).
    Only checks patterns enabled in game settings.
    """
    # Early exit optimization: if card has less than 5 numbers marked, it can't have bingo
    # Minimum bingo requires 5 numbers in a line (row, column, or diagonal)
    if len(card.selected_numbers) < 5:
        return (False, None)
    
    # Check if card has winning pattern (no DB query needed - uses card layout in memory)
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
            return True  # FREE is always considered marked
        return cell.get('marked', False)
    
    # IMPORTANT: If only 'full_card' is enabled, skip all other pattern checks
    # This ensures full_card only wins when ALL cells are marked, not when other patterns are complete
    only_full_card = enabled_patterns_set == {'full_card'}
    
    # Check horizontal lines (any row) - skip if only full_card is enabled
    if not only_full_card and 'horizontal' in enabled_patterns_set:
        for row_idx, row in enumerate(layout):
            if all(is_cell_marked(cell) for cell in row):
                return (True, f'row_{row_idx}')
    
    # Check vertical lines (any column) - skip if only full_card is enabled
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


def get_winning_number(card: GameCard, winning_pattern: str, called_numbers: list) -> Optional[int]:
    """
    Find the number that completed the bingo pattern.
    Returns the last number called that is part of the winning pattern.
    This is the number that actually made the bingo.
    """
    if not winning_pattern or not called_numbers:
        return None
    
    layout = card.card_layout
    if not layout:
        return None
    
    # Get all numbers in the winning pattern
    pattern_numbers = []
    
    if winning_pattern.startswith('row_'):
        row_idx = int(winning_pattern.split('_')[1])
        pattern_numbers = [cell.get('number') for cell in layout[row_idx] if cell.get('number') is not None]
    elif winning_pattern.startswith('col_'):
        col_idx = int(winning_pattern.split('_')[1])
        pattern_numbers = [layout[row_idx][col_idx].get('number') for row_idx in range(5) 
                          if layout[row_idx][col_idx].get('number') is not None]
    elif winning_pattern == 'diagonal_1':
        pattern_numbers = [layout[i][i].get('number') for i in range(5) 
                          if layout[i][i].get('number') is not None]
    elif winning_pattern == 'diagonal_2':
        pattern_numbers = [layout[i][4-i].get('number') for i in range(5) 
                          if layout[i][4-i].get('number') is not None]
    elif winning_pattern == 'corner':
        corners = [layout[0][0], layout[0][4], layout[4][0], layout[4][4], layout[2][2]]
        pattern_numbers = [cell.get('number') for cell in corners if cell.get('number') is not None]
    elif winning_pattern == 'full_card':
        pattern_numbers = [cell.get('number') for row in layout for cell in row 
                          if cell.get('number') is not None]
    
    # Find which number in the pattern was called last (most recent in called_numbers)
    # Reverse called_numbers to check from most recent to oldest
    for number in reversed(called_numbers):
        if number in pattern_numbers:
            return number
    
    # Fallback: return the last called number if pattern number not found
    return called_numbers[-1] if called_numbers else None


def claim_bingo(card: GameCard, game: Game) -> Tuple[bool, Optional[str]]:
    """
    Process a BINGO claim for REAL users.
    This is a wrapper that calls the unified claim function.
    
    Returns (success, winning_pattern)
    Raises ValueError on failure
    """
    # Call unified function for real users
    success, winning_pattern, error_message = claim_bingo_unified(card, game, is_fake_user=False)
    
    if not success:
        raise ValueError(error_message or "Bingo claim failed")
    
    return (True, winning_pattern)


def claim_bingo_unified(card, game: Game, is_fake_user: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    UNIFIED bingo claim function for BOTH real and fake users.
    
    This is the SINGLE AUTHORITY for bingo claims - no other code should end games.
    
    Args:
        card: Either GameCard (real user) or FakeUserGameCard (fake user)
        game: Game object
        is_fake_user: True if card is FakeUserGameCard, False if GameCard
    
    Returns:
        (success: bool, winning_pattern: str, error_message: str)
        - success: True if claim was successful
        - winning_pattern: Pattern that won (if successful)
        - error_message: Error message if claim failed
    
    This function:
    - Uses Redis lock to ensure atomic claims
    - Validates ONLY the claiming card (not others)
    - Implements free_play logic (real priority when free_play is OFF)
    - Ends game and broadcasts winner (single authority)
    """
    from .models import GameSettings, GameCard, FakeUserGameCard
    from .redis_utils import get_called_numbers_from_redis
    
    # CRITICAL: Acquire Redis lock for atomic bingo claim
    # This ensures only ONE claim is processed at a time across all machines
    if not acquire_bingo_claim_lock(game.id, timeout=5):
        return (False, None, "Another bingo claim is being processed. Please try again.")
    
    try:
        # CRITICAL: Always get fresh game from DB first (needed for tie-window check when completed)
        game = Game.objects.get(id=game.id)
        game.refresh_from_db()
        
        # Allow claims when game is completed ONLY if within tie window (3 sec max)
        allow_completed_tie = False
        if game.status == 'completed':
            if not game.completed_at:
                return (False, None, "Another player claimed bingo first")
            elapsed = timezone.now() - game.completed_at
            if elapsed > timedelta(seconds=3):
                return (False, None, "Another player claimed bingo first")
            allow_completed_tie = True
        elif game.status != 'active':
            return (False, None, f"Game is not active (status: {game.status})")
        
        # Refresh card to get latest state (including marked cells in layout)
        # Use select_related to load relationships to avoid extra queries later
        if is_fake_user:
            card = FakeUserGameCard.objects.select_related('fake_user').get(id=card.id)
        else:
            card = GameCard.objects.select_related('user').get(id=card.id)
        
        # Check if card already won
        if card.is_winner:
            return (False, None, "This card has already won")
        
        # CRITICAL: Ensure card layout is loaded (it should be, but double-check)
        if not card.card_layout:
            return (False, None, "Card layout is missing")
        
        # Get called numbers from Redis
        called_numbers = get_called_numbers_from_redis(game.id)
        if not called_numbers:
            return (False, None, "No numbers have been called yet")
        
        # Validate that all marked numbers on card were actually called
        if is_fake_user:
            # For fake users, check selected_numbers against called_numbers
            marked_numbers = set(card.selected_numbers or [])
            called_set = set(called_numbers)
            if not marked_numbers.issubset(called_set):
                return (False, None, "Some marked numbers were not called")
            
            # Check bingo using fake user bingo checker
            from .fake_user_manager import check_fake_user_bingo
            has_bingo, winning_pattern = check_fake_user_bingo(card, called_set, game)
        else:
            # For real users, validate card layout
            layout = card.card_layout
            if layout:
                for row in layout:
                    for cell in row:
                        if cell.get('marked', False) and cell.get('number') is not None:
                            if cell['number'] not in called_numbers:
                                return (False, None, f"Number {cell['number']} is marked but was not called")
            
            # Check bingo using real user bingo checker
            has_bingo, winning_pattern = check_bingo(card, game)
        
        if not has_bingo:
            return (False, None, "BINGO pattern not complete")
        
        # CRITICAL: Check free_play setting for priority logic
        # If free_play is OFF and this is a fake user, check if any real user has bingo
        # If free_play is ON, it's truly random - first to claim wins
        settings = GameSettings.get_settings(game_id=game.id)
        free_play = getattr(settings, 'free_play', False)
        
        if is_fake_user and not free_play:
            # free_play is OFF: Check if any real user has bingo (give them priority)
            real_cards = GameCard.objects.filter(game=game, is_winner=False).select_related('user')
            for real_card in real_cards:
                real_has_bingo, _ = check_bingo(real_card, game)
                if real_has_bingo:
                    # Real user has bingo - reject fake user claim
                    print(f"CRITICAL: Real user {real_card.user.id} has bingo! Rejecting fake user claim (free_play is OFF).")
                    return (False, None, "Real user has priority (free_play is OFF)")
        
        # Re-check game status only when NOT in tie-window path (co-winner path already knows game is completed)
        if not allow_completed_tie:
            game.refresh_from_db()
            if game.status != 'active':
                return (False, None, "Game was completed by another player")
        
        # Use Redis for winner window: 1 sec when first is real, 3 sec when first is fake
        success, is_first_winner = try_acquire_bingo_window(game.id, first_claim_is_fake=is_fake_user)
        if not success:
            return (False, None, "Another player claimed bingo first")
        
        # Mark card as winner
        claim_time = timezone.now()
        card.is_winner = True
        if is_fake_user:
            card.winning_pattern = winning_pattern
        else:
            card.claimed_at = claim_time
        card.save()
        
        # Add winner to Redis set
        user_id = None if is_fake_user else card.user.id
        add_bingo_winner(game.id, card.id, user_id)
        
        if is_first_winner:
            # Do NOT set game completed yet: keep game active for the tie window (3s fake / 1s real)
            # so real players can tick numbers and claim as co-winners. Completed + broadcast happen in delayed task.
            game.refresh_from_db()
            if not is_fake_user and card.user_id:
                game.winners.add(card.user)
            print(f"SUCCESS: Game {game.id} first claim by {'fake user' if is_fake_user else f'real user {card.user.id}'} (window open)")
            
            # Fixed one-time window: 3s if first is fake, 1s if first is real. We do NOT wait extra seconds
            # when more co-winners join; the same single countdown runs once, then we set completed and announce all.
            from .tasks import task_broadcast_winner_declared_delayed, task_process_bingo_winners
            window_sec = 3 if is_fake_user else 1
            task_broadcast_winner_declared_delayed.apply_async(args=[game.id], countdown=window_sec)
            print(f"Scheduled winner broadcast + game complete for game {game.id} in {window_sec}s (fixed window, no extra wait per co-winner)")
            task_process_bingo_winners.apply_async(args=[game.id], countdown=window_sec)
        else:
            # Co-winner within window: add to list only. Do NOT schedule any new task or extend the timer;
            # the single delayed task (scheduled on first claim) will run after the fixed window and announce all.
            game.refresh_from_db()
            if not is_fake_user and card.user_id:
                game.winners.add(card.user)
            print(f"Co-winner added for game {game.id}; broadcast will happen when delayed task runs")
        
        return (True, winning_pattern, None)
    
    finally:
        # Always release the lock
        release_bingo_claim_lock(game.id)


def start_game(game: Game) -> bool:
    """Start a game - requires at least 2 total players (real + fake)
    Also caches game settings to prevent mid-game changes
    """
    from django.core.cache import cache
    from .models import GameSettings
    
    # Refresh game from database to get latest status (prevents race conditions)
    game.refresh_from_db()
    
    if game.status != 'waiting':
        return False
    
    # No grace period needed - game starts immediately when timer ends
    # State transitions are handled atomically with locks
    
    # CRITICAL: Cache game settings at game start to prevent mid-game changes.
    # free_play: when True, number calling is random (no extra processing). When False,
    # task_auto_call_numbers uses get_safe_number_to_call so real users don't win (fake users can).
    settings = GameSettings.get_settings()
    game_settings_cache_key = f'game:{game.id}:settings'
    cache.set(game_settings_cache_key, {
        'time_between_calls': settings.time_between_calls,
        'allow_system_account': settings.allow_system_account,
        'free_play': settings.free_play,
        'bid_amount': float(settings.bid_amount),
        'percentage_cut': float(settings.percentage_cut),
        'card_selection_timer': settings.card_selection_timer,
        'total_cards': settings.total_cards,
        'system_accounts_min': getattr(settings, 'system_accounts_min', 15),
        'system_accounts_max': getattr(settings, 'system_accounts_max', 30),
        'winning_patterns': getattr(settings, 'winning_patterns', ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']),
    }, 3600)  # Cache for 1 hour (game won't last that long)
    
    # Check if system accounts are enabled (use cached settings)
    allow_system_account = settings.allow_system_account
    
    # Count real players
    real_player_count = game.gamecards.count()
    
    # Count fake players
    fake_player_count = 0
    if allow_system_account:
        try:
            from .fake_user_manager import get_fake_user_count_for_game
            fake_player_count = get_fake_user_count_for_game(game)
        except:
            fake_player_count = 0
    
    # Total players (real + fake)
    total_player_count = real_player_count + fake_player_count
    
    # CRITICAL: If system accounts are enabled, ensure we have at least the minimum
    # This is a final check right before game starts to catch any edge cases
    if allow_system_account:
        min_system_accounts = getattr(settings, 'system_accounts_min', 15)
        # If we have fewer fake users than minimum, add more immediately
        if fake_player_count < min_system_accounts:
            try:
                from .fake_user_manager import get_random_fake_users, get_available_card_numbers_for_fake, create_fake_user_card
                from .models import FakeUser, FakeUserGameCard
                import random
                
                fake_users_needed = min_system_accounts - fake_player_count
                print(f"Game {game.id}: Final check - only {fake_player_count} fake users before start, adding {fake_users_needed} more to reach minimum {min_system_accounts}")
                
                # Get fake users that don't already have cards
                existing_fake_user_ids = set(FakeUserGameCard.objects.filter(game=game).values_list('fake_user_id', flat=True))
                all_fake_users = list(FakeUser.objects.filter(is_active=True).exclude(id__in=existing_fake_user_ids))
                
                if len(all_fake_users) >= fake_users_needed:
                    fake_users_to_add = random.sample(all_fake_users, fake_users_needed)
                    available_cards = get_available_card_numbers_for_fake(game)
                    
                    # PHASE 5 OPTIMIZATION: Collect card selections for batching
                    batched_card_events = []
                    
                    if len(available_cards) >= fake_users_needed:
                        for fake_user in fake_users_to_add:
                            if available_cards:
                                # Prefer cards from 1-100 range (70% chance) for more realistic selection
                                preferred_cards = [c for c in available_cards if c <= 100]
                                other_cards = [c for c in available_cards if c > 100]
                                
                                if preferred_cards and random.random() < 0.7:
                                    card_number = random.choice(preferred_cards)
                                elif preferred_cards:
                                    card_number = random.choice(preferred_cards)
                                elif other_cards:
                                    card_number = random.choice(other_cards)
                                else:
                                    card_number = random.choice(available_cards)
                                
                                available_cards.remove(card_number)
                                try:
                                    create_fake_user_card(game, fake_user, card_number)
                                    fake_player_count += 1
                                    
                                    # Add to batch instead of broadcasting immediately
                                    batched_card_events.append({
                                        'type': 'card_selected',
                                        'data': {
                                            'card_number': card_number,
                                            'user_id': None,  # Fake user
                                            'username': fake_user.name,
                                            'is_fake': True,
                                            'available_cards': get_available_card_numbers(game)
                                        }
                                    })
                                    
                                    print(f"Added fake user {fake_user.name} with card {card_number} to game {game.id} (final check)")
                                except Exception as e:
                                    print(f"Error adding fake user {fake_user.name}: {e}")
                        
                        # Batch broadcast all card selections at once
                        if batched_card_events:
                            try:
                                from .redis_utils import batch_broadcast_to_game
                                batch_broadcast_to_game(game.id, batched_card_events)
                                print(f"  Batched {len(batched_card_events)} fake user card selections from final check")
                            except Exception as e:
                                print(f"WebSocket batch broadcast error for final check fake user cards: {e}")
            except Exception as e:
                print(f"Error in final fake user check for game {game.id}: {e}")
                import traceback
                traceback.print_exc()
    
    # Require at least 2 total players to start the game
    # BUT: If system accounts are enabled, allow starting with just fake players (even 0 real players)
    total_player_count = real_player_count + fake_player_count
    if allow_system_account:
        # If system accounts enabled, only need at least 1 fake player (can start with 0 real players)
        if fake_player_count < 1:
            return False
    else:
        # If system accounts disabled, need at least 2 real players
        if total_player_count < 2:
            return False
    
    # IMPORTANT: Recalculate derash BEFORE setting game to active
    # This ensures derash and player count are synchronized before countdown starts
    # Refresh game from DB to get latest fake user count before recalculating derash
    game.refresh_from_db()
    
    # Ensure all fake user cards are committed to DB before recalculating
    # Add a small delay to ensure all pending fake user card selections are complete
    import time
    time.sleep(0.5)  # Small delay to ensure all fake user selections are committed
    
    # Refresh again to get the latest count after delay
    game.refresh_from_db()
    
    # Recalculate derash to include fake users (MUST be done BEFORE setting status to active)
    # This ensures derash is correct when the game starts and countdown begins
    game.recalculate_derash()
    
    # Refresh again after derash calculation to ensure latest values are synced
    game.refresh_from_db()
    
    # FINAL CHECK: Ensure we have at least minimum fake users before starting
    # This is the absolute last check before game starts
    if allow_system_account:
        min_system_accounts = getattr(settings, 'system_accounts_min', 15)
        current_fake_count = get_fake_user_count_for_game(game)
        if current_fake_count < min_system_accounts:
            print(f"Game {game.id}: CRITICAL - Only {current_fake_count} fake users before start, need {min_system_accounts}. Adding more...")
            try:
                from .fake_user_manager import get_random_fake_users, get_available_card_numbers_for_fake, create_fake_user_card
                from .models import FakeUser, FakeUserGameCard
                import random
                
                fake_users_needed = min_system_accounts - current_fake_count
                existing_fake_user_ids = set(FakeUserGameCard.objects.filter(game=game).values_list('fake_user_id', flat=True))
                all_fake_users = list(FakeUser.objects.filter(is_active=True).exclude(id__in=existing_fake_user_ids))
                
                if len(all_fake_users) >= fake_users_needed:
                    fake_users_to_add = random.sample(all_fake_users, fake_users_needed)
                    available_cards = get_available_card_numbers_for_fake(game)
                    
                    # PHASE 5 OPTIMIZATION: Collect card selections for batching
                    batched_card_events = []
                    
                    if len(available_cards) >= fake_users_needed:
                        for fake_user in fake_users_to_add:
                            if available_cards:
                                # Prefer cards from 1-100 range (70% chance) for more realistic selection
                                preferred_cards = [c for c in available_cards if c <= 100]
                                other_cards = [c for c in available_cards if c > 100]
                                
                                if preferred_cards and random.random() < 0.7:
                                    card_number = random.choice(preferred_cards)
                                elif preferred_cards:
                                    card_number = random.choice(preferred_cards)
                                elif other_cards:
                                    card_number = random.choice(other_cards)
                                else:
                                    card_number = random.choice(available_cards)
                                
                                available_cards.remove(card_number)
                                try:
                                    create_fake_user_card(game, fake_user, card_number)
                                    
                                    # Add to batch instead of broadcasting immediately
                                    batched_card_events.append({
                                        'type': 'card_selected',
                                        'data': {
                                            'card_number': card_number,
                                            'user_id': None,  # Fake user
                                            'username': fake_user.name,
                                            'is_fake': True,
                                            'available_cards': get_available_card_numbers(game)
                                        }
                                    })
                                    
                                    print(f"CRITICAL: Added fake user {fake_user.name} with card {card_number} to game {game.id} (final pre-start check)")
                                except Exception as e:
                                    print(f"Error in final pre-start fake user addition: {e}")
                        
                        # Batch broadcast all card selections at once
                        if batched_card_events:
                            try:
                                from .redis_utils import batch_broadcast_to_game
                                batch_broadcast_to_game(game.id, batched_card_events)
                                print(f"  Batched {len(batched_card_events)} fake user card selections from final pre-start check")
                            except Exception as e:
                                print(f"WebSocket batch broadcast error for pre-start fake user cards: {e}")
                        
                        # Recalculate derash after adding fake users
                        game.refresh_from_db()
                        game.recalculate_derash()
            except Exception as e:
                print(f"Error in final pre-start fake user check: {e}")
                import traceback
                traceback.print_exc()
    
    # CRITICAL: Double-check game is still waiting before setting to active
    # This prevents race conditions where multiple requests try to start the game
    if game.status != 'waiting':
        # Game was already started by another process, return False
        return False
    
    # Now set game to active (after derash is calculated and synced)
    game.status = 'active'
    game.started_at = timezone.now()
    game.save()
    
    # PHASE 4 OPTIMIZATION: Sync game state to Redis immediately when game starts
    from .redis_utils import sync_game_state_to_redis
    sync_game_state_to_redis(game)
    
    # Final refresh to ensure all values are synced
    game.refresh_from_db()
    
    # Invalidate game cache when game starts
    cache.delete('game:current')
    
    return True


def get_available_card_numbers(game: Game) -> List[int]:
    """Get list of available card numbers for a game (excludes both real and fake user cards)"""
    from .models import GameSettings, FakeUserGameCard
    # Get total_cards from settings
    settings = GameSettings.get_settings()
    total_cards = settings.total_cards
    # Get taken numbers from both real and fake users
    real_taken = set(GameCard.objects.filter(game=game).values_list('card_number', flat=True))
    fake_taken = set(FakeUserGameCard.objects.filter(game=game).values_list('card_number', flat=True))
    taken_numbers = real_taken | fake_taken
    all_numbers = list(range(1, total_cards + 1))
    return [num for num in all_numbers if num not in taken_numbers]

