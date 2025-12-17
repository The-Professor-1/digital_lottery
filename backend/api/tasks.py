"""
Celery background tasks for Bingo game operations
"""
from celery import shared_task
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Game, GameCard, CalledNumber, User
from .game_logic import call_number, check_bingo, claim_bingo, generate_bingo_card, create_game_card
from decimal import Decimal
import random
import time
from django.core.cache import cache
from typing import List

channel_layer = get_channel_layer()


@shared_task(bind=True, max_retries=3)
def task_call_number(self, game_id: int, number: int):
    """
    Background task to call a number in a game.
    After calling, checks all cards for bingo.
    """
    try:
        game = Game.objects.get(id=game_id)
        
        if game.status != 'active':
            return {'error': 'Game is not active'}
        
        # Call the number
        called_number = call_number(game, number)
        
        # Refresh game from database to get updated current_call_count
        game.refresh_from_db()
        
        # Broadcast number called via WebSocket
        try:
            async_to_sync(channel_layer.group_send)(
                f'game_{game.id}',
                {
                    'type': 'number_called',
                    'data': {
                        'number': called_number.number,
                        'letter': called_number.letter,
                        'call_count': game.current_call_count
                    }
                }
            )
        except Exception as e:
            print(f"WebSocket broadcast error in task_call_number: {e}")
        
        # Check all cards for bingo after calling number
        task_check_bingo_for_all_cards.delay(game_id)
        
        return {
            'success': True,
            'number': called_number.number,
            'letter': called_number.letter,
            'call_count': game.current_call_count
        }
    except Game.DoesNotExist:
        return {'error': 'Game not found'}
    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        # Retry on unexpected errors
        raise self.retry(exc=e, countdown=5)


def _get_card_current_mode(card):
    """Get the current mode for a card from mode_history"""
    mode_history = card.mode_history or []
    if not mode_history:
        # Default to manual if no mode history
        return 'manual'
    # Get the last mode entry (most recent)
    last_mode_entry = mode_history[-1]
    return last_mode_entry.get('mode', 'manual')


@shared_task(bind=True)
def task_check_bingo_for_all_cards(self, game_id: int):
    """
    Background task to check all cards in a game for bingo patterns.
    This runs after each number is called.
    Only auto-claims bingo for cards in automatic mode.
    """
    try:
        game = Game.objects.get(id=game_id)
        
        # Don't check if game is not active or already has a winner
        if game.status != 'active' or game.winner:
            return {'message': 'Game not active or already has winner'}
        
        # Get all cards for this game
        cards = GameCard.objects.filter(game=game, is_winner=False)
        
        winners_found = []
        
        for card in cards:
            # Check if card has bingo
            has_bingo, pattern = check_bingo(card, game)
            
            if has_bingo:
                # CRITICAL: Only auto-claim bingo if card is in automatic mode
                # In manual mode, user must manually click the bingo button
                card_mode = _get_card_current_mode(card)
                
                if card_mode != 'automatic':
                    # Manual mode - skip auto-claim, user will claim manually
                    print(f"Card {card.id} has bingo but is in {card_mode} mode - skipping auto-claim")
                    continue
                
                # Claim bingo for this card (only in automatic mode)
                try:
                    success, winning_pattern = claim_bingo(card, game)
                    if success:
                        winners_found.append({
                            'card_id': card.id,
                            'user_id': card.user.id,
                            'username': card.user.username,
                            'pattern': winning_pattern
                        })
                except Exception as e:
                    print(f"Error claiming bingo for card {card.id}: {e}")
        
        # If winners found, broadcast winner_declared
        if winners_found:
            game.refresh_from_db()
            if game.status == 'completed' and game.winner:
                # Prepare winner data
                winner_data = {
                    'game_id': game.id,
                    'winners': []
                }
                
                # Get all winner cards
                winner_cards = GameCard.objects.filter(game=game, is_winner=True)
                for winner_card in winner_cards:
                    # Recalculate winning pattern for this card
                    has_bingo, winning_pattern = check_bingo(winner_card, game)
                    winner_data['winners'].append({
                        'winner': {
                            'id': winner_card.user.id,
                            'username': winner_card.user.username
                        },
                        'card_number': winner_card.card_number,
                        'card_layout': winner_card.card_layout,
                        'winning_pattern': winning_pattern if has_bingo else None,
                        'prize': float(game.total_derash) / winner_cards.count() if winner_cards.count() > 0 else 0
                    })
                
                winner_data['total_prize'] = float(game.total_derash)
                winner_data['prize'] = float(game.total_derash) / winner_cards.count() if winner_cards.count() > 0 else 0
                
                # Broadcast winner declared
                try:
                    async_to_sync(channel_layer.group_send)(
                        f'game_{game.id}',
                        {
                            'type': 'winner_declared',
                            'data': winner_data
                        }
                    )
                except Exception as e:
                    print(f"WebSocket broadcast error for winner: {e}")
        
        return {'winners_found': len(winners_found)}
    except Game.DoesNotExist:
        return {'error': 'Game not found'}
    except Exception as e:
        print(f"Error in task_check_bingo_for_all_cards: {e}")
        return {'error': str(e)}


@shared_task(bind=True)
def task_process_bingo_winners(self, game_id: int):
    """
    Process all bingo winners after 1-second window expires.
    This task is called 1 second after the first winner claims bingo.
    """
    try:
        from .models import Game, GameCard, Transaction
        from .redis_utils import get_bingo_winners, cleanup_game_redis_keys
        from decimal import Decimal
        
        game = Game.objects.get(id=game_id)
        
        # Get all winners from Redis
        redis_winners = get_bingo_winners(game_id)
        
        if not redis_winners:
            print(f"No winners found in Redis for game {game_id}")
            cleanup_game_redis_keys(game_id)
            return {'error': 'No winners found'}
        
        # Get winner cards from database
        winner_card_ids = [w['card_id'] for w in redis_winners]
        winner_cards = list(GameCard.objects.filter(
            id__in=winner_card_ids,
            game=game,
            is_winner=True
        ).select_related('user'))
        
        if not winner_cards:
            print(f"No winner cards found for game {game_id}")
            cleanup_game_redis_keys(game_id)
            return {'error': 'No winner cards found'}
        
        # Refresh game to get latest derash
        game.refresh_from_db()
        
        # Calculate prize split
        total_prize = game.total_derash
        winner_count = len(winner_cards)
        prize_per_winner = total_prize / Decimal(str(winner_count)) if winner_count > 0 else Decimal('0')
        
        # Award prizes to all winners
        print(f"Processing {winner_count} winners for game {game_id}, total prize: {total_prize}, prize per winner: {prize_per_winner}")
        
        for winner_card in winner_cards:
            # Check if transaction already exists (to prevent double-payment)
            existing_transaction = Transaction.objects.filter(
                user=winner_card.user,
                game=game,
                transaction_type='win'
            ).first()
            
            if not existing_transaction:
                print(f"Awarding prize {prize_per_winner} to user {winner_card.user.id} (card {winner_card.card_number})")
                winner_card.user.refresh_from_db()
                old_balance = winner_card.user.balance
                winner_card.user.balance = Decimal(str(winner_card.user.balance)) + prize_per_winner
                winner_card.user.save()
                
                Transaction.objects.create(
                    user=winner_card.user,
                    transaction_type='win',
                    amount=prize_per_winner,
                    game=game,
                    description=f'Won game {game.id} (split among {winner_count} winners) with card {winner_card.card_number}'
                )
                print(f"User {winner_card.user.id} balance updated: {old_balance} -> {winner_card.user.balance}")
            else:
                print(f"User {winner_card.user.id} already received prize (transaction exists)")
        
        # Broadcast final winners list with correct prize split
        from .serializers import UserSerializer
        from .game_logic import check_bingo
        
        winners_data = []
        for winner_card in winner_cards:
            has_bingo, pattern = check_bingo(winner_card, game)
            winners_data.append({
                'winner': UserSerializer(winner_card.user).data,
                'card_number': winner_card.card_number,
                'card_id': winner_card.id,
                'card_layout': winner_card.card_layout,
                'winning_pattern': pattern if has_bingo else None,
                'prize': float(prize_per_winner)
            })
        
        # Broadcast final winner_declared with all winners
        try:
            async_to_sync(channel_layer.group_send)(
                f'game_{game.id}',
                {
                    'type': 'winner_declared',
                    'data': {
                        'winners': winners_data,
                        'winner': UserSerializer(winner_cards[0].user).data if winner_cards else None,
                        'total_prize': float(total_prize),
                        'prize': float(prize_per_winner),
                        'winner_count': winner_count
                    }
                }
            )
        except Exception as e:
            print(f"WebSocket broadcast error in task_process_bingo_winners: {e}")
        
        # Cleanup Redis keys
        cleanup_game_redis_keys(game_id)
        
        return {
            'success': True,
            'winners_processed': winner_count,
            'prize_per_winner': float(prize_per_winner)
        }
    except Game.DoesNotExist:
        return {'error': 'Game not found'}
    except Exception as e:
        print(f"Error in task_process_bingo_winners: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


@shared_task(bind=True, max_retries=3)
def task_auto_call_numbers(self, game_id: int):
    """
    Background task to automatically call numbers for a game.
    This runs continuously until game ends or all numbers are called.
    Uses recursive task scheduling to avoid long-running tasks.
    CRITICAL: Uses Redis lock to ensure only one number is called at a time.
    """
    try:
        # CRITICAL: Acquire lock to ensure only one instance calls numbers at a time
        from .redis_utils import acquire_number_calling_lock, release_number_calling_lock
        if not acquire_number_calling_lock(game_id, timeout=10):
            # Another instance is already calling a number, skip this execution
            print(f"Number calling lock already held for game {game_id}, skipping this execution")
            # Reschedule for next call using cached settings from game start
            from .models import GameSettings
            # CRITICAL: Use cached settings from game start to ensure consistency
            settings = GameSettings.get_settings(game_id=game_id)
            time_between_calls = settings.time_between_calls or 3
            task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
            return {'success': True, 'skipped': True, 'reason': 'Lock already held'}
        
        try:
            game = Game.objects.get(id=game_id)
            
            if game.status != 'active':
                release_number_calling_lock(game_id)
                return {'error': 'Game is not active', 'stopped': True}
            
            # Check if game has a winner
            if game.winner:
                release_number_calling_lock(game_id)
                return {'error': 'Game already has winner', 'stopped': True}
            
            from .models import GameSettings
            # Use cached settings from game start to prevent mid-game changes
            settings = GameSettings.get_settings(game_id=game_id)
            time_between_calls = settings.time_between_calls or 3  # Default to 3 seconds
            
            # Get current called numbers
            called_numbers = list(CalledNumber.objects.filter(game=game).values_list('number', flat=True))
            
            # If this is the first call, wait 3 seconds after game starts (matches frontend countdown)
            if len(called_numbers) == 0:
                time.sleep(3)
            
            available_numbers = list(range(1, 76))
            remaining = [n for n in available_numbers if n not in called_numbers]
            
            if not remaining:
                # All numbers called, wait a bit for BINGO claims
                time.sleep(5)
                game.refresh_from_db()
                if game.status == 'active' and not game.winner:
                    # No winner, end the game
                    game.status = 'completed'
                    game.completed_at = timezone.now()
                    game.save()
                    
                    # Cleanup Redis keys for this game
                    from .redis_utils import cleanup_game_redis_keys
                    cleanup_game_redis_keys(game.id)
                    
                    # Invalidate cache
                    cache.delete('game:current')
                    
                    try:
                        async_to_sync(channel_layer.group_send)(
                            f'game_{game.id}',
                            {
                                'type': 'game_ended',
                                'data': {
                                    'game_id': game.id,
                                    'no_winner': True
                                }
                            }
                        )
                    except Exception as e:
                        print(f"WebSocket broadcast error: {e}")
                release_number_calling_lock(game_id)
                return {'success': True, 'message': 'All numbers called', 'stopped': True}
            
            # Pick a number - use safe selection if fake users are enabled and free_play is off
            # Use cached settings from game start (prevents mid-game changes)
            from .fake_user_manager import get_safe_number_to_call
            called_numbers_set = set(called_numbers)
            
            # Get allow_system_account and free_play from cached settings
            # These are cached at game start to prevent mid-game changes
            allow_system_account = getattr(settings, 'allow_system_account', False)
            free_play = getattr(settings, 'free_play', False)
            
            if allow_system_account and not free_play:
                # Use safe number selection to ensure fake users can win
                number = get_safe_number_to_call(game, called_numbers_set, free_play=False)
                if number is None:
                    # Fallback to random if no safe number available
                    number = random.choice(remaining)
            else:
                # Free play or no fake users - use random selection
                number = random.choice(remaining)
            
            # Call the number directly (we're already in a background task)
            # CRITICAL: We have the lock, so only one instance can call a number at a time
            # CRITICAL: time_between_calls is already fetched from cached settings above
            try:
                # Double-check that number hasn't been called by another instance (race condition protection)
                game.refresh_from_db()
                if CalledNumber.objects.filter(game=game, number=number).exists():
                    print(f"WARNING: Number {number} was already called (race condition detected), skipping")
                    release_number_calling_lock(game_id)
                    # Reschedule immediately
                    task_auto_call_numbers.apply_async(args=[game_id], countdown=1)
                    return {'success': True, 'skipped': True, 'reason': 'Number already called'}
                
                called_number = call_number(game, number)
                
                # CRITICAL FIX: Broadcast number_called BEFORE checking for bingo
                # This ensures users see the number even if a fake user wins immediately
                # Refresh game from database to get updated current_call_count
                game.refresh_from_db()
                
                # Broadcast number called FIRST, before checking for winners
                try:
                    async_to_sync(channel_layer.group_send)(
                        f'game_{game.id}',
                        {
                            'type': 'number_called',
                            'data': {
                                'number': called_number.number,
                                'letter': called_number.letter,
                                'call_count': game.current_call_count
                            }
                        }
                    )
                except Exception as e:
                    print(f"WebSocket broadcast error in auto_call_numbers (number_called): {e}")
                
                # Mark number on fake user cards (optimized batch processing)
                from .fake_user_manager import mark_number_on_fake_card, check_fake_user_bingo
                from .models import FakeUserGameCard
                # Use select_related for better performance and list() to evaluate query once
                fake_cards = list(FakeUserGameCard.objects.filter(game=game, is_winner=False).select_related('fake_user'))
                
                # Process fake cards in batch for better performance
                called_numbers_set.add(number)
                for fake_card in fake_cards:
                    mark_number_on_fake_card(fake_card, number)
                    # Check if fake user won
                    has_bingo, pattern = check_fake_user_bingo(fake_card, called_numbers_set)
                    if has_bingo:
                        # Fake user won!
                        fake_card.is_winner = True
                        fake_card.winning_pattern = pattern
                        fake_card.save()
                        
                        # Mark game as completed if not already
                        game.refresh_from_db()
                        if game.status == 'active' and not game.winner:
                            game.status = 'completed'
                            game.completed_at = timezone.now()
                            game.save()
                            
                            # Broadcast fake user winner
                            try:
                                # Get called numbers for this game (CalledNumber is already imported at top)
                                called_numbers = list(CalledNumber.objects.filter(game=game).order_by('called_at').values_list('number', flat=True))
                                
                                # For fake users, the number that made them win is the number we just called
                                # This is checked BEFORE it's broadcasted to other users, so the number variable
                                # is definitely the one that completed the winning pattern
                                # We just need to verify it's actually in the winning pattern
                                last_called_number = None
                                if number and pattern and fake_card.card_layout:
                                    layout = fake_card.card_layout
                                    number_in_pattern = False
                                    
                                    # Check if the number is in the winning pattern
                                    if pattern.startswith('row_'):
                                        row_idx = int(pattern.split('_')[1])
                                        number_in_pattern = any(cell.get('number') == number for cell in layout[row_idx])
                                    elif pattern.startswith('col_'):
                                        col_idx = int(pattern.split('_')[1])
                                        number_in_pattern = any(layout[row_idx][col_idx].get('number') == number for row_idx in range(5))
                                    elif pattern == 'diagonal_1':
                                        number_in_pattern = any(layout[i][i].get('number') == number for i in range(5))
                                    elif pattern == 'diagonal_2':
                                        number_in_pattern = any(layout[i][4-i].get('number') == number for i in range(5))
                                    elif pattern == 'full_card':
                                        number_in_pattern = any(cell.get('number') == number for row in layout for cell in row)
                                    
                                    # If the number is in the pattern, use it (it's the one that made them win)
                                    if number_in_pattern:
                                        last_called_number = number
                                        print(f"Fake user winner: number {number} is in pattern {pattern}, using as last_called_number")
                                    else:
                                        print(f"WARNING: Fake user winner: number {number} is NOT in pattern {pattern}, but using it anyway")
                                
                                # Fallback: if we couldn't verify, use the number anyway (it should be correct)
                                # since we check bingo right after calling it
                                if last_called_number is None:
                                    last_called_number = number if number else (called_numbers[-1] if called_numbers else None)
                                    print(f"Fake user winner: Using fallback last_called_number: {last_called_number}")
                                
                                print(f"Fake user winner: Final last_called_number: {last_called_number}, number: {number}, pattern: {pattern}")
                                
                                # Calculate prize amount (derash_amount) - show even for fake users
                                from decimal import Decimal
                                game.refresh_from_db()
                                prize_amount = float(game.derash_amount) if game.derash_amount else 0.0
                                
                                winner_data = {
                                    'winner': {
                                        'id': None,
                                        'username': fake_card.fake_user.name,
                                        'name': fake_card.fake_user.name,
                                        'is_fake': True
                                    },
                                    'winners': [{
                                        'winner': {
                                            'id': None,
                                            'username': fake_card.fake_user.name,
                                            'name': fake_card.fake_user.name,
                                            'is_fake': True
                                        },
                                        'card_number': fake_card.card_number,
                                        'card_id': fake_card.id,
                                        'card_layout': fake_card.card_layout,
                                        'selected_numbers': fake_card.selected_numbers,  # Ticked numbers
                                        'called_numbers': called_numbers,  # All called numbers
                                        'last_called_number': last_called_number,  # The number that made them win
                                        'winning_pattern': pattern,
                                        'prize': prize_amount  # Show derash amount even for fake users
                                    }],
                                    'card_number': fake_card.card_number,
                                    'card_id': fake_card.id,
                                    'card_layout': fake_card.card_layout,
                                    'selected_numbers': fake_card.selected_numbers,  # Ticked numbers
                                    'called_numbers': called_numbers,  # All called numbers
                                    'last_called_number': last_called_number,  # The number that made them win
                                    'winning_pattern': pattern,
                                    'prize': prize_amount,  # Show derash amount even for fake users
                                    'total_prize': prize_amount,
                                    'winner_count': 1
                                }
                                
                                # Add 2.5 second delay AFTER number call before showing winner banner for fake users
                                # This makes it less obvious that fake users win
                                # The delay happens after the number has been called and broadcasted
                                time.sleep(2.5)
                                
                                async_to_sync(channel_layer.group_send)(
                                    f'game_{game.id}',
                                    {
                                        'type': 'winner_declared',
                                        'data': winner_data
                                    }
                                )
                                print(f"Broadcasted fake user winner: {fake_card.fake_user.name} (card {fake_card.card_number})")
                            except Exception as e:
                                print(f"Error broadcasting fake user winner: {e}")
                                import traceback
                                traceback.print_exc()
                            
                            # Cleanup Redis keys for this game
                            from .redis_utils import cleanup_game_redis_keys
                            cleanup_game_redis_keys(game.id)
                            
                            # Invalidate cache
                            cache.delete('game:current')
                            
                            # Release lock and stop calling numbers
                            release_number_calling_lock(game_id)
                            return {'success': True, 'fake_winner': True, 'stopped': True}
                
                # Check all real user cards for bingo after calling number
                task_check_bingo_for_all_cards.delay(game_id)
            except Exception as e:
                print(f"Error calling number {number} in auto_call_numbers: {e}")
                release_number_calling_lock(game_id)
                # If error, retry the task after delay
                if self.request.retries < self.max_retries:
                    raise self.retry(exc=e, countdown=time_between_calls)
                return {'error': f'Failed to call number after retries: {str(e)}'}
            
            # Release lock before scheduling next call
            release_number_calling_lock(game_id)
            
            # Schedule next call recursively (this prevents long-running tasks)
            # Wait according to settings before next call
            task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
            
            return {'success': True, 'number': number, 'scheduled_next': True}
        finally:
            # Always release lock in case of any unexpected errors
            try:
                release_number_calling_lock(game_id)
            except:
                pass
    except Game.DoesNotExist:
        return {'error': 'Game not found', 'stopped': True}
    except Exception as e:
        print(f"Error in task_auto_call_numbers: {e}")
        import traceback
        traceback.print_exc()
        # Retry if we haven't exceeded max retries
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=5)
        return {'error': str(e), 'stopped': True}


@shared_task(bind=True)
def task_generate_and_create_card(self, game_id: int, user_id: int, card_number: int):
    """
    Background task to generate a bingo card and create it for a user.
    This offloads the card generation work from the API request.
    """
    try:
        game = Game.objects.get(id=game_id)
        user = User.objects.get(id=user_id)
        
        # Generate card layout
        card_data = generate_bingo_card()
        
        # Create the card (this handles payment and validation)
        card = create_game_card(game, user, card_number)
        
        # Broadcast card selection
        try:
            from .game_logic import get_available_card_numbers
            async_to_sync(channel_layer.group_send)(
                f'game_{game.id}',
                {
                    'type': 'card_selected',
                    'data': {
                        'card_number': card_number,
                        'user_id': user.id,
                        'username': user.username,
                        'available_cards': get_available_card_numbers(game)
                    }
                }
            )
        except Exception as e:
            print(f"WebSocket broadcast error in task_generate_and_create_card: {e}")
        
        return {
            'success': True,
            'card_id': card.id,
            'card_number': card.card_number,
            'card_layout': card.card_layout
        }
    except Game.DoesNotExist:
        return {'error': 'Game not found'}
    except User.DoesNotExist:
        return {'error': 'User not found'}
    except Exception as e:
        print(f"Error in task_generate_and_create_card: {e}")
        return {'error': str(e)}


@shared_task(bind=True)
def task_refund_and_cancel_game(self, game_id: int, bet_amount: Decimal):
    """
    Background task to refund all players and cancel a game.
    This is called after a delay when admin cancels game with refund.
    """
    try:
        from .models import Game, GameCard, Transaction, AdminMessage
        from decimal import Decimal
        
        game = Game.objects.get(id=game_id)
        
        # Refund all players
        cards = GameCard.objects.filter(game_id=game_id).select_related('user')
        users_to_refund = {}
        for card in cards:
            user = card.user
            if user.id not in users_to_refund:
                users_to_refund[user.id] = {'user': user, 'amount': bet_amount}
        
        refunded_count = 0
        for user_id, refund_data in users_to_refund.items():
            user = refund_data['user']
            user.refresh_from_db()
            user.balance = Decimal(str(user.balance)) + refund_data['amount']
            user.save()
            Transaction.objects.create(
                user=user,
                transaction_type='bet',
                amount=refund_data['amount'],
                description=f'Refund for game {game_id} cancellation'
            )
            refunded_count += 1
        
        # Get admin message if it exists
        admin_message = AdminMessage.objects.filter(game=game).order_by('-created_at').first()
        
        # Cancel the game
        game.delete()
        
        # Mark message as processed
        if admin_message:
            admin_message.refund_processed = True
            admin_message.cancel_processed = True
            admin_message.save()
        
        return {
            'success': True,
            'refunded_count': refunded_count,
            'game_cancelled': True
        }
    except Game.DoesNotExist:
        return {'error': 'Game not found'}
    except Exception as e:
        print(f"Error in task_refund_and_cancel_game: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


@shared_task(bind=True, max_retries=3)
def task_add_fake_users_to_game(self, game_id: int, fake_user_ids: List[int]):
    """
    Background task to add fake users to a game with simulated delays
    This replaces threading for production-safe async execution
    """
    try:
        from .models import FakeUser, FakeUserGameCard
        from .fake_user_manager import (
            get_available_card_numbers_for_fake,
            create_fake_user_card
        )
        
        game = Game.objects.get(id=game_id)
        
        # Check if game is still waiting
        if game.status != 'waiting':
            return {'error': 'Game is not in waiting status', 'stopped': True}
        
        # Get fake users
        fake_users = FakeUser.objects.filter(id__in=fake_user_ids, is_active=True)
        if not fake_users.exists():
            return {'error': 'No active fake users found', 'stopped': True}
        
        available_cards = get_available_card_numbers_for_fake(game)
        if not available_cards:
            return {'error': 'No available cards', 'stopped': True}
        
        # Select cards for fake users with delays
        # Use Celery's countdown to simulate delays instead of time.sleep
        selected_count = 0
        for i, fake_user in enumerate(fake_users):
            if not available_cards:
                break
            
            # Calculate delay for this fake user (0.5 to 2.0 seconds)
            delay = random.uniform(0.5, 2.0)
            
            # Schedule individual card selection with delay
            task_select_single_fake_card.apply_async(
                args=[game_id, fake_user.id],
                countdown=delay + (i * 0.1)  # Stagger slightly to avoid race conditions
            )
            selected_count += 1
        
        return {
            'success': True,
            'scheduled_count': selected_count,
            'message': f'Scheduled {selected_count} fake user card selections'
        }
    except Game.DoesNotExist:
        return {'error': 'Game not found', 'stopped': True}
    except Exception as e:
        print(f"Error in task_add_fake_users_to_game: {e}")
        import traceback
        traceback.print_exc()
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=5)
        return {'error': str(e), 'stopped': True}


@shared_task(bind=True, max_retries=3)
def task_select_single_fake_card(self, game_id: int, fake_user_id: int):
    """
    Background task to select a single card for one fake user
    This is called with delays to simulate real user behavior
    """
    try:
        from .models import FakeUser, FakeUserGameCard
        from .fake_user_manager import (
            get_available_card_numbers_for_fake,
            create_fake_user_card
        )
        
        game = Game.objects.get(id=game_id)
        fake_user = FakeUser.objects.get(id=fake_user_id, is_active=True)
        
        # Check if game is still waiting
        if game.status != 'waiting':
            return {'error': 'Game is not in waiting status', 'stopped': True}
        
        # Check if fake user already has a card
        if FakeUserGameCard.objects.filter(game=game, fake_user=fake_user).exists():
            return {'error': 'Fake user already has a card', 'stopped': True}
        
        available_cards = get_available_card_numbers_for_fake(game)
        if not available_cards:
            return {'error': 'No available cards', 'stopped': True}
        
        # Randomly select a card
        card_number = random.choice(available_cards)
        
        try:
            card = create_fake_user_card(game, fake_user, card_number)
            
            # Broadcast card selection via WebSocket
            try:
                from .game_logic import get_available_card_numbers
                async_to_sync(channel_layer.group_send)(
                    f'game_{game.id}',
                    {
                        'type': 'card_selected',
                        'data': {
                            'card_number': card_number,
                            'user_id': None,  # Fake user
                            'username': fake_user.name,
                            'is_fake': True,
                            'available_cards': get_available_card_numbers(game)
                        }
                    }
                )
            except Exception as e:
                print(f"WebSocket broadcast error for fake user card: {e}")
            
            return {
                'success': True,
                'fake_user_id': fake_user_id,
                'fake_user_name': fake_user.name,
                'card_number': card_number
            }
        except ValueError as e:
            # Card was taken, try another if available
            if available_cards:
                available_cards.remove(card_number)
                if available_cards:
                    card_number = random.choice(available_cards)
                    try:
                        card = create_fake_user_card(game, fake_user, card_number)
                        return {
                            'success': True,
                            'fake_user_id': fake_user_id,
                            'card_number': card_number
                        }
                    except:
                        return {'error': 'Failed to select card after retry', 'stopped': True}
            return {'error': str(e), 'stopped': True}
    except (Game.DoesNotExist, FakeUser.DoesNotExist) as e:
        return {'error': f'Game or fake user not found: {str(e)}', 'stopped': True}
    except Exception as e:
        print(f"Error in task_select_single_fake_card: {e}")
        import traceback
        traceback.print_exc()
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=2)
        return {'error': str(e), 'stopped': True}


@shared_task(bind=True, max_retries=3)
def task_simulate_fake_user_selections(self, game_id: int, fake_user_ids: List[int]):
    """
    Simulate fake user card selections with staggered delays and card changes
    This task schedules individual selections with delays and simulates card changes
    """
    try:
        from .models import FakeUser, FakeUserGameCard
        from .fake_user_manager import (
            get_available_card_numbers_for_fake,
            create_fake_user_card
        )
        
        game = Game.objects.get(id=game_id)
        
        # Check if game is still waiting
        if game.status != 'waiting':
            return {'error': 'Game is not in waiting status', 'stopped': True}
        
        fake_users = FakeUser.objects.filter(id__in=fake_user_ids, is_active=True)
        if not fake_users.exists():
            return {'error': 'No active fake users found', 'stopped': True}
        
        # Schedule initial selections with staggered delays
        # IMPORTANT: All selections must complete within card_selection_timer
        # Get timer from settings to calculate max delay per user
        from .models import GameSettings
        settings = GameSettings.get_settings()
        timer_seconds = settings.card_selection_timer
        
        # Calculate max delay per user to ensure all finish before timer ends
        # Reserve 5 seconds buffer at the end, and distribute remaining time across all users
        # For 20-30 users, this gives ~0.5-1 second per user (with some randomness)
        max_total_time = timer_seconds - 5  # Reserve 5 seconds buffer
        num_users = len(fake_users)
        max_delay_per_user = max_total_time / num_users if num_users > 0 else 1.0
        # Clamp between 0.2 and 1.5 seconds per user
        max_delay_per_user = min(max(max_delay_per_user, 0.2), 1.5)
        
        cumulative_delay = 0
        for i, fake_user in enumerate(fake_users):
            # Add small random delay (0.2 to max_delay_per_user seconds) for each user
            delay_increment = random.uniform(0.2, max_delay_per_user)
            cumulative_delay += delay_increment
            task_select_fake_card_with_changes.apply_async(
                args=[game_id, fake_user.id],
                countdown=cumulative_delay
            )
        
        return {
            'success': True,
            'scheduled_count': len(fake_users),
            'message': f'Scheduled {len(fake_users)} fake user selections with delays'
        }
    except Game.DoesNotExist:
        return {'error': 'Game not found', 'stopped': True}
    except Exception as e:
        print(f"Error in task_simulate_fake_user_selections: {e}")
        import traceback
        traceback.print_exc()
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=5)
        return {'error': str(e), 'stopped': True}


@shared_task(bind=True, max_retries=3)
def task_select_fake_card_with_changes(self, game_id: int, fake_user_id: int):
    """
    Select a card for a fake user and simulate card changes until game starts
    This simulates real user behavior of changing cards
    """
    try:
        from .models import FakeUser, FakeUserGameCard
        from .fake_user_manager import (
            get_available_card_numbers_for_fake,
            create_fake_user_card
        )
        from .game_logic import get_available_card_numbers
        
        game = Game.objects.get(id=game_id)
        fake_user = FakeUser.objects.get(id=fake_user_id, is_active=True)
        
        # Check if game is still waiting
        if game.status != 'waiting':
            return {'error': 'Game is not in waiting status', 'stopped': True}
        
        # Get available cards (excluding real user cards)
        available_cards = get_available_card_numbers_for_fake(game)
        if not available_cards:
            return {'error': 'No available cards', 'stopped': True}
        
        # Select initial card
        card_number = random.choice(available_cards)
        
        try:
            # Check if fake user already has a card (from previous change)
            existing_card = FakeUserGameCard.objects.filter(game=game, fake_user=fake_user).first()
            if existing_card:
                # Unselect previous card (simulate user changing card)
                old_card_number = existing_card.card_number
                existing_card.delete()
                
                # Broadcast unselection
                try:
                    async_to_sync(channel_layer.group_send)(
                        f'game_{game.id}',
                        {
                            'type': 'card_selected',
                            'data': {
                                'card_number': None,  # Indicates unselection
                                'user_id': None,
                                'username': fake_user.name,
                                'is_fake': True,
                                'available_cards': get_available_card_numbers(game)
                            }
                        }
                    )
                except Exception as e:
                    print(f"WebSocket broadcast error for fake user unselection: {e}")
                
                # Delay before selecting new card - at least 2 seconds to make it less obvious
                time.sleep(random.uniform(2.0, 2.5))
            
            # Create new card
            card = create_fake_user_card(game, fake_user, card_number)
            
            # Broadcast card selection
            try:
                async_to_sync(channel_layer.group_send)(
                    f'game_{game.id}',
                    {
                        'type': 'card_selected',
                        'data': {
                            'card_number': card_number,
                            'user_id': None,  # Fake user
                            'username': fake_user.name,
                            'is_fake': True,
                            'available_cards': get_available_card_numbers(game)
                        }
                    }
                )
            except Exception as e:
                print(f"WebSocket broadcast error for fake user card: {e}")
            
            # Recalculate derash after card selection to ensure it includes all fake users
            game.refresh_from_db()
            game.recalculate_derash()
            game.refresh_from_db()  # Refresh again to get updated derash
            
            # Schedule card change simulation (reduced chance and faster timing)
            # Only 20% chance to change, and with much shorter delay to ensure completion before timer
            if game.status == 'waiting' and random.random() < 0.2:  # 20% chance (reduced from 40%)
                # Schedule a card change after 1.0-2.0 seconds (minimized to ensure players are added faster)
                change_delay = random.uniform(1.0, 2.0)
                task_select_fake_card_with_changes.apply_async(
                    args=[game_id, fake_user_id],
                    countdown=change_delay
                )
            
            return {
                'success': True,
                'fake_user_id': fake_user_id,
                'fake_user_name': fake_user.name,
                'card_number': card_number
            }
        except ValueError as e:
            # Card was taken, try another if available
            available_cards = get_available_card_numbers_for_fake(game)
            if available_cards and card_number in available_cards:
                available_cards.remove(card_number)
            if available_cards:
                card_number = random.choice(available_cards)
                try:
                    card = create_fake_user_card(game, fake_user, card_number)
                    # Broadcast selection
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
                        print(f"WebSocket broadcast error: {e}")
                    
                    game.refresh_from_db()
                    game.recalculate_derash()
                    
                    return {
                        'success': True,
                        'fake_user_id': fake_user_id,
                        'card_number': card_number
                    }
                except:
                    return {'error': 'Failed to select card after retry', 'stopped': True}
            return {'error': str(e), 'stopped': True}
    except (Game.DoesNotExist, FakeUser.DoesNotExist) as e:
        return {'error': f'Game or fake user not found: {str(e)}', 'stopped': True}
    except Exception as e:
        print(f"Error in task_select_fake_card_with_changes: {e}")
        import traceback
        traceback.print_exc()
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=2)
        return {'error': str(e), 'stopped': True}


@shared_task(bind=True, max_retries=2)
def task_adjust_fake_users_before_game_start(self, game_id: int):
    """
    Final adjustment of fake users at 5 seconds before game starts
    This is a safety check to ensure fake users match real player count
    Real-time adjustments happen in views.py when cards are selected/unselected
    """
    try:
        game = Game.objects.get(id=game_id)
        
        # Only adjust if game is still waiting
        if game.status != 'waiting':
            return {'error': 'Game is not in waiting status', 'skipped': True}
        
        from .models import GameCard
        from .fake_user_manager import get_fake_user_count_for_game
        from .models import FakeUserGameCard
        
        # Count real players (only those who have selected cards - GameCard)
        real_player_count = GameCard.objects.filter(game=game).count()
        
        # Count current fake users
        fake_user_count = get_fake_user_count_for_game(game)
        
        # Calculate how many fake users to remove
        # For every real player, remove one fake user
        fake_users_to_remove = min(real_player_count, fake_user_count)
        
        if fake_users_to_remove > 0:
            # Get fake user cards (randomly select which ones to remove)
            fake_cards = list(FakeUserGameCard.objects.filter(game=game))
            
            if len(fake_cards) > fake_users_to_remove:
                # Randomly select which fake users to remove
                import random
                cards_to_remove = random.sample(fake_cards, fake_users_to_remove)
                
                # Remove selected fake user cards
                for card in cards_to_remove:
                    card.delete()
                
                # Broadcast card unselection for removed fake users
                try:
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync
                    channel_layer = get_channel_layer()
                    
                    # Get updated available cards
                    from .game_logic import get_available_card_numbers
                    available_cards = get_available_card_numbers(game)
                    
                    # Broadcast unselection for each removed fake user
                    for card in cards_to_remove:
                        async_to_sync(channel_layer.group_send)(
                            f'game_{game.id}',
                            {
                                'type': 'card_selected',
                                'data': {
                                    'card_number': None,  # None means unselected
                                    'user_id': None,
                                    'username': card.fake_user.name,
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
                
                print(f"Adjusted fake users for game {game.id}: Removed {fake_users_to_remove} fake users (real players: {real_player_count}, remaining fake: {fake_user_count - fake_users_to_remove})")
                
                return {
                    'success': True,
                    'removed_count': fake_users_to_remove,
                    'real_players': real_player_count,
                    'remaining_fake': fake_user_count - fake_users_to_remove
                }
            elif len(fake_cards) == fake_users_to_remove:
                # Remove all fake users
                FakeUserGameCard.objects.filter(game=game).delete()
                
                # Broadcast all unselections
                try:
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync
                    channel_layer = get_channel_layer()
                    from .game_logic import get_available_card_numbers
                    available_cards = get_available_card_numbers(game)
                    
                    for card in fake_cards:
                        async_to_sync(channel_layer.group_send)(
                            f'game_{game.id}',
                            {
                                'type': 'card_selected',
                                'data': {
                                    'card_number': None,
                                    'user_id': None,
                                    'username': card.fake_user.name,
                                    'is_fake': True,
                                    'available_cards': available_cards
                                }
                            }
                        )
                except Exception as e:
                    print(f"Error broadcasting fake user removal: {e}")
                
                from django.core.cache import cache
                if cache:
                    cache.delete('game:current')
                    cache.delete(f'game:{game.id}')
                
                print(f"Removed all fake users for game {game.id} (real players: {real_player_count})")
                return {
                    'success': True,
                    'removed_count': fake_users_to_remove,
                    'real_players': real_player_count,
                    'remaining_fake': 0
                }
        
        return {
            'success': True,
            'removed_count': 0,
            'real_players': real_player_count,
            'remaining_fake': fake_user_count,
            'message': 'No adjustment needed'
        }
    except Game.DoesNotExist:
        return {'error': 'Game not found', 'stopped': True}
    except Exception as e:
        print(f"Error adjusting fake users: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e), 'stopped': True}

