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
    """
    try:
        game = Game.objects.get(id=game_id)
        
        if game.status != 'active':
            return {'error': 'Game is not active', 'stopped': True}
        
        # Check if game has a winner
        if game.winner:
            return {'error': 'Game already has winner', 'stopped': True}
        
        from .models import GameSettings
        settings = GameSettings.get_settings()
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
            return {'success': True, 'message': 'All numbers called', 'stopped': True}
        
        # Pick a random number from remaining
        number = random.choice(remaining)
        
        # Call the number directly (we're already in a background task)
        try:
            called_number = call_number(game, number)
            
            # Refresh game from database to get updated current_call_count
            game.refresh_from_db()
            
            # Broadcast number called
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
                print(f"WebSocket broadcast error in auto_call_numbers: {e}")
            
            # Check all cards for bingo after calling number
            task_check_bingo_for_all_cards.delay(game_id)
        except Exception as e:
            print(f"Error calling number {number} in auto_call_numbers: {e}")
            # If error, retry the task after delay
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e, countdown=time_between_calls)
            return {'error': f'Failed to call number after retries: {str(e)}'}
        
        # Schedule next call recursively (this prevents long-running tasks)
        # Wait according to settings before next call
        task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
        
        return {'success': True, 'number': number, 'scheduled_next': True}
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

