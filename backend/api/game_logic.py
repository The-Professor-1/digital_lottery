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
        
        # Check if user has sufficient balance (unwithdrawable + withdrawable)
        current_balance = Decimal(str(user.balance))
        if current_balance < bet_amount:
            raise ValueError(f"በቂ ሂሳብ የሎትም።\nያለዎት ሂሳብ: {current_balance} ብር\nየሚያስፈልገው: {bet_amount} ብር\n\nእባክዎ ገንዘብ ያስገቡ።")
        
        # Deduct from unwithdrawable_balance first, then withdrawable_balance
        user.deduct_bid(bet_amount)
        
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
        # Keep legacy key + live game-scoped key in sync so Celery and claims agree.
        from .redis_utils import mark_number_on_card_redis, mark_number_on_card_live
        mark_number_on_card_redis(card.id, number)
        mark_number_on_card_live(card.game_id, card.id, number)
        
        # Invalidate card cache when card is updated
        cache.delete(f'card:{card.game.id}:{card.user.id}')
        
        return True
    
    return False


def check_bingo_from_marked(layout, marked_numbers: set, game_id: int = None) -> Tuple[bool, Optional[str]]:
    """
    Check if a card has bingo using a set of marked cell numbers (ints).
    Same algorithm as Celery task_check_bingo_for_number — single source of truth.
    FREE space is always treated as marked.
    """
    # Minimum real-number marks can be 4 because FREE participates in center row/col,
    # both diagonals, and corner pattern.
    if not layout or not marked_numbers or len(marked_numbers) < 4:
        return (False, None)

    from .models import GameSettings
    settings = GameSettings.get_settings(game_id=game_id)
    enabled_patterns = getattr(settings, "winning_patterns", [])
    if not enabled_patterns:
        enabled_patterns = ["horizontal", "vertical", "diagonal", "corner", "full_card"]
    enabled_patterns_set = set(enabled_patterns)

    def is_marked(cell):
        if cell.get("letter") == "FREE":
            return True
        cell_number = cell.get("number")
        if cell_number is None:
            return False
        try:
            return int(cell_number) in marked_numbers
        except (ValueError, TypeError):
            return False

    only_full_card = enabled_patterns_set == {"full_card"}

    if not only_full_card and "horizontal" in enabled_patterns_set:
        for row_idx, row in enumerate(layout):
            if all(is_marked(cell) for cell in row):
                return (True, f"row_{row_idx}")

    if not only_full_card and "vertical" in enabled_patterns_set:
        for col_idx in range(5):
            if all(is_marked(layout[row_idx][col_idx]) for row_idx in range(5)):
                return (True, f"col_{col_idx}")

    if not only_full_card and "diagonal" in enabled_patterns_set:
        if all(is_marked(layout[i][i]) for i in range(5)):
            return (True, "diagonal_1")
        if all(is_marked(layout[i][4 - i]) for i in range(5)):
            return (True, "diagonal_2")

    if not only_full_card and "corner" in enabled_patterns_set:
        corners = [layout[0][0], layout[0][4], layout[4][0], layout[4][4], layout[2][2]]
        if all(is_marked(cell) for cell in corners):
            return (True, "corner")

    if "full_card" in enabled_patterns_set:
        if all(is_marked(cell) for row in layout for cell in row):
            return (True, "full_card")

    return (False, None)


def check_bingo(card: GameCard, game: Game) -> Tuple[bool, Optional[str]]:
    """Check if a card has a winning BINGO using effective marks (Redis + DB), not layout flags alone."""
    from .redis_utils import get_effective_marked_numbers_for_card

    if not game:
        return (False, None)
    layout = card.card_layout
    if not layout:
        return (False, None)

    marked_numbers = get_effective_marked_numbers_for_card(
        game.id, card.id, card.card_layout, card.selected_numbers
    )
    # Keep consistent with check_bingo_from_marked (FREE can reduce required marks to 4).
    if len(marked_numbers) < 4:
        return (False, None)

    return check_bingo_from_marked(layout, marked_numbers, game.id)


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
    from .redis_utils import get_called_numbers_from_redis, get_effective_marked_numbers_for_card
    
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
        
        # Get called numbers: union Redis + DB so co-winner can claim after fake winner
        # (finalize may have cleared Redis and persisted to DB only).
        from .models import CalledNumber

        def _called_union() -> set:
            redis_called = get_called_numbers_from_redis(game.id) or set()
            db_called_local = set(CalledNumber.objects.filter(game=game).values_list('number', flat=True))
            return redis_called | db_called_local

        called_set = _called_union()
        if not called_set:
            return (False, None, "እስካሁን ምንም ቁጥር አልተጠራም")
        
        # Validate that all marked numbers on card were actually called
        if is_fake_user:
            effective_marked = get_effective_marked_numbers_for_card(
                game.id, card.id, card.card_layout, card.selected_numbers
            )
            if not effective_marked.issubset(called_set):
                # Small retry for Redis/DB visibility race around the latest called number.
                import time
                time.sleep(0.08)
                called_set = _called_union()
                if not effective_marked.issubset(called_set):
                    return (False, None, "አንዳንድ ቁጥሮች አልተጠራትም")
            from .fake_user_manager import check_fake_user_bingo
            has_bingo, winning_pattern = check_fake_user_bingo(card, called_set, game)
        else:
            effective_marked = get_effective_marked_numbers_for_card(
                game.id, card.id, card.card_layout, card.selected_numbers
            )
            if not effective_marked.issubset(called_set):
                # Small retry for Redis/DB visibility race around the latest called number.
                import time
                time.sleep(0.08)
                called_set = _called_union()
                if not effective_marked.issubset(called_set):
                    return (False, None, "ይህ ቁጥር አልተጠራም")
            has_bingo, winning_pattern = check_bingo(card, game)
        
        if not has_bingo:
            # Retry once for mark/claim race: user may press Bingo immediately after
            # tapping the last number while mark save is still in-flight.
            import time
            time.sleep(0.12)
            if is_fake_user:
                card = FakeUserGameCard.objects.select_related('fake_user').get(id=card.id)
                called_set = _called_union()
                from .fake_user_manager import check_fake_user_bingo
                has_bingo, winning_pattern = check_fake_user_bingo(card, called_set, game)
            else:
                card = GameCard.objects.select_related('user').get(id=card.id)
                has_bingo, winning_pattern = check_bingo(card, game)
            if not has_bingo:
                return (False, None, "ቢንጎ አልሰሩም")
        
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
            
            # Real first: 1s window; fake first: 3s. Single countdown, then task reads Redis and announces all.
            from .tasks import task_process_bingo_winners
            window_sec = 3 if is_fake_user else 1
            task_process_bingo_winners.apply_async(args=[game.id], countdown=window_sec)
            print(f"Scheduled task_process_bingo_winners for game {game.id} in {window_sec}s (completes game, credits, broadcasts)")
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


def prepare_test_co_win_sequence_for_game(game: Game, armed: bool) -> bool:
    """
    Build predetermined call order in Redis (shared last number for 1 real + 1 fake).
    Idempotent: if queue already exists (e.g. prepared at T-10s), only refreshes Redis active flag.
    """
    if not armed:
        return False
    from .models import GameSettings, FakeUserGameCard
    from .redis_utils import (
        test_co_win_queue_length,
        test_co_win_push_queue,
        set_test_co_win_completing_number,
        set_test_co_win_fake_card_id,
        set_test_co_win_active_redis,
    )
    from .test_co_win_sequence import build_test_co_win_sequence
    settings = GameSettings.get_settings()
    allow_system_account = settings.allow_system_account
    if test_co_win_queue_length(game.id) > 0:
        set_test_co_win_active_redis(game.id, True)
        return True
    real_n = game.gamecards.count()
    try:
        from .fake_user_manager import get_fake_user_count_for_game
        fake_n = get_fake_user_count_for_game(game) if allow_system_account else 0
    except Exception:
        fake_n = 0
    wp = getattr(settings, 'winning_patterns', ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card'])
    if not allow_system_account or real_n != 1 or fake_n != 1:
        return False
    rc = game.gamecards.first()
    fc = FakeUserGameCard.objects.filter(game=game).first()
    if not rc or not fc or not rc.card_layout or not fc.card_layout:
        return False
    seq = build_test_co_win_sequence(rc.card_layout, fc.card_layout, wp, game.id)
    if not seq:
        print(f"prepare_test_co_win_sequence_for_game: game {game.id} no valid sequence for layouts/patterns")
        return False
    if not test_co_win_push_queue(game.id, seq):
        return False
    set_test_co_win_completing_number(game.id, seq[-1])
    set_test_co_win_fake_card_id(game.id, fc.id)
    set_test_co_win_active_redis(game.id, True)
    print(f"prepare_test_co_win_sequence_for_game: game {game.id} len={len(seq)} last={seq[-1]}")
    return True


def prepare_anti_abuse_avoid_numbers_for_game(game: Game, enabled: bool) -> bool:
    """Store deduplicated avoid-list numbers for free_play_allowed=False users in Redis."""
    from .models import GameCard
    from .redis_utils import set_abuse_avoid_numbers
    if not enabled:
        set_abuse_avoid_numbers(game.id, [])
        try:
            Game.objects.filter(id=game.id).update(avoid_list_numbers=[])
        except Exception:
            pass
        return False
    restricted_cards = list(
        GameCard.objects.filter(game=game, user__free_play_allowed=False).select_related('user')
    )
    if not restricted_cards:
        set_abuse_avoid_numbers(game.id, [])
        try:
            Game.objects.filter(id=game.id).update(avoid_list_numbers=[])
        except Exception:
            pass
        return False
    # Positions by user requirement: 1o, 2n, 3i, 4g, 5b
    cells = [(0, 4), (1, 2), (2, 1), (3, 3), (4, 0)]
    if len(restricted_cards) > 10:
        # >10 users: skip 2n
        cells = [(r, c) for (r, c) in cells if not (r == 1 and c == 2)]
    avoid = set()
    for card in restricted_cards:
        layout = card.card_layout or []
        if not layout or len(layout) < 5:
            continue
        for r, c in cells:
            try:
                cell = layout[r][c]
                n = cell.get('number')
                if n is not None:
                    avoid.add(int(n))
            except Exception:
                continue
    avoid_list = sorted(list(avoid))
    set_abuse_avoid_numbers(game.id, avoid_list)
    try:
        Game.objects.filter(id=game.id).update(avoid_list_numbers=avoid_list)
    except Exception:
        pass
    print(f"prepare_anti_abuse_avoid_numbers_for_game: game {game.id} restricted={len(restricted_cards)} avoid={len(avoid)}")
    return bool(avoid)


def maybe_prepare_test_co_win_when_waiting(game: Game, settings) -> None:
    """
    When ~10s remain on card selection, scan real/fake cards and build the call sequence early.
    Throttled so we retry if players finish picking cards late.
    """
    from django.core.cache import cache
    if not settings:
        return
    test_armed = bool(getattr(settings, 'test_co_win_next_game', False))
    anti_enabled = bool(getattr(settings, 'anti_abuse_filter_enabled', False))
    if not test_armed and not anti_enabled:
        return
    throttle_key = f"game:{game.id}:pre_start_prepare_throttle"
    if cache.get(throttle_key):
        return
    cache.set(throttle_key, 1, 2)
    if test_armed and prepare_test_co_win_sequence_for_game(game, armed=True):
        cache.set(f"game:{game.id}:test_co_win_prep_sent", 1, timeout=120)
    if anti_enabled:
        prepare_anti_abuse_avoid_numbers_for_game(game, enabled=True)


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
    # Number calling uses fair random selection (per-user win control may be added separately).
    settings = GameSettings.get_settings()
    test_co_win_armed = getattr(settings, 'test_co_win_next_game', False)
    game_settings_cache_key = f'game:{game.id}:settings'
    pref = getattr(settings, 'fake_win_preference', 0)
    cache.set(game_settings_cache_key, {
        'time_between_calls': settings.time_between_calls,
        'allow_system_account': settings.allow_system_account,
        'free_play': settings.free_play,
        'fake_win_preference': pref,
        'bid_amount': float(settings.bid_amount),
        'percentage_cut': float(settings.percentage_cut),
        'card_selection_timer': settings.card_selection_timer,
        'total_cards': settings.total_cards,
        'system_accounts_min': getattr(settings, 'system_accounts_min', 15),
        'system_accounts_max': getattr(settings, 'system_accounts_max', 30),
        'winning_patterns': getattr(settings, 'winning_patterns', ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']),
        'test_co_win_mode': False,
        'anti_abuse_filter_enabled': getattr(settings, 'anti_abuse_filter_enabled', False),
    }, 3600)  # Cache for 1 hour (game won't last that long)
    game.fake_win_preference_snapshot = max(0, min(2, int(pref)))
    game.save(update_fields=['fake_win_preference_snapshot'])
    
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
    # Skip minimum fake fill when test co-win next game is armed (need exactly 1 real + 1 fake for QA)
    if allow_system_account and not test_co_win_armed:
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
    if allow_system_account and not test_co_win_armed:
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
    # Ensure anti-abuse avoid list exists for this started game (safe no-op if already prepared at T-10s)
    try:
        prepare_anti_abuse_avoid_numbers_for_game(game, enabled=getattr(settings, 'anti_abuse_filter_enabled', False))
    except Exception as e:
        print(f"prepare_anti_abuse_avoid_numbers_for_game start_game: {e}")
    
    # Test co-win QA: one-shot DB flag; predetermined calls; fake auto-claims on last number (needs 1 real + 1 fake)
    if test_co_win_armed:
        from .models import GameSettings as GSModel
        gs_row = GSModel.objects.get(pk=1)
        gs_row.test_co_win_next_game = False
        gs_row.save(update_fields=['test_co_win_next_game'])
        cache.delete('game_settings')
        game.refresh_from_db()
        ok = prepare_test_co_win_sequence_for_game(game, armed=True)
        if ok:
            gs_cache = cache.get(game_settings_cache_key) or {}
            gs_cache['test_co_win_mode'] = True
            cache.set(game_settings_cache_key, gs_cache, 3600)
            print(f"Game {game.id}: test_co_win_mode cached (Django) + queue in Redis")
        else:
            print(f"Game {game.id}: test co-win armed but preparation failed (need 1 real + 1 fake, layouts, solvable patterns)")
    
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

