"""
Auto game manager - creates new games after completion
"""
from django.utils import timezone
from datetime import timedelta
from .models import Game, GameSettings
from .game_logic import start_game
import random


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
    
    # Add fake users immediately if system accounts are enabled
    try:
        allow_system_account = getattr(settings, 'allow_system_account', False)
        if allow_system_account:
            add_fake_users_to_game_immediately(new_game)
    except Exception as e:
        # If fake user addition fails, log and continue
        print(f"Warning: Failed to add fake users in create_new_game_after_completion: {e}")
        import traceback
        traceback.print_exc()
    
    return new_game


def check_and_create_new_game():
    """Check if we need to create a new game"""
    # Check if there's already a waiting or active game
    existing_game = Game.objects.filter(status__in=['waiting', 'active']).first()
    
    if existing_game:
        # Ensure fake users are added if system accounts are enabled
        if existing_game.status == 'waiting':
            try:
                settings = GameSettings.get_settings()
                allow_system_account = getattr(settings, 'allow_system_account', False)
                if allow_system_account:
                    from .fake_user_manager import get_fake_user_count_for_game
                    fake_count = get_fake_user_count_for_game(existing_game)
                    if fake_count == 0:
                        add_fake_users_to_game_immediately(existing_game)
            except Exception as e:
                # If fake user addition fails, log and continue
                print(f"Warning: Failed to add fake users in check_and_create_new_game: {e}")
                import traceback
                traceback.print_exc()
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
    
    # Add fake users immediately if system accounts are enabled
    try:
        allow_system_account = getattr(settings, 'allow_system_account', False)
        if allow_system_account:
            add_fake_users_to_game_immediately(new_game)
    except Exception as e:
        # If fake user addition fails, log and continue
        print(f"Warning: Failed to add fake users in check_and_create_new_game (new game): {e}")
        import traceback
        traceback.print_exc()
    
    return new_game


def add_fake_users_to_game_immediately(game):
    """Add fake users to a game with staggered selections and simulate card changes
    Also schedules a task to adjust fake users at 5 seconds before timer ends
    
    IMPORTANT: Immediately selects cards for minimum fake users to ensure visual consistency
    """
    from .fake_user_manager import (
        initialize_fake_users,
        get_random_fake_users,
        get_available_card_numbers_for_fake,
        create_fake_user_card
    )
    from .tasks import task_select_fake_card_with_changes, task_adjust_fake_users_before_game_start
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    from .game_logic import get_available_card_numbers
    
    # Initialize fake users if needed
    initialize_fake_users()
    
    # Get system accounts range from settings
    settings = GameSettings.get_settings()
    # Use getattr with defaults in case migration hasn't been run yet
    # Wrap in try-except to handle database-level errors if migration hasn't run
    try:
        min_count = getattr(settings, 'system_accounts_min', 15)
        max_count = getattr(settings, 'system_accounts_max', 30)
        # If getattr returns None (field doesn't exist), use defaults
        if min_count is None:
            min_count = 15
        if max_count is None:
            max_count = 30
    except (AttributeError, Exception):
        # If any error occurs accessing these fields, use defaults
        min_count = 15
        max_count = 30
    
    # Ensure valid range
    if min_count < 1:
        min_count = 1
    if max_count < min_count:
        max_count = min_count
    
    # Randomly select total fake users within the configured range
    fake_user_count = random.randint(min_count, max_count)
    fake_users = get_random_fake_users(fake_user_count)
    
    # Get card selection timer to calculate selection rate
    timer_seconds = settings.card_selection_timer
    
    # Schedule all fake users to select at rate of 2 cards per second
    # This provides smooth, realistic UX - cards appear gradually, not all at once
    fake_user_ids = [fu.id for fu in fake_users]
    num_fake_users = len(fake_user_ids)
    
    if num_fake_users == 0:
        return []
    
    # Calculate available time window (reserve 5 seconds at the end for adjustments)
    available_time = max(2, timer_seconds - 5)  # At least 2 seconds available
    
    # Distribute selections evenly across available time
    # We want to spread them out smoothly, starting from 0.5s, ending at available_time
    # This ensures selections are spread across the entire timer window
    if num_fake_users <= 1:
        # Single user, schedule at 0.5s
        delays = [0.5]
    else:
        # Distribute evenly: start at 0.5s, end at available_time
        # Calculate interval to space them evenly
        time_span = available_time - 0.5  # Time from first (0.5s) to last selection
        interval = time_span / (num_fake_users - 1) if num_fake_users > 1 else 0.5
        
        # Generate delays: 0.5s, then evenly spaced to available_time
        delays = [0.5 + (i * interval) for i in range(num_fake_users)]
    
    # Execute first 2-4 selections immediately (synchronously) for instant visibility
    # Then schedule the rest with delays
    immediate_count = min(4, num_fake_users)  # Execute first 4 immediately
    
    from .fake_user_manager import get_available_card_numbers_for_fake, create_fake_user_card
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    from .game_logic import get_available_card_numbers
    
    channel_layer = get_channel_layer()
    available_cards = get_available_card_numbers_for_fake(game)
    
    # Execute immediate selections synchronously
    for i in range(immediate_count):
        if not available_cards:
            break
        
        fake_user = fake_users[i]
        fake_user_id = fake_user_ids[i]
        
        # Prefer cards from 1-100 range (70% chance)
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
            
            # Broadcast immediately
            try:
                async_to_sync(channel_layer.group_send)(
                    f'game_{game.id}',
                    {
                        'type': 'card_selected',
                        'data': {
                            'card_number': card_number,
                            'user_id': None,
                            'username': fake_user.name,
                            'is_fake': True,
                            'available_cards': get_available_card_numbers(game)
                        }
                    }
                )
            except Exception as e:
                print(f"WebSocket broadcast error for immediate fake user card: {e}")
            
            print(f"  Immediately selected fake user {fake_user_id} with card {card_number} (index {i})")
        except Exception as e:
            print(f"Error creating immediate fake user card: {e}")
    
    # Schedule remaining selections with calculated delays
    for i in range(immediate_count, num_fake_users):
        fake_user_id = fake_user_ids[i]
        
        # Get base delay for this user
        base_delay = delays[i] if i < len(delays) else delays[-1] + (i - len(delays) + 1) * 0.5
        
        # Add small random variation (0-0.25s) to make it look more natural
        max_variation = min(0.25, interval * 0.5 if num_fake_users > 1 else 0.25)
        random_variation = random.uniform(0.0, max_variation)
        delay = base_delay + random_variation
        
        # Ensure delay doesn't exceed available time
        delay = min(delay, available_time)
        
        # Ensure minimum delay of 0.3s to avoid immediate execution
        delay = max(0.3, delay)
        
        # Schedule the selection using eta (absolute time) for more reliable execution
        eta_time = timezone.now() + timedelta(seconds=delay)
        task_select_fake_card_with_changes.apply_async(
            args=[game.id, fake_user_id],
            eta=eta_time
        )
        
        # Debug logging for first few scheduled and last
        if i < immediate_count + 3 or i >= num_fake_users - 3:
            print(f"  Scheduled fake user {fake_user_id} with delay {delay:.2f}s (index {i}/{num_fake_users-1}, base={base_delay:.2f}s)")
    
    # Schedule task to adjust fake users at 5 seconds before timer ends
    # This will:
    # 1. Ensure we have at least min_system_accounts (add more if needed)
    # 2. Reduce fake users based on real player count (but never below minimum)
    timer_seconds = settings.card_selection_timer
    # Schedule at (timer_seconds - 5) seconds from now using eta for reliability
    adjustment_delay = max(0, timer_seconds - 5)
    adjustment_eta = timezone.now() + timedelta(seconds=adjustment_delay)
    task_adjust_fake_users_before_game_start.apply_async(args=[game.id], eta=adjustment_eta)
    
    print(f"Scheduled {len(fake_user_ids)} fake users for game {game.id} (target: {min_count}-{max_count}) at 2 cards/second rate, will verify/adjust at {adjustment_delay}s before game starts")
    return fake_user_ids

