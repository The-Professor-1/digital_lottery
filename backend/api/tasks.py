"""
Celery background tasks for Bingo game operations
"""
from celery import shared_task
from django.utils import timezone
from .models import Game, GameCard, CalledNumber, User, FakeUserGameCard
from .game_logic import call_number, check_bingo, claim_bingo, generate_bingo_card, create_game_card
from .channels import broadcast_to_game_rooms
from .redis_utils import batch_broadcast_to_game
from decimal import Decimal
import random
import time
from django.core.cache import cache
from typing import List


@shared_task(bind=True, queue='gameplay', name='api.tasks.test_celery_connection')
def test_celery_connection(self):
    """Simple test task to verify Celery is working"""
    print("✅ CELERY IS WORKING! Test task executed successfully!")
    import logging
    logger = logging.getLogger(__name__)
    logger.info("✅ CELERY IS WORKING! Test task executed successfully!")
    return {'success': True, 'message': 'Celery is working'}


@shared_task(bind=True, max_retries=3, queue='gameplay')
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
        
        # CRITICAL FIX: Only mark number on real user cards that are in AUTOMATIC mode
        # Manual mode users must mark their own numbers
        from .game_logic import mark_number_on_card
        from .models import GameCard
        
        # Get all real user cards for this game
        real_cards = GameCard.objects.filter(game=game, is_winner=False).only('id', 'mode_history')
        marked_count = 0
        
        for card in real_cards:
            # Check card mode - only mark if in automatic mode
            card_mode = _get_card_current_mode(card)
            if card_mode == 'automatic':
                # Only mark numbers automatically for cards in automatic mode
                if mark_number_on_card(card, number):
                    marked_count += 1
            # Manual mode cards are NOT marked automatically - user must mark them manually
        
        print(f"Manually called number {number}: Marked on {marked_count} real user cards (automatic mode only)")
        
        # Refresh game from database to get updated current_call_count
        game.refresh_from_db()
        
        # Broadcast number called via WebSocket (players + watchers rooms)
        try:
            broadcast_to_game_rooms(game.id, 'number_called', {
                'number': called_number.number,
                'letter': called_number.letter,
                'call_count': game.current_call_count
            })
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


@shared_task(bind=True, queue='gameplay')
def task_check_bingo_for_all_cards(self, game_id: int):
    """
    Background task to check all cards in a game for bingo patterns.
    This runs after each number is called.
    Only auto-claims bingo for cards in automatic mode.
    """
    try:
        # CRITICAL FIX: Get game and immediately refresh to get latest status
        # This ensures we see the latest game status even if a real user just won manually
        # Note: Can't use select_for_update in Celery tasks (requires transaction)
        game = Game.objects.get(id=game_id)
        
        # CRITICAL FIX: Refresh immediately to get the absolute latest status
        # This prevents race conditions when a real user manually claims bingo
        game.refresh_from_db()
        
        # CRITICAL FIX: Don't check if game is not active or already has a winner
        # This prevents fake users from winning after a real user has won
        if game.status != 'active' or game.winner:
            print(f"Game {game_id}: Not checking bingo - status: {game.status}, winner: {game.winner}")
            return {'message': 'Game not active or already has winner'}
        
        # PHASE 3 OPTIMIZATION: Filter cards early using Redis (skip cards with < 5 marked numbers)
        # This reduces database queries and CPU time significantly
        from .redis_utils import get_card_marked_count_redis
        
        # Get all cards for this game
        all_cards = GameCard.objects.filter(game=game, is_winner=False).only('id', 'is_winner', 'mode_history')
        
        # Filter cards using Redis (early exit optimization)
        potential_winners = []
        for card in all_cards:
            marked_count = get_card_marked_count_redis(card.id)
            # Only check cards with 5+ marked numbers (minimum for bingo)
            if marked_count >= 5:
                potential_winners.append(card)
        
        # If no potential winners, return early (no database queries needed)
        if not potential_winners:
            return {'message': 'No potential winners found', 'cards_checked': len(all_cards), 'potential_winners': 0}
        
        # Load full card data only for potential winners (reduces queries)
        card_ids = [card.id for card in potential_winners]
        cards = GameCard.objects.filter(id__in=card_ids).select_related('user')
        
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
                
                # PHASE 2 OPTIMIZATION #2: Get called numbers from Redis (faster)
                from .redis_utils import get_called_numbers_list_from_redis
                from .game_logic import get_winning_number
                called_numbers = get_called_numbers_list_from_redis(game.id)
                
                for winner_card in winner_cards:
                    # Recalculate winning pattern for this card
                    has_bingo, winning_pattern = check_bingo(winner_card, game)
                    
                    # CRITICAL FIX: Find the actual number that completed the bingo pattern
                    # This is the number that should be highlighted, not just the last number called
                    winning_number = get_winning_number(winner_card, winning_pattern if has_bingo else None, called_numbers)
                    if not winning_number:
                        # Fallback to last called number if we can't determine the winning number
                        winning_number = called_numbers[-1] if called_numbers else None
                    
                    winner_data['winners'].append({
                        'winner': {
                            'id': winner_card.user.id,
                            'username': winner_card.user.username
                        },
                        'card_number': winner_card.card_number,
                        'card_layout': winner_card.card_layout,
                        'winning_pattern': winning_pattern if has_bingo else None,
                        'selected_numbers': winner_card.selected_numbers or [],
                        'called_numbers': called_numbers,
                        'last_called_number': winning_number,  # The number that completed this card's bingo
                        'prize': float(game.total_derash) / winner_cards.count() if winner_cards.count() > 0 else 0
                    })
                
                winner_data['total_prize'] = float(game.total_derash)
                winner_data['prize'] = float(game.total_derash) / winner_cards.count() if winner_cards.count() > 0 else 0
                
                # Broadcast winner declared (players + watchers rooms)
                try:
                    broadcast_to_game_rooms(game.id, 'winner_declared', winner_data)
                except Exception as e:
                    print(f"WebSocket broadcast error for winner: {e}")
        
        return {'winners_found': len(winners_found)}
    except Game.DoesNotExist:
        return {'error': 'Game not found'}
    except Exception as e:
        print(f"Error in task_check_bingo_for_all_cards: {e}")
        return {'error': str(e)}


@shared_task(bind=True, queue='gameplay')
def task_process_bingo_winners(self, game_id: int):
    """
    Single decider for bingo winners: runs after the 2s tie window.
    Reads the single source (Redis bingo_winners set), then:
    - 1 winner: announce and add full prize.
    - N winners: announce all and split prize; credit each real winner.
    Only this task broadcasts winner_declared and game_ended (API does not).
    """
    try:
        from django.utils import timezone
        from .models import Game, GameCard, Transaction, User
        from .redis_utils import get_bingo_winners, cleanup_game_redis_keys, sync_game_state_to_redis
        from decimal import Decimal
        
        game = Game.objects.get(id=game_id)
        
        # Get all winners from Redis
        redis_winners = get_bingo_winners(game_id)
        
        if not redis_winners:
            print(f"No winners found in Redis for game {game_id}")
            cleanup_game_redis_keys(game_id)
            return {'error': 'No winners found'}
        
        # Separate real and fake user winners
        real_winner_card_ids = [w['card_id'] for w in redis_winners if w['user_id'] is not None]
        fake_winner_card_ids = [w['card_id'] for w in redis_winners if w['user_id'] is None]
        
        # Get real user winner cards
        real_winner_cards = list(GameCard.objects.filter(
            id__in=real_winner_card_ids,
            game=game,
            is_winner=True
        ).select_related('user')) if real_winner_card_ids else []
        
        # Get fake user winner cards
        from .models import FakeUserGameCard
        fake_winner_cards = list(FakeUserGameCard.objects.filter(
            id__in=fake_winner_card_ids,
            game=game,
            is_winner=True
        ).select_related('fake_user')) if fake_winner_card_ids else []
        
        # Combine all winner cards (we'll process them separately)
        winner_cards = real_winner_cards
        all_winner_count = len(real_winner_cards) + len(fake_winner_cards)
        
        if all_winner_count == 0:
            print(f"No winner cards found for game {game_id}")
            cleanup_game_redis_keys(game_id)
            return {'error': 'No winner cards found'}
        
        # Set game completed and winner(s) so /completed view sees completed and redirects to card selection
        game.refresh_from_db()
        if game.status == 'active':
            now = timezone.now()
            first_real_user = real_winner_cards[0].user if real_winner_cards else None
            Game.objects.filter(id=game_id, status='active').update(
                status='completed', completed_at=now,
                winner_id=first_real_user.id if first_real_user else None
            )
            game.refresh_from_db()
            if real_winner_cards:
                game.winners.set([c.user for c in real_winner_cards])
            sync_game_state_to_redis(game)
            from .user_utils import update_user_withdrawal_approval
            for uid in GameCard.objects.filter(game_id=game_id).values_list('user_id', flat=True).distinct():
                if uid:
                    try:
                        u = User.objects.get(pk=uid)
                        update_user_withdrawal_approval(u)
                    except User.DoesNotExist:
                        pass
            print(f"Game {game_id} marked completed in task_process_bingo_winners (split prize)")
            try:
                from django.core.cache import cache
                cache.delete('game:current')
            except Exception:
                pass
        
        # Refresh game to get latest derash
        game.refresh_from_db()
        
        # Calculate prize split (split by ALL winners for realism, but only real users receive prizes)
        total_prize = game.total_derash
        real_winner_count = len(real_winner_cards)
        all_winner_count = len(real_winner_cards) + len(fake_winner_cards)
        
        # CRITICAL FIX: Split prize by ALL winners (real + fake) to make it look realistic
        # Real players see 3 winners announced, so prize should be split 3 ways
        # But only real winners actually receive the split amount
        prize_per_winner = total_prize / Decimal(str(all_winner_count)) if all_winner_count > 0 else Decimal('0')
        
        # Award prizes to real winners only (fake users don't get prizes, but are counted in split)
        print(f"Processing {all_winner_count} winners ({real_winner_count} real, {len(fake_winner_cards)} fake) for game {game_id}, total prize: {total_prize}, prize split by {all_winner_count} winners = {prize_per_winner} per winner (only real winners receive)")
        
        # CRITICAL FIX: Use atomic transaction and F() expressions for balance updates
        from django.db import transaction
        from django.db.models import F
        
        for winner_card in real_winner_cards:
            # Check if transaction already exists (to prevent double-payment)
            existing_transaction = Transaction.objects.filter(
                user=winner_card.user,
                game=game,
                transaction_type='win'
            ).first()
            
            if not existing_transaction:
                try:
                    with transaction.atomic():
                        user = User.objects.select_for_update().get(id=winner_card.user.id)
                        old_balance = user.balance
                        # Prize: add to withdrawable_balance if user has deposited >= min_withdraw, else unwithdrawable_balance
                        if user.has_withdrawable_active():
                            User.objects.filter(id=user.id).update(withdrawable_balance=F('withdrawable_balance') + prize_per_winner)
                        else:
                            User.objects.filter(id=user.id).update(unwithdrawable_balance=F('unwithdrawable_balance') + prize_per_winner)
                        user.refresh_from_db()
                        Transaction.objects.create(
                            user=user,
                            transaction_type='win',
                            amount=prize_per_winner,
                            game=game,
                            description=f'Won game {game.id} (split among {all_winner_count} winners) with card {winner_card.card_number}'
                        )
                        print(f"✅ Awarded prize {prize_per_winner} to user {user.id} (card {winner_card.card_number}), balance: {old_balance} -> {user.balance}")
                except Exception as e:
                    print(f"❌ ERROR awarding prize to user {winner_card.user.id}: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continue processing other winners even if one fails
            else:
                print(f"⚠️ User {winner_card.user.id} already received prize (transaction exists)")
        
        # Broadcast final winners list with correct prize split
        from .serializers import UserSerializer
        from .game_logic import check_bingo, get_winning_number
        from .redis_utils import get_called_numbers_list_from_redis
        from .fake_user_manager import check_fake_user_bingo
        
        # PHASE 2 OPTIMIZATION: Get called numbers from Redis (faster)
        called_numbers = get_called_numbers_list_from_redis(game.id)
        called_numbers_set = set(called_numbers) if called_numbers else set()
        
        winners_data = []
        
        # Process real user winners
        for winner_card in real_winner_cards:
            has_bingo, pattern = check_bingo(winner_card, game)
            
            # CRITICAL FIX: Find the actual number that completed the bingo pattern
            # This is the number that should be highlighted, not just the last number called
            winning_number = get_winning_number(winner_card, pattern if has_bingo else None, called_numbers)
            if not winning_number:
                # Fallback to last called number if we can't determine the winning number
                winning_number = called_numbers[-1] if called_numbers else None
            
            winners_data.append({
                'winner': UserSerializer(winner_card.user).data,
                'username': winner_card.user.username,
                'is_fake': False,
                'card_number': winner_card.card_number,
                'card_id': winner_card.id,
                'card_layout': winner_card.card_layout,
                'winning_pattern': pattern if has_bingo else None,
                'selected_numbers': winner_card.selected_numbers or [],
                'called_numbers': called_numbers,
                'last_called_number': winning_number,  # The number that completed this card's bingo
                'prize': float(prize_per_winner)  # Show split amount (realistic for all winners)
            })
        
        # Process fake user winners (they don't get prizes, but are shown in winners list)
        for fake_card in fake_winner_cards:
            has_bingo, pattern = check_fake_user_bingo(fake_card, called_numbers_set, game)
            
            # Find winning number for fake user
            winning_number = None
            if pattern and called_numbers:
                layout = fake_card.card_layout
                if layout:
                    pattern_numbers = []
                    if pattern.startswith('row_'):
                        row_idx = int(pattern.split('_')[1])
                        pattern_numbers = [cell.get('number') for cell in layout[row_idx] if cell.get('number') is not None]
                    elif pattern.startswith('col_'):
                        col_idx = int(pattern.split('_')[1])
                        pattern_numbers = [layout[row_idx][col_idx].get('number') for row_idx in range(5) if layout[row_idx][col_idx].get('number') is not None]
                    elif pattern == 'diagonal_1':
                        pattern_numbers = [layout[i][i].get('number') for i in range(5) if layout[i][i].get('number') is not None]
                    elif pattern == 'diagonal_2':
                        pattern_numbers = [layout[i][4-i].get('number') for i in range(5) if layout[i][4-i].get('number') is not None]
                    elif pattern == 'corner':
                        corners = [layout[0][0], layout[0][4], layout[4][0], layout[4][4], layout[2][2]]
                        pattern_numbers = [cell.get('number') for cell in corners if cell.get('number') is not None]
                    elif pattern == 'full_card':
                        pattern_numbers = [cell.get('number') for row in layout for cell in row if cell.get('number') is not None]
                    
                    # Find the last called number that's in the pattern
                    for number in reversed(called_numbers):
                        if number in pattern_numbers:
                            winning_number = number
                            break
            
            if not winning_number:
                winning_number = called_numbers[-1] if called_numbers else None
            
            # Create a winner object for fake users (same structure as in claim_bingo_unified)
            fake_winner_obj = {
                'id': None,
                'username': fake_card.fake_user.name,
                'name': fake_card.fake_user.name,
                'is_fake': True
            }
            
            winners_data.append({
                'winner': fake_winner_obj,  # Include winner object with username for frontend consistency
                'username': fake_card.fake_user.name,
                'is_fake': True,
                'card_number': fake_card.card_number,
                'card_id': fake_card.id,
                'card_layout': fake_card.card_layout,
                'winning_pattern': pattern if has_bingo else None,
                'selected_numbers': fake_card.selected_numbers or [],
                'called_numbers': called_numbers,
                'last_called_number': winning_number,
                'prize': float(prize_per_winner)  # Show split amount (for display consistency, but they don't actually receive it)
            })
        
        # Broadcast final winner_declared with all winners
        try:
            # Determine primary winner (first real user if any, otherwise first fake user)
            primary_winner = None
            if real_winner_cards:
                primary_winner = UserSerializer(real_winner_cards[0].user).data
            elif fake_winner_cards:
                # Create winner object for fake user (same structure as in claim_bingo_unified)
                primary_winner = {
                    'id': None,
                    'username': fake_winner_cards[0].fake_user.name,
                    'name': fake_winner_cards[0].fake_user.name,
                    'is_fake': True
                }
            
            # Show split prize amount for all winners (realistic display)
            # All winners see the same split amount, but only real winners actually receive it
            display_prize = float(prize_per_winner)
            
            broadcast_to_game_rooms(game.id, 'winner_declared', {
                'winners': winners_data,
                'winner': primary_winner,
                'total_prize': float(total_prize),
                'prize': display_prize,
                'winner_count': all_winner_count
            })
            broadcast_to_game_rooms(game.id, 'game_ended', {
                'game_id': game.id,
                'status': 'completed',
                'completed_at': game.completed_at.isoformat() if game.completed_at else None,
                'winner': primary_winner,
                'winner_count': all_winner_count
            })
        except Exception as e:
            print(f"WebSocket broadcast error in task_process_bingo_winners: {e}")
        
        # Cleanup Redis keys
        cleanup_game_redis_keys(game_id)
        
        return {
            'success': True,
            'winners_processed': all_winner_count,
            'real_winners': real_winner_count,
            'fake_winners': len(fake_winner_cards),
            'prize_per_winner': float(prize_per_winner) if real_winner_count > 0 else 0.0
        }
    except Game.DoesNotExist:
        return {'error': 'Game not found'}
    except Exception as e:
        print(f"Error in task_process_bingo_winners: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


@shared_task(bind=True, queue='gameplay')
def task_broadcast_winner_declared_delayed(game_id: int):
    """
    Runs once after the fixed tie window (3s if first was fake, 1s if first was real).
    Sets game completed, then broadcasts winner_declared and game_ended with whoever is
    in the winner list at this moment (no extra wait per co-winner).
    """
    try:
        from django.utils import timezone
        from .models import Game, GameCard, FakeUserGameCard
        from .redis_utils import (
            get_bingo_winners,
            get_called_numbers_list_from_redis,
            batch_broadcast_to_game,
            sync_game_state_to_redis,
        )
        from .serializers import UserSerializer
        from .game_logic import check_bingo, get_winning_number
        from .fake_user_manager import check_fake_user_bingo

        game = Game.objects.get(id=game_id)
        # If task_process_bingo_winners already ran and set completed, skip broadcast to avoid duplicate
        if game.status == 'completed':
            # Still update withdrawal_approval for players
            from .models import User
            from .user_utils import update_user_withdrawal_approval
            for uid in GameCard.objects.filter(game_id=game_id).values_list('user_id', flat=True).distinct():
                if uid:
                    try:
                        u = User.objects.get(pk=uid)
                        update_user_withdrawal_approval(u)
                    except User.DoesNotExist:
                        pass
            return {'skipped': True, 'reason': 'Game already completed by task_process_bingo_winners'}

        # Set game completed only when this task runs (e.g. if task_process_bingo_winners didn't run first)
        if game.status == 'active':
            now = timezone.now()
            Game.objects.filter(id=game_id, status='active').update(status='completed', completed_at=now)
            game.refresh_from_db()
            sync_game_state_to_redis(game)
            try:
                from django.core.cache import cache
                cache.delete('game:current')
            except Exception:
                pass
            print(f"Game {game_id} marked completed in delayed task (tie window ended)")
            from .models import User
            from .user_utils import update_user_withdrawal_approval
            for uid in GameCard.objects.filter(game_id=game_id).values_list('user_id', flat=True).distinct():
                if uid:
                    try:
                        u = User.objects.get(pk=uid)
                        update_user_withdrawal_approval(u)
                    except User.DoesNotExist:
                        pass

        redis_winners = get_bingo_winners(game_id)
        if not redis_winners:
            return {'error': 'No winners in Redis'}

        real_ids = [w['card_id'] for w in redis_winners if w.get('user_id') is not None]
        fake_ids = [w['card_id'] for w in redis_winners if w.get('user_id') is None]
        real_cards = list(GameCard.objects.filter(id__in=real_ids, game=game, is_winner=True).select_related('user')) if real_ids else []
        fake_cards = list(FakeUserGameCard.objects.filter(id__in=fake_ids, game=game, is_winner=True).select_related('fake_user')) if fake_ids else []
        all_count = len(real_cards) + len(fake_cards)
        if all_count == 0:
            return {'error': 'No winner cards'}

        game.refresh_from_db()
        total_prize = float(game.total_derash or 0)
        prize_per = total_prize / all_count if all_count else 0.0
        called_numbers = get_called_numbers_list_from_redis(game_id)
        called_set = set(called_numbers) if called_numbers else set()

        winners_data = []
        for c in real_cards:
            _, pat = check_bingo(c, game)
            wn = get_winning_number(c, pat, called_numbers)
            winners_data.append({
                'winner': UserSerializer(c.user).data,
                'username': c.user.username,
                'is_fake': False,
                'card_number': c.card_number,
                'card_id': c.id,
                'card_layout': c.card_layout,
                'selected_numbers': c.selected_numbers or [],
                'winning_pattern': pat,
                'last_called_number': wn or (called_numbers[-1] if called_numbers else None),
                'called_numbers': called_numbers,
                'prize': prize_per
            })
        for c in fake_cards:
            _, pattern = check_fake_user_bingo(c, called_set, game)
            wn = None
            if pattern and called_numbers and c.card_layout:
                layout = c.card_layout
                pattern_numbers = []
                if pattern.startswith('row_'):
                    row_idx = int(pattern.split('_')[1])
                    pattern_numbers = [cell.get('number') for cell in layout[row_idx] if cell.get('number') is not None]
                elif pattern.startswith('col_'):
                    col_idx = int(pattern.split('_')[1])
                    pattern_numbers = [layout[r][col_idx].get('number') for r in range(5) if layout[r][col_idx].get('number') is not None]
                elif pattern == 'diagonal_1':
                    pattern_numbers = [layout[i][i].get('number') for i in range(5) if layout[i][i].get('number') is not None]
                elif pattern == 'diagonal_2':
                    pattern_numbers = [layout[i][4-i].get('number') for i in range(5) if layout[i][4-i].get('number') is not None]
                elif pattern == 'corner':
                    corners = [layout[0][0], layout[0][4], layout[4][0], layout[4][4], layout[2][2]]
                    pattern_numbers = [cell.get('number') for cell in corners if cell and cell.get('number') is not None]
                else:
                    pattern_numbers = [cell.get('number') for row in layout for cell in row if cell.get('number') is not None]
                for num in reversed(called_numbers):
                    if num in pattern_numbers:
                        wn = num
                        break
            winners_data.append({
                'winner': {'id': None, 'username': c.fake_user.name, 'name': c.fake_user.name, 'is_fake': True},
                'username': c.fake_user.name,
                'is_fake': True,
                'card_number': c.card_number,
                'card_id': c.id,
                'card_layout': c.card_layout,
                'selected_numbers': c.selected_numbers or [],
                'winning_pattern': getattr(c, 'winning_pattern', None),
                'last_called_number': wn or (called_numbers[-1] if called_numbers else None),
                'called_numbers': called_numbers,
                'prize': prize_per
            })

        primary = winners_data[0]['winner'] if winners_data else None
        batch_broadcast_to_game(game_id, [
            {
                'type': 'winner_declared',
                'data': {
                    'winners': winners_data,
                    'winner': primary,
                    'total_prize': total_prize,
                    'prize': prize_per,
                    'winner_count': all_count
                }
            },
            {
                'type': 'game_ended',
                'data': {
                    'game_id': game_id,
                    'status': 'completed',
                    'completed_at': game.completed_at.isoformat() if game.completed_at else None,
                    'winner': primary,
                    'winner_count': all_count
                }
            }
        ])
        print(f"Broadcasted winner_declared (delayed) for game {game_id}: {all_count} winner(s)")
        return {'success': True, 'winner_count': all_count}
    except Exception as e:
        print(f"Error in task_broadcast_winner_declared_delayed: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


@shared_task(bind=True, max_retries=3, queue='gameplay')
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
        if not acquire_number_calling_lock(game_id, timeout=30):
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
            # PHASE 4 OPTIMIZATION: Check game state from Redis cache first (faster than DB)
            from .redis_utils import get_game_state_from_redis
            cached_state = get_game_state_from_redis(game_id)
            
            # If cache has status, use it for fast check
            if cached_state and 'status' in cached_state:
                if cached_state['status'] != 'active':
                    print(f"Game {game_id}: Not active (status: {cached_state['status']}), stopping number calling")
                    release_number_calling_lock(game_id)
                    return {'error': 'Game is not active', 'stopped': True}
                
                # Check winner from cache if available
                if cached_state.get('winner_id'):
                    print(f"Game {game_id}: Already has winner (from cache), stopping number calling")
                    release_number_calling_lock(game_id)
                    return {'error': 'Game already has winner', 'stopped': True}
            
            # Get game from DB (needed for operations, but we've already checked status from cache)
            game = Game.objects.get(id=game_id)
            
            # Only refresh if cache didn't have status (fallback)
            if not cached_state or 'status' not in cached_state:
                game.refresh_from_db()
                print(f"Game {game_id}: Status = {game.status}, Winner = {game.winner}")
            
            # Double-check with DB (source of truth)
            if game.status != 'active':
                print(f"Game {game_id}: Not active (status: {game.status}), stopping number calling")
                release_number_calling_lock(game_id)
                return {'error': 'Game is not active', 'stopped': True}
            
            # Check if game has a winner
            if game.winner:
                print(f"Game {game_id}: Already has winner ({game.winner}), stopping number calling")
                release_number_calling_lock(game_id)
                return {'error': 'Game already has winner', 'stopped': True}
            
            from .models import GameSettings
            # Use cached settings from game start to prevent mid-game changes
            settings = GameSettings.get_settings(game_id=game_id)
            time_between_calls = settings.time_between_calls or 3  # Default to 3 seconds
            
            # Get current called numbers
            called_numbers = list(CalledNumber.objects.filter(game=game).values_list('number', flat=True))
            
            # If this is the first call, schedule the actual first number call with 3-second delay
            # CRITICAL FIX: Use Celery countdown instead of time.sleep() to avoid blocking worker
            # But we need to actually call the number, not just reschedule
            if len(called_numbers) == 0:
                release_number_calling_lock(game_id)
                # Schedule first number call with 3-second delay (matches frontend countdown)
                task_call_first_number.apply_async(args=[game_id], countdown=3)
                return {'success': True, 'scheduled_first_call': True, 'delay': 3}
            
            available_numbers = list(range(1, 76))
            remaining = [n for n in available_numbers if n not in called_numbers]
            
            if not remaining:
                # All numbers called, schedule check after 5 seconds for BINGO claims
                # CRITICAL FIX: Use Celery countdown instead of time.sleep() to avoid blocking worker
                release_number_calling_lock(game_id)
                # Schedule final check after 5 seconds
                task_check_all_numbers_called.apply_async(args=[game_id], countdown=5)
                return {'success': True, 'all_numbers_called': True, 'checking_for_winners': True}
                
                # PHASE 4 OPTIMIZATION: Check game state from Redis cache first
                cached_state = get_game_state_from_redis(game_id)
                if cached_state and 'status' in cached_state:
                    if cached_state['status'] != 'active' or cached_state.get('winner_id'):
                        # Game completed or has winner, no need to refresh
                        release_number_calling_lock(game_id)
                        return {'success': True, 'message': 'All numbers called, game completed', 'stopped': True}
                
                # Refresh from DB to verify
                game.refresh_from_db()
                if game.status == 'active' and not game.winner:
                    # No winner, end the game
                    game.status = 'completed'
                    game.completed_at = timezone.now()
                    game.save()
                    
                    # PHASE 4 OPTIMIZATION: Sync game state to Redis immediately
                    from .redis_utils import sync_game_state_to_redis, invalidate_game_state_cache
                    sync_game_state_to_redis(game)
                    
                    # Cleanup Redis keys for this game
                    from .redis_utils import cleanup_game_redis_keys
                    cleanup_game_redis_keys(game.id)
                    
                    # Invalidate cache
                    cache.delete('game:current')
                    
                    try:
                        broadcast_to_game_rooms(game.id, 'game_ended', {
                            'game_id': game.id,
                            'no_winner': True
                        })
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
                    # No safe number (every remaining number would let a real user win) - skip this round
                    release_number_calling_lock(game_id)
                    task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
                    return {'success': True, 'skipped': True, 'reason': 'No safe number (skip real-user-winning numbers)'}
            else:
                # Free play or no fake users - use random selection
                number = random.choice(remaining)
            
            # Call the number directly (we're already in a background task)
            # CRITICAL: We have the lock, so only one instance can call a number at a time
            # CRITICAL: time_between_calls is already fetched from cached settings above
            try:
                # Double-check that number hasn't been called by another instance (race condition protection)
                # Note: We still need DB check for called numbers (not cached in game state)
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
                # PHASE 4 OPTIMIZATION: Get call_count from Redis cache (faster than DB refresh)
                cached_state = get_game_state_from_redis(game_id)
                if cached_state and 'call_count' in cached_state:
                    call_count = cached_state['call_count']
                else:
                    # Cache miss, refresh from DB
                    game.refresh_from_db()
                    call_count = game.current_call_count
                
                # Broadcast number called FIRST (players + watchers rooms)
                try:
                    broadcast_to_game_rooms(game.id, 'number_called', {
                        'number': called_number.number,
                        'letter': called_number.letter,
                        'call_count': call_count
                    })
                except Exception as e:
                    print(f"WebSocket broadcast error in auto_call_numbers (number_called): {e}")
                
                # OPTIMIZATION #1: Batch mark number on fake user cards
                # This replaces individual save() calls with a single bulk_update()
                from .fake_user_manager import batch_mark_number_on_fake_cards
                # CalledNumber is already imported at the top of the file
                
                # CRITICAL FIX: Check if game already has a winner (real user) BEFORE processing fake cards
                # This prevents fake users from winning after a real user has already won
                # PHASE 4 OPTIMIZATION: Check game state from Redis cache first
                cached_state = get_game_state_from_redis(game_id)
                if cached_state and 'status' in cached_state:
                    if cached_state['status'] == 'completed' or cached_state.get('winner_id'):
                        print(f"Game {game_id}: Already has winner or is completed (from cache), skipping fake user processing")
                        release_number_calling_lock(game_id)
                        return {'success': True, 'message': 'Game already has winner', 'stopped': True}
                
                # Verify with DB (source of truth)
                game.refresh_from_db()
                if game.status == 'completed' or game.winner:
                    print(f"Game {game_id}: Already has winner or is completed, skipping fake user processing")
                    release_number_calling_lock(game_id)
                    return {'success': True, 'message': 'Game already has winner', 'stopped': True}
                
                # Batch process all fake cards (with error handling)
                try:
                    updated_count, winners = batch_mark_number_on_fake_cards(game.id, number)
                    print(f"Batch processed {updated_count} fake cards for number {number}, found {len(winners)} winners")
                except Exception as e:
                    print(f"ERROR in batch_mark_number_on_fake_cards: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continue with number calling even if fake user processing fails
                    winners = []
                    updated_count = 0
                
                # Redis-only system players: mark number and check bingo (no DB, no payout)
                from .fake_user_manager import batch_mark_number_on_system_players_redis
                from .redis_utils import set_game_winner_system_sentinel
                try:
                    redis_updated, redis_winners = batch_mark_number_on_system_players_redis(game_id, number)
                    if redis_updated:
                        print(f"Marked number {number} on {redis_updated} Redis system players")
                    if redis_winners:
                        print(f"Redis system player(s) bingo: {[w.get('name') for w in redis_winners]}")
                        set_game_winner_system_sentinel(game_id)
                        release_number_calling_lock(game_id)
                        task_finalize_redis_system_winner.delay(game_id, redis_winners[0])
                        return {'success': True, 'redis_system_winner': True, 'stopped': True}
                except Exception as e:
                    print(f"ERROR in batch_mark_number_on_system_players_redis: {e}")
                
                # CRITICAL FIX: Check again if game has a winner after processing fake cards
                # A real user might have won while we were processing fake cards
                # PHASE 4 OPTIMIZATION: Check game state from Redis cache first
                cached_state = get_game_state_from_redis(game_id)
                if cached_state and 'status' in cached_state:
                    if cached_state['status'] == 'completed' or cached_state.get('winner_id'):
                        print(f"Game {game_id}: Winner found after processing fake cards (from cache), stopping")
                        release_number_calling_lock(game_id)
                        return {'success': True, 'message': 'Game has winner', 'stopped': True}
                
                # Verify with DB
                game.refresh_from_db()
                if game.status == 'completed' or game.winner:
                    print(f"Game {game_id}: Winner found after processing fake cards, stopping")
                    release_number_calling_lock(game_id)
                    return {'success': True, 'message': 'Game has winner', 'stopped': True}
                
                # Process any winners found (only if no real winner exists)
                # CRITICAL: Fake users are PASSIVE - they call the unified claim function, not directly end games
                if winners:
                    # Get the first winner (if multiple, process the first one)
                    fake_card, pattern = winners[0]
                    
                    # CRITICAL: Refresh card from database to ensure we have latest state
                    # The card object from batch_mark_number_on_fake_cards might have stale data
                    from .models import FakeUserGameCard
                    fake_card = FakeUserGameCard.objects.get(id=fake_card.id)
                    
                    # Double-check card is not already a winner (another process might have claimed it)
                    if fake_card.is_winner:
                        print(f"Fake user {fake_card.fake_user.name} (card {fake_card.card_number}) already won - skipping")
                        release_number_calling_lock(game_id)
                        # Reschedule for next call
                        task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
                        return {'success': True, 'card_already_won': True}
                    
                    # CRITICAL: Use unified claim function - this is the SINGLE AUTHORITY for bingo claims
                    # Fake users are treated as passive event responders, not game controllers
                    from .game_logic import claim_bingo_unified
                    
                    print(f"Fake user {fake_card.fake_user.name} (card {fake_card.card_number}) has bingo - scheduling claim after 2 seconds")
                    
                    # CRITICAL FIX: Use Celery countdown instead of time.sleep() to avoid blocking worker
                    # Schedule fake user claim after 2-second delay (gives real users time to claim first)
                    release_number_calling_lock(game_id)
                    task_process_fake_user_claim.apply_async(args=[game_id, fake_card.id], countdown=2)
                    # Schedule next number call
                    task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
                    return {'success': True, 'fake_winner_scheduled': True, 'fake_card_id': fake_card.id}
                    
                    # Double-check game is still active after delay (real user might have claimed)
                    # PHASE 4 OPTIMIZATION: Check game state from Redis cache first
                    cached_state = get_game_state_from_redis(game_id)
                    if cached_state and 'status' in cached_state:
                        if cached_state['status'] != 'active' or cached_state.get('winner_id'):
                            print(f"Game {game_id}: Already completed or has winner after delay (from cache), skipping fake user claim")
                            release_number_calling_lock(game_id)
                            task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
                            return {'success': True, 'game_completed_during_delay': True}
                    
                    # Verify with DB
                    game.refresh_from_db()
                    if game.status != 'active' or game.winner:
                        print(f"Game {game_id}: Already completed or has winner after delay, skipping fake user claim")
                        release_number_calling_lock(game_id)
                        # Reschedule for next call
                        task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
                        return {'success': True, 'game_completed_during_delay': True}
                    
                    # Double-check card is still not a winner (another process might have claimed it during delay)
                    fake_card.refresh_from_db()
                    if fake_card.is_winner:
                        print(f"Fake user {fake_card.fake_user.name} (card {fake_card.card_number}) already won during delay - skipping")
                        release_number_calling_lock(game_id)
                        # Reschedule for next call
                        task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
                        return {'success': True, 'card_already_won_during_delay': True}
                    
                    print(f"Fake user {fake_card.fake_user.name} (card {fake_card.card_number}) claiming bingo after 2-second delay")
                    
                    # Call unified function for fake user
                    success, winning_pattern, error_message = claim_bingo_unified(fake_card, game, is_fake_user=True)
                    
                    if success:
                        print(f"SUCCESS: Fake user {fake_card.fake_user.name} claimed bingo successfully")
                        # Game is now completed by unified function - stop calling numbers
                        release_number_calling_lock(game_id)
                        return {'success': True, 'fake_winner': True, 'stopped': True, 'updated_cards': updated_count}
                    else:
                        # Claim failed (e.g., real user has priority, game already completed, etc.)
                        print(f"Fake user claim failed: {error_message}")
                        # Don't stop - continue calling numbers (real user might claim or another fake user might win)
                        # Just release lock and continue
                        release_number_calling_lock(game_id)
                        # Reschedule for next call
                        task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
                        return {'success': True, 'fake_claim_failed': True, 'reason': error_message}
                
                # CRITICAL FIX: Check game status BEFORE triggering bingo check
                # This prevents race conditions when a real user manually claims bingo
                # PHASE 4 OPTIMIZATION: Check game state from Redis cache first
                cached_state = get_game_state_from_redis(game_id)
                if cached_state and 'status' in cached_state:
                    if cached_state['status'] == 'completed' or cached_state.get('winner_id'):
                        print(f"CRITICAL: Game {game_id}: Game already completed or has winner before bingo check (from cache), stopping immediately")
                        release_number_calling_lock(game_id)
                        return {'success': True, 'number': number, 'stopped': True, 'reason': 'Game already completed'}
                
                # Verify with DB
                game.refresh_from_db()
                print(f"CRITICAL task_auto_call_numbers: Before bingo check - Game {game_id} status={game.status}, winner={game.winner}")
                if game.status == 'completed' or game.winner:
                    print(f"CRITICAL: Game {game_id}: Game already completed or has winner before bingo check, stopping immediately")
                    release_number_calling_lock(game_id)
                    return {'success': True, 'number': number, 'stopped': True, 'reason': 'Game already completed'}
                
                # Check all real user cards for bingo after calling number
                # Only trigger if game is still active (real user might have just won manually)
                task_check_bingo_for_all_cards.delay(game_id)
                
                # CRITICAL FIX: Check if game was completed by a real user after calling number
                # Schedule a check after 0.5 seconds to allow bingo checking task to process
                # CRITICAL FIX: Use Celery countdown instead of time.sleep() to avoid blocking worker
                release_number_calling_lock(game_id)
                task_check_game_status_after_number.apply_async(args=[game_id, number], countdown=0.5)
                return {'success': True, 'number': number, 'status_check_scheduled': True}
                
                # PHASE 4 OPTIMIZATION: Check game state from Redis cache first
                cached_state = get_game_state_from_redis(game_id)
                if cached_state and 'status' in cached_state:
                    if cached_state['status'] == 'completed' or cached_state.get('winner_id'):
                        print(f"Game {game_id}: Game completed or has winner after calling number {number} (from cache), stopping number calling")
                        release_number_calling_lock(game_id)
                        return {'success': True, 'number': number, 'stopped': True, 'reason': 'Game completed'}
                
                # Verify with DB
                game.refresh_from_db()
                
                # If game is now completed or has a winner, stop calling numbers immediately
                if game.status == 'completed' or game.winner:
                    print(f"Game {game_id}: Game completed or has winner after calling number {number}, stopping number calling")
                    release_number_calling_lock(game_id)
                    return {'success': True, 'number': number, 'stopped': True, 'reason': 'Game completed'}
            except Exception as e:
                print(f"Error calling number {number} in auto_call_numbers: {e}")
                release_number_calling_lock(game_id)
                # If error, retry the task after delay
                if self.request.retries < self.max_retries:
                    raise self.retry(exc=e, countdown=time_between_calls)
                return {'error': f'Failed to call number after retries: {str(e)}'}
            
            # CRITICAL FIX: Double-check game status before scheduling next call
            # This prevents scheduling calls after game has ended
            # PHASE 4 OPTIMIZATION: Check game state from Redis cache first
            cached_state = get_game_state_from_redis(game_id)
            if cached_state and 'status' in cached_state:
                if cached_state['status'] != 'active' or cached_state.get('winner_id'):
                    print(f"Game {game_id}: Game status changed to {cached_state['status']} or has winner (from cache), stopping number calling")
                    release_number_calling_lock(game_id)
                    return {'success': True, 'stopped': True, 'reason': 'Game ended'}
            
            # Verify with DB
            game.refresh_from_db()
            if game.status != 'active' or game.winner:
                print(f"Game {game_id}: Game status changed to {game.status} or has winner, stopping number calling")
                release_number_calling_lock(game_id)
                return {'success': True, 'stopped': True, 'reason': 'Game ended'}
            
            # Release lock before scheduling next call
            release_number_calling_lock(game_id)
            
            # Schedule next call recursively (this prevents long-running tasks)
            # Wait according to settings before next call
            print(f"Game {game_id}: Number {number} called successfully. Scheduling next call in {time_between_calls} seconds.")
            task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
            
            return {'success': True, 'number': number, 'scheduled_next': True, 'next_call_in': time_between_calls}
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


@shared_task(bind=True, max_retries=2, queue='gameplay')
def task_call_first_number(self, game_id: int):
    """
    Call the first number after initial 3-second delay.
    CRITICAL FIX: Separate task to handle first call delay without blocking worker.
    This prevents infinite loop where task_auto_call_numbers keeps rescheduling itself.
    """
    try:
        from .redis_utils import acquire_number_calling_lock, release_number_calling_lock, get_game_state_from_redis
        from .models import GameSettings
        
        # Check game state from Redis cache first
        cached_state = get_game_state_from_redis(game_id)
        if cached_state and 'status' in cached_state:
            if cached_state['status'] != 'active':
                return {'error': 'Game is not active', 'stopped': True}
            if cached_state.get('winner_id'):
                return {'error': 'Game already has winner', 'stopped': True}
        
        # Get game
        game = Game.objects.get(id=game_id)
        if game.status != 'active' or game.winner:
            return {'error': 'Game is not active or has winner', 'stopped': True}
        
        # Check if numbers already called (another process might have started)
        called_numbers = list(CalledNumber.objects.filter(game=game).values_list('number', flat=True))
        if len(called_numbers) > 0:
            # Numbers already being called, just continue with normal flow
            settings = GameSettings.get_settings(game_id=game_id)
            time_between_calls = settings.time_between_calls or 3
            task_auto_call_numbers.apply_async(args=[game_id], countdown=time_between_calls)
            return {'success': True, 'already_started': True}
        
        # Acquire lock and call first number
        if not acquire_number_calling_lock(game_id, timeout=30):
            # Lock held, reschedule
            settings = GameSettings.get_settings(game_id=game_id)
            time_between_calls = settings.time_between_calls or 3
            task_auto_call_numbers.apply_async(args=[game_id], countdown=1)
            return {'success': True, 'lock_held': True}
        
        try:
            # Call first number - use normal number calling logic
            from .fake_user_manager import get_safe_number_to_call
            import random
            
            available_numbers = list(range(1, 76))
            number = random.choice(available_numbers)
            
            # Double-check number not called (shouldn't happen, but safety check)
            if CalledNumber.objects.filter(game=game, number=number).exists():
                # Pick another number
                remaining = [n for n in available_numbers if n not in [number]]
                if remaining:
                    number = random.choice(remaining)
                else:
                    release_number_calling_lock(game_id)
                    return {'error': 'All numbers already called'}
            
            # Call the number
            called_number = call_number(game, number)
            
            # Get call count from cache or DB
            cached_state = get_game_state_from_redis(game_id)
            if cached_state and 'call_count' in cached_state:
                call_count = cached_state['call_count']
            else:
                game.refresh_from_db()
                call_count = game.current_call_count
            
            # Broadcast number called (players + watchers rooms)
            try:
                broadcast_to_game_rooms(game.id, 'number_called', {
                    'number': called_number.number,
                    'letter': called_number.letter,
                    'call_count': call_count
                })
            except Exception as e:
                print(f"WebSocket broadcast error: {e}")
            
            # Trigger fake card processing (non-blocking, separate task)
            from .fake_user_manager import batch_mark_number_on_fake_cards, batch_mark_number_on_system_players_redis
            from .redis_utils import set_game_winner_system_sentinel
            try:
                updated_count, winners = batch_mark_number_on_fake_cards(game.id, number)
                print(f"Batch processed {updated_count} fake cards for number {number}, found {len(winners)} winners")
                
                # Process fake winners if any (but don't block)
                if winners:
                    fake_card, pattern = winners[0]
                    from .models import FakeUserGameCard
                    fake_card = FakeUserGameCard.objects.get(id=fake_card.id)
                    if not fake_card.is_winner:
                        # Schedule fake user claim after 2-second delay
                        task_process_fake_user_claim.apply_async(args=[game_id, fake_card.id], countdown=2)
            except Exception as e:
                print(f"ERROR in batch_mark_number_on_fake_cards: {e}")
            
            # Redis-only system players: mark and check bingo (no DB, no payout)
            try:
                redis_updated, redis_winners = batch_mark_number_on_system_players_redis(game_id, number)
                if redis_winners:
                    set_game_winner_system_sentinel(game_id)
                    task_finalize_redis_system_winner.delay(game_id, redis_winners[0])
                    release_number_calling_lock(game_id)
                    return {'success': True, 'number': number, 'first_call': True, 'redis_system_winner': True}
            except Exception as e:
                print(f"ERROR in batch_mark_number_on_system_players_redis: {e}")
            
            # Trigger bingo check (non-blocking)
            task_check_bingo_for_all_cards.delay(game_id)
            
            # Release lock
            release_number_calling_lock(game_id)
            
            # Schedule next call
            settings = GameSettings.get_settings(game_id=game_id)
            time_between_calls = settings.time_between_calls or 3
            
            # Schedule status check after 0.5 seconds, which will schedule next call if game still active
            task_check_game_status_after_number.apply_async(args=[game_id, number], countdown=0.5)
            
            return {'success': True, 'number': number, 'first_call': True, 'next_scheduled': True}
        finally:
            release_number_calling_lock(game_id)
    except Exception as e:
        print(f"Error in task_call_first_number: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


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
        
        # Broadcast card selection (players + watchers rooms)
        try:
            from .game_logic import get_available_card_numbers
            broadcast_to_game_rooms(game.id, 'card_selected', {
                'card_number': card_number,
                'user_id': user.id,
                'username': user.username,
                'available_cards': get_available_card_numbers(game)
            })
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
            amt = refund_data['amount']
            if user.has_withdrawable_active():
                User.objects.filter(id=user.id).update(withdrawable_balance=F('withdrawable_balance') + amt)
            else:
                User.objects.filter(id=user.id).update(unwithdrawable_balance=F('unwithdrawable_balance') + amt)
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


@shared_task(bind=True)
def task_cancel_game(self, game_id: int):
    """
    Background task to cancel a game (without refund).
    This is called after a delay when admin cancels game without refund.
    """
    try:
        from .models import Game, GameSettings, AdminMessage
        
        game = Game.objects.get(id=game_id)
        old_game_id = game_id  # Store for WebSocket broadcast
        
        # Get admin message if it exists
        admin_message = AdminMessage.objects.filter(game=game).order_by('-created_at').first()
        
        # Update admin_message first before deleting the game
        if admin_message:
            admin_message.cancel_processed = True
            admin_message.save()
        
        # Get settings for new game
        settings = GameSettings.get_settings()
        
        # Delete the game (this will cascade delete related objects like GameCards, AdminMessage, etc.)
        game.delete()
        
        # CRITICAL: Use game creation lock to prevent multiple games
        from .redis_utils import acquire_game_creation_lock, release_game_creation_lock
        
        if not acquire_game_creation_lock(timeout=15):
            print("CRITICAL: Game creation lock already held - checking for existing game")
            existing_game = Game.objects.filter(status__in=['waiting', 'active']).first()
            if existing_game:
                new_game = existing_game
            else:
                # Wait a bit and check again
                import time
                time.sleep(0.5)
                existing_game = Game.objects.filter(status__in=['waiting', 'active']).first()
                if existing_game:
                    new_game = existing_game
                else:
                    # No game exists, create one (but this shouldn't happen if lock is held)
                    print("WARNING: Lock held but no game found - creating anyway")
                    new_game = Game.objects.create(
                        status='waiting',
                        bet_amount=settings.bid_amount,
                        derash_amount=Decimal('0.00')
                    )
        else:
            try:
                # Check if game already exists
                existing_game = Game.objects.filter(status__in=['waiting', 'active']).first()
                if existing_game:
                    new_game = existing_game
                else:
                    # Create new game
                    new_game = Game.objects.create(
                        status='waiting',
                        bet_amount=settings.bid_amount,
                        derash_amount=Decimal('0.00')
                    )
            finally:
                release_game_creation_lock()
        
        # Broadcast game cancelled (players + watchers rooms)
        try:
            broadcast_to_game_rooms(old_game_id, 'game_cancelled', {
                'message': 'Game has been cancelled. Please select a new card.',
                'new_game_id': new_game.id
            })
        except Exception as e:
            print(f"WebSocket broadcast error: {e}")
        
        return {
            'success': True,
            'game_cancelled': True,
            'new_game_id': new_game.id
        }
    except Game.DoesNotExist:
        return {'error': 'Game not found'}
    except Exception as e:
        print(f"Error in task_cancel_game: {e}")
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
        
        try:
            card = create_fake_user_card(game, fake_user, card_number)
            
            # Broadcast card selection via WebSocket
            try:
                from .game_logic import get_available_card_numbers
                broadcast_to_game_rooms(game.id, 'card_selected', {
                    'card_number': card_number,
                    'user_id': None,  # Fake user
                    'username': fake_user.name,
                    'is_fake': True,
                    'available_cards': get_available_card_numbers(game)
                })
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
    Simulate fake user card selections in batches every 2 seconds
    - Select random amount of fake users
    - Show them selecting in batches every 2 seconds
    - Leave 5 seconds at the end for state management
    - No unselection - once selected, remain selected
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
        
        # Get timer from settings
        from .models import GameSettings
        settings = GameSettings.get_settings()
        timer_seconds = settings.card_selection_timer
        
        # Reserve 5 seconds at the end for state management
        # Use first 2 seconds to randomly choose which fake users will select
        available_time = timer_seconds - 5  # Leave 5 seconds buffer
        selection_window = available_time - 2  # First 2 seconds for planning
        
        if selection_window <= 0:
            return {'error': 'Timer too short for simulation', 'stopped': True}
        
        # Randomly select which fake users will participate (random amount)
        fake_users_list = list(fake_users)
        num_fake_users = len(fake_users_list)
        
        # Randomly choose how many will select (at least 1, at most all)
        num_to_select = random.randint(1, num_fake_users)
        selected_fake_users = random.sample(fake_users_list, num_to_select)
        
        if num_to_select == 0:
            return {'error': 'No fake users to schedule', 'stopped': True}
        
        # Calculate how many users per batch (every 2 seconds)
        # We have selection_window seconds, batches every 2 seconds
        num_batches = max(1, int(selection_window / 2))
        users_per_batch = max(1, int(num_to_select / num_batches))
        
        # Distribute users across batches
        # Make sure we don't miss any users due to rounding
        batches = []
        remaining_users = selected_fake_users.copy()
        
        for batch_idx in range(num_batches):
            if not remaining_users:
                break
            
            # Calculate how many users in this batch
            if batch_idx == num_batches - 1:
                # Last batch gets all remaining users
                batch_users = remaining_users
            else:
                # Distribute evenly, but ensure we don't miss any
                batch_size = min(users_per_batch, len(remaining_users))
                batch_users = remaining_users[:batch_size]
                remaining_users = remaining_users[batch_size:]
            
            if batch_users:
                batches.append(batch_users)
        
        # Schedule batches every 2 seconds (starting after 2 seconds for planning)
        for batch_idx, batch_users in enumerate(batches):
            # Delay: 2 seconds (planning) + (batch_idx * 2 seconds)
            delay = 2 + (batch_idx * 2)
            
            # Schedule each user in the batch at the same time (with tiny random offset for realism)
            for fake_user in batch_users:
                # Tiny random offset (0-0.1 seconds) to make it look more natural
                user_delay = delay + random.uniform(0.0, 0.1)
                
                task_select_fake_card_once.apply_async(
                    args=[game_id, fake_user.id],
                    countdown=user_delay
                )
        
        return {
            'success': True,
            'scheduled_count': num_to_select,
            'batches': len(batches),
            'message': f'Scheduled {num_to_select} fake user selections in {len(batches)} batches'
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
        
        # Prefer cards from 1-100 range (70% chance) for more realistic selection
        preferred_cards = [c for c in available_cards if c <= 100]
        other_cards = [c for c in available_cards if c > 100]
        
        if preferred_cards and random.random() < 0.7:
            # 70% chance to pick from preferred range (1-100)
            card_number = random.choice(preferred_cards)
        elif preferred_cards:
            # 30% chance to pick from preferred if available
            card_number = random.choice(preferred_cards)
        elif other_cards:
            # Fallback to other cards if preferred is empty
            card_number = random.choice(other_cards)
        else:
            # Last resort - any available card
            card_number = random.choice(available_cards)
        
        try:
            # Check if fake user already has a card (from previous change)
            existing_card = FakeUserGameCard.objects.filter(game=game, fake_user=fake_user).first()
            if existing_card:
                # Unselect previous card (simulate user changing card)
                old_card_number = existing_card.card_number
                existing_card.delete()
                
                # Broadcast unselection immediately
                try:
                    broadcast_to_game_rooms(game.id, 'card_selected', {
                        'card_number': None,  # Indicates unselection
                        'user_id': None,
                        'username': fake_user.name,
                        'is_fake': True,
                        'available_cards': get_available_card_numbers(game)
                    })
                except Exception as e:
                    print(f"WebSocket broadcast error for fake user unselection: {e}")
                
                # IMPORTANT: Immediately select new card (no delay) to keep synchronized
                # This ensures for every unselect, there's a new select right away
                # Get fresh available cards after unselection
                available_cards = get_available_card_numbers_for_fake(game)
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
                else:
                    # No cards available, return error
                    return {'error': 'No available cards after unselection', 'stopped': True}
            
            # Create new card (this handles both initial selection and reselection after unselect)
            card = create_fake_user_card(game, fake_user, card_number)
            
            # Broadcast card selection immediately
            try:
                broadcast_to_game_rooms(game.id, 'card_selected', {
                    'card_number': card_number,
                    'user_id': None,  # Fake user
                    'username': fake_user.name,
                    'is_fake': True,
                    'available_cards': get_available_card_numbers(game)
                })
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
                    # Broadcast selection (players + watchers rooms)
                    try:
                        broadcast_to_game_rooms(game.id, 'card_selected', {
                            'card_number': card_number,
                            'user_id': None,
                            'username': fake_user.name,
                            'is_fake': True,
                            'available_cards': get_available_card_numbers(game)
                        })
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


@shared_task(bind=True, max_retries=3)
def task_select_fake_card_once(self, game_id: int, fake_user_id: int):
    """
    Select a card for a fake user once - no unselection, no changes
    Once selected, the card remains selected
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
        
        # Check if fake user already has a card - if so, don't select again
        existing_card = FakeUserGameCard.objects.filter(game=game, fake_user=fake_user).first()
        if existing_card:
            # Already has a card, return success (no unselection)
            return {
                'success': True,
                'fake_user_id': fake_user_id,
                'fake_user_name': fake_user.name,
                'card_number': existing_card.card_number,
                'message': 'Fake user already has a card'
            }
        
        # Get available cards (excluding real user cards and other fake user cards)
        # Check available cards right before selection to handle real users taking cards
        available_cards = get_available_card_numbers_for_fake(game)
        if not available_cards:
            return {'error': 'No available cards', 'stopped': True}
        
        # Prefer cards from 1-100 range (70% chance) for more realistic selection
        preferred_cards = [c for c in available_cards if c <= 100]
        other_cards = [c for c in available_cards if c > 100]
        
        if preferred_cards and random.random() < 0.7:
            # 70% chance to pick from preferred range (1-100)
            card_number = random.choice(preferred_cards)
        elif preferred_cards:
            # 30% chance to pick from preferred if available
            card_number = random.choice(preferred_cards)
        elif other_cards:
            # Fallback to other cards if preferred is empty
            card_number = random.choice(other_cards)
        else:
            # Last resort - any available card
            card_number = random.choice(available_cards)
        
        try:
            # Create card (will raise ValueError if card is taken)
            card = create_fake_user_card(game, fake_user, card_number)
            
            # Broadcast card selection immediately
            try:
                broadcast_to_game_rooms(game.id, 'card_selected', {
                    'card_number': card_number,
                    'user_id': None,  # Fake user
                    'username': fake_user.name,
                    'is_fake': True,
                    'available_cards': get_available_card_numbers(game)
                })
            except Exception as e:
                print(f"WebSocket broadcast error for fake user card: {e}")
            
            # Recalculate derash after card selection to ensure it includes all fake users
            game.refresh_from_db()
            game.recalculate_derash()
            game.refresh_from_db()  # Refresh again to get updated derash
            
            return {
                'success': True,
                'fake_user_id': fake_user_id,
                'fake_user_name': fake_user.name,
                'card_number': card_number
            }
        except ValueError as e:
            # Card was taken by real user or another fake user, try another if available
            # Get fresh available cards
            available_cards = get_available_card_numbers_for_fake(game)
            if card_number in available_cards:
                available_cards.remove(card_number)
            
            if available_cards:
                # Try another card
                card_number = random.choice(available_cards)
                try:
                    card = create_fake_user_card(game, fake_user, card_number)
                    # Broadcast selection
                    try:
                        broadcast_to_game_rooms(game.id, 'card_selected', {
                            'card_number': card_number,
                            'user_id': None,
                            'username': fake_user.name,
                            'is_fake': True,
                            'available_cards': get_available_card_numbers(game)
                        })
                    except Exception as e:
                        print(f"WebSocket broadcast error: {e}")
                    
                    game.refresh_from_db()
                    game.recalculate_derash()
                    
                    return {
                        'success': True,
                        'fake_user_id': fake_user_id,
                        'card_number': card_number
                    }
                except ValueError:
                    # Card taken again, return error
                    return {'error': 'Card taken by another user', 'stopped': True}
            else:
                return {'error': 'No available cards after card taken', 'stopped': True}
    except (Game.DoesNotExist, FakeUser.DoesNotExist) as e:
        return {'error': f'Game or fake user not found: {str(e)}', 'stopped': True}
    except Exception as e:
        print(f"Error in task_select_fake_card_once: {e}")
        import traceback
        traceback.print_exc()
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=5)
        return {'error': str(e), 'stopped': True}


@shared_task(bind=True, max_retries=2, queue='gameplay')
def task_check_all_numbers_called(self, game_id: int):
    """
    Check if all numbers are called and handle game completion.
    This is scheduled after all numbers are called to give time for BINGO claims.
    CRITICAL FIX: Separate task to avoid blocking number calling.
    """
    try:
        from .redis_utils import get_game_state_from_redis
        game = Game.objects.get(id=game_id)
        
        # Check game state from Redis cache first
        cached_state = get_game_state_from_redis(game_id)
        if cached_state and 'status' in cached_state:
            if cached_state['status'] != 'active' or cached_state.get('winner_id'):
                # Game completed or has winner, no need to refresh
                return {'success': True, 'message': 'Game already completed or has winner', 'stopped': True}
        
        # Refresh from DB to verify
        game.refresh_from_db()
        if game.status == 'active' and not game.winner:
            # No winner, end the game
            game.status = 'completed'
            game.completed_at = timezone.now()
            game.save()
            
            # Sync game state to Redis immediately
            from .redis_utils import sync_game_state_to_redis, cleanup_game_redis_keys
            sync_game_state_to_redis(game)
            cleanup_game_redis_keys(game.id)
            
            # Invalidate cache
            cache.delete('game:current')
            
            # Broadcast game ended (players + watchers rooms)
            try:
                broadcast_to_game_rooms(game.id, 'game_ended', {
                    'game_id': game.id,
                    'no_winner': True
                })
            except Exception as e:
                print(f"WebSocket broadcast error: {e}")
        
        return {'success': True, 'message': 'All numbers called check completed'}
    except Exception as e:
        print(f"Error in task_check_all_numbers_called: {e}")
        return {'error': str(e)}


@shared_task(bind=True, max_retries=2, queue='gameplay')
def task_process_fake_user_claim(self, game_id: int, fake_card_id: int):
    """
    Process fake user bingo claim after delay.
    CRITICAL FIX: Check for real user winners before claiming - if real users claimed during the 3-second delay,
    include them as multiple winners and process all together.
    """
    try:
        from .models import FakeUserGameCard, GameCard
        from .redis_utils import get_game_state_from_redis, get_bingo_winners
        from .game_logic import claim_bingo_unified
        
        # Check game state from Redis cache first
        cached_state = get_game_state_from_redis(game_id)
        if cached_state and 'status' in cached_state:
            if cached_state['status'] != 'active' or cached_state.get('winner_id'):
                print(f"Game {game_id}: Already completed or has winner (from cache), skipping fake user claim")
                return {'success': True, 'game_completed_during_delay': True}
        
        # Verify with DB
        game = Game.objects.get(id=game_id)
        game.refresh_from_db()
        
        # CRITICAL FIX: Check if game is already completed (real user might have won during 3-second delay)
        if game.status == 'completed':
            print(f"Game {game_id}: Already completed (real user likely won during delay), checking for multiple winners...")
            # Check if there are real winners in Redis
            redis_winners = get_bingo_winners(game_id)
            if redis_winners:
                real_winners = [w for w in redis_winners if w.get('user_id') is not None]
                if real_winners:
                    print(f"Game {game_id}: Real user(s) already won. Fake user will be included in multiple winners processing.")
                    # The game is already completed, but we should still add fake user to winners if valid
                    # However, since game is completed, claim_bingo_unified will reject it
                    # So we need to check if fake user should be added to existing winners
                    fake_card = FakeUserGameCard.objects.get(id=fake_card_id)
                    fake_card.refresh_from_db()
                    if not fake_card.is_winner:
                        # Fake user hasn't been marked as winner yet, but real user won
                        # This means real user won first, so fake user doesn't get to claim
                        print(f"Game {game_id}: Real user won first, fake user {fake_card.fake_user.name} claim rejected")
                        return {'success': True, 'real_user_won_first': True}
            return {'success': True, 'game_completed_during_delay': True}
        
        if game.status != 'active':
            print(f"Game {game_id}: Not active (status: {game.status}), skipping fake user claim")
            return {'success': True, 'game_not_active': True}
        
        # CRITICAL FIX: Check if any real users have claimed bingo during the 3-second delay
        # This handles the race condition where real user clicks bingo while fake user is waiting
        redis_winners = get_bingo_winners(game_id)
        real_winners_in_redis = [w for w in redis_winners] if redis_winners else []
        real_winner_cards = []
        
        if real_winners_in_redis:
            # Check if any are real users (user_id is not None)
            real_winner_ids = [w['card_id'] for w in real_winners_in_redis if w.get('user_id') is not None]
            if real_winner_ids:
                # Real users have claimed! Get their cards
                real_winner_cards = list(GameCard.objects.filter(
                    id__in=real_winner_ids,
                    game=game
                ).select_related('user'))
                print(f"Game {game_id}: Found {len(real_winner_cards)} real user winner(s) in Redis during fake user delay")
        
        # Get fake card
        fake_card = FakeUserGameCard.objects.get(id=fake_card_id)
        
        # Double-check card is not already a winner
        fake_card.refresh_from_db()
        if fake_card.is_winner:
            print(f"Fake user {fake_card.fake_user.name} (card {fake_card.card_number}) already won - skipping")
            return {'success': True, 'card_already_won': True}
        
        # CRITICAL FIX: If real users have claimed, add fake user to winners and process all together
        if real_winner_cards:
            print(f"Game {game_id}: Real user(s) claimed during delay. Adding fake user {fake_card.fake_user.name} and processing all winners together...")
            
            # Validate fake user's bingo before adding
            from .redis_utils import get_called_numbers_from_redis
            from .fake_user_manager import check_fake_user_bingo
            called_numbers = get_called_numbers_from_redis(game_id)
            if called_numbers:
                called_set = set(called_numbers)
                has_bingo, winning_pattern = check_fake_user_bingo(fake_card, called_set, game)
                
                if has_bingo:
                    # Fake user has valid bingo - add to winners and process all together
                    from .redis_utils import add_bingo_winner
                    add_bingo_winner(game_id, fake_card.id, user_id=None)  # None for fake users
                    
                    # Mark fake card as winner
                    fake_card.is_winner = True
                    fake_card.winning_pattern = winning_pattern
                    fake_card.claimed_at = timezone.now()
                    fake_card.save()
                    
                    print(f"Game {game_id}: Added fake user {fake_card.fake_user.name} to winners. Processing all {len(real_winner_cards) + 1} winners together...")
                    
                    # Process all winners together (real + fake)
                    # This will handle prize splitting correctly (only real users get prizes)
                    task_process_bingo_winners.delay(game_id)
                    
                    return {'success': True, 'multiple_winners': True, 'real_count': len(real_winner_cards), 'fake_count': 1}
                else:
                    print(f"Game {game_id}: Fake user {fake_card.fake_user.name} doesn't have valid bingo, skipping")
                    return {'success': True, 'fake_no_bingo': True}
            else:
                print(f"Game {game_id}: No called numbers found, cannot validate fake user bingo")
                return {'success': True, 'no_called_numbers': True}
        else:
            # No real winners - proceed with normal fake user claim
            print(f"Game {game_id}: No real winners found. Fake user {fake_card.fake_user.name} (card {fake_card.card_number}) claiming bingo after delay")
            
            # Call unified function for fake user
            success, winning_pattern, error_message = claim_bingo_unified(fake_card, game, is_fake_user=True)
            
            if success:
                print(f"SUCCESS: Fake user {fake_card.fake_user.name} claimed bingo successfully")
                return {'success': True, 'fake_winner': True, 'stopped': True}
            else:
                print(f"Fake user claim failed: {error_message}")
                return {'success': True, 'fake_claim_failed': True, 'reason': error_message}
    except Exception as e:
        print(f"Error in task_process_fake_user_claim: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


@shared_task(bind=True, max_retries=2, queue='gameplay', name='api.tasks.task_call_next_number')
def task_call_next_number(self, game_id: int):
    """
    EVENT-DRIVEN NUMBER CALLING - Redis-first architecture.
    
    This is the NEW freeze-proof number calling task:
    - Redis is source of truth (no DB queries)
    - Fast execution (<200ms)
    - No locks, no sleeps, no blocking
    - Fire-and-forget scheduling
    
    Flow:
    1. Read game state from Redis
    2. If not active or has winner → exit
    3. If first call (no numbers called) → schedule with 3-second delay
    4. Pick next number
    5. Store in Redis
    6. Broadcast via WebSocket
    7. Schedule next call with countdown
    8. Trigger bingo check (separate task)
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"🎯 task_call_next_number STARTED for game {game_id}")
    print(f"🎯 task_call_next_number STARTED for game {game_id}")
    
    try:
        from .redis_utils import (
            get_game_live_state, add_called_number_live,
            get_called_numbers_from_redis
        )
        from .models import GameSettings
        import random
        
        logger.info(f"Game {game_id}: Reading Redis state...")
        # Read game state from Redis (source of truth)
        state = get_game_live_state(game_id)
        logger.info(f"Game {game_id}: Redis state: {state}")
        print(f"Game {game_id}: Redis state: {state}")
        
        # CRITICAL FIX: If state is missing, try to initialize it (resilience)
        if not state or len(state) == 0:
            logger.warning(f"⚠️ [CALL NUMBER] Game {game_id}: Redis state not found, attempting to initialize...")
            print(f"⚠️ [CALL NUMBER] Game {game_id}: Redis state not found, attempting to initialize...")
            
            # Try to get game from DB to check status
            try:
                game = Game.objects.get(id=game_id)
                if game.status == 'active':
                    # Game is active but Redis state missing - try to initialize
                    from .redis_utils import initialize_game_live_state
                    from .models import GameSettings
                    settings = GameSettings.get_settings()
                    call_interval = settings.time_between_calls or 3
                    
                    init_success = initialize_game_live_state(game_id, "active", call_interval)
                    if init_success:
                        # Re-read state
                        state = get_game_live_state(game_id)
                        logger.info(f"✅ [CALL NUMBER] Game {game_id}: Redis state initialized, new state: {state}")
                        print(f"✅ [CALL NUMBER] Game {game_id}: Redis state initialized")
                    else:
                        logger.error(f"❌ [CALL NUMBER] Game {game_id}: Failed to initialize Redis state")
                        print(f"❌ [CALL NUMBER] Game {game_id}: Failed to initialize Redis state")
                        return {'error': 'Game state not found in Redis and initialization failed', 'stopped': True}
                else:
                    # Game is not active - don't initialize, just stop
                    logger.info(f"Game {game_id}: Game status is '{game.status}', not initializing Redis state")
                    return {'error': f'Game is not active (status: {game.status})', 'stopped': True}
            except Game.DoesNotExist:
                logger.error(f"❌ [CALL NUMBER] Game {game_id}: Game not found in database")
                return {'error': 'Game not found', 'stopped': True}
            except Exception as e:
                logger.error(f"❌ [CALL NUMBER] Game {game_id}: Error checking game status: {e}")
                import traceback
                traceback.print_exc()
                return {'error': f'Error checking game: {str(e)}', 'stopped': True}
        
        # Final check - if state is still empty, stop
        if not state or len(state) == 0:
            logger.error(f"❌ [CALL NUMBER] Game {game_id}: Redis state still empty after initialization attempt")
            print(f"❌ ERROR: Game {game_id} live state not found in Redis. Task stopping.")
            return {'error': 'Game state not found in Redis', 'stopped': True}
        
        if state.get('status') != 'active':
            print(f"Game {game_id}: Not active (status: {state.get('status')}), stopping")
            return {'stopped': True, 'reason': f"Game not active (status: {state.get('status')})"}
        
        if state.get('winner_card_id'):
            print(f"Game {game_id}: Already has winner, stopping")
            return {'stopped': True, 'reason': 'Game already has winner'}
        
        # Get called numbers from Redis
        called_numbers = get_called_numbers_from_redis(game_id)
        
        # CRITICAL: If this is the first call (no numbers called yet), proceed immediately
        # The 3-second delay is handled by the initial call from start_game using countdown
        # This task should only be called AFTER the initial delay, so we proceed to call the number
        is_first_call = len(called_numbers) == 0
        if is_first_call:
            logger.info(f"🎯 Game {game_id}: First number call - proceeding immediately (after 3s delay)")
            print(f"🎯 Game {game_id}: First number call - proceeding immediately (after 3s delay)")
            
            # Double-check game is still active before calling first number
            try:
                game = Game.objects.get(id=game_id)
                if game.status != 'active':
                    logger.warning(f"Game {game_id}: Status changed to {game.status} before first call, stopping")
                    return {'error': f'Game status is {game.status}, not active', 'stopped': True}
                if game.winner:
                    logger.warning(f"Game {game_id}: Has winner before first call, stopping")
                    return {'error': 'Game already has winner', 'stopped': True}
            except Game.DoesNotExist:
                logger.error(f"Game {game_id}: Not found in database before first call")
                return {'error': 'Game not found', 'stopped': True}
            except Exception as e:
                logger.error(f"Game {game_id}: Error checking game status before first call: {e}")
                import traceback
                traceback.print_exc()
        
        # Check if all numbers called
        if len(called_numbers) >= 75:
            # All numbers called - schedule final check
            task_check_all_numbers_called.apply_async(args=[game_id], countdown=5)
            return {'stopped': True, 'reason': 'All numbers called'}
        
        # Pick next number
        available = [n for n in range(1, 76) if n not in called_numbers]
        if not available:
            print(f"Game {game_id}: No available numbers (all called)")
            task_check_all_numbers_called.apply_async(args=[game_id], countdown=5)
            return {'stopped': True, 'reason': 'No available numbers'}
        
        number = random.choice(available)
        
        # REDIS-FIRST: Add to Redis only (fast, no DB hit during gameplay)
        # DB records will be created at game end for history
        call_count = add_called_number_live(game_id, number)
        if call_count == 0:
            logger.error(f"❌ ERROR: Failed to add number {number} to Redis for game {game_id}")
            print(f"❌ ERROR: Failed to add number {number} to Redis for game {game_id}")
            # Retry once more before giving up
            import time
            time.sleep(0.1)  # Small delay
            call_count = add_called_number_live(game_id, number)
            if call_count == 0:
                logger.error(f"❌ CRITICAL: Retry also failed to add number {number} to Redis for game {game_id}")
                return {'error': 'Failed to add number to Redis (after retry)', 'stopped': True}
            else:
                logger.info(f"✅ Retry successful: Added number {number} to Redis for game {game_id}")
                print(f"✅ Retry successful: Added number {number} to Redis for game {game_id}")
        
        # Get letter for number
        from .models import CalledNumber
        letter = CalledNumber.get_letter_for_number(number)
        
        print(f"✅ Game {game_id}: Called number {number} ({letter}) - call #{call_count} [Redis-only, DB write at game end]")
        
        # Broadcast number called (players + watchers rooms)
        try:
            broadcast_to_game_rooms(game_id, 'number_called', {
                'number': number,
                'letter': letter,
                'call_count': call_count
            })
        except Exception as e:
            print(f"WebSocket broadcast error: {e}")
        
        # CRITICAL FIX: Mark cards FIRST, then check bingo (add delay to avoid race condition)
        # Marking must complete before bingo check, otherwise bingo check sees unmarked cards
        # We add a small delay to bingo check to ensure marking completes first
        task_mark_cards_for_number.delay(game_id, number)
        
        # Add 0.3 second delay to bingo check to ensure marking has time to complete
        # This is a workaround - ideally we'd chain tasks, but this is simpler and more reliable
        task_check_bingo_for_number.apply_async(args=[game_id, number], countdown=0.3)
        
        # CRITICAL: Schedule next call ONLY if game is still active
        # Re-check state before scheduling (game might have ended during this task)
        state_after = get_game_live_state(game_id)
        if state_after and state_after.get('status') == 'active' and not state_after.get('winner_card_id'):
            call_interval = state_after.get('call_interval', 3)
            # Use explicit task name to ensure routing works
            from celery import current_app
            task = current_app.tasks['api.tasks.task_call_next_number']
            result = task.apply_async(args=[game_id], countdown=call_interval)
            print(f"✅ Game {game_id}: Scheduled next call in {call_interval} seconds (task_id: {result.id})")
            logger.info(f"Game {game_id}: Scheduled next call in {call_interval} seconds (task_id: {result.id})")
            return {'success': True, 'number': number, 'call_count': call_count, 'next_in': call_interval}
        else:
            # Game ended or has winner - don't schedule next call
            print(f"Game {game_id}: Stopped scheduling (status: {state_after.get('status') if state_after else 'None'}, winner: {state_after.get('winner_card_id') if state_after else 'None'})")
            return {'success': True, 'number': number, 'call_count': call_count, 'stopped': True, 'reason': 'Game ended'}
    except Exception as e:
        print(f"❌ ERROR in task_call_next_number for game {game_id}: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e), 'stopped': True}


@shared_task(bind=True, max_retries=2, queue='gameplay')
def task_mark_cards_for_number(self, game_id: int, number: int):
    """
    Mark number on all cards that contain it (Redis-first).
    Separate task so it doesn't block number calling.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🎯 [MARK] Game {game_id}: Starting to mark number {number} on cards")
    print(f"🎯 [MARK] Game {game_id}: Starting to mark number {number} on cards")
    
    try:
        from .redis_utils import mark_number_on_card_live
        from .models import GameCard, FakeUserGameCard
        
        # Get all real cards for this game (include mode_history to check mode)
        real_cards = GameCard.objects.filter(game_id=game_id, is_winner=False).only('id', 'mode_history')
        real_card_count = real_cards.count()
        logger.info(f"🎯 [MARK] Game {game_id}: Found {real_card_count} real cards to check")
        print(f"🎯 [MARK] Game {game_id}: Found {real_card_count} real cards to check")
        
        # CRITICAL FIX: Only mark on real cards that are in AUTOMATIC mode
        # Manual mode users must mark their own numbers
        marked_count = 0
        skipped_manual = 0
        for card in real_cards:
            # Check card mode - only mark if in automatic mode
            card_mode = _get_card_current_mode(card)
            if card_mode == 'automatic':
                # Only mark numbers automatically for cards in automatic mode
                if mark_number_on_card_live(game_id, card.id, number):
                    marked_count += 1
                    logger.debug(f"🎯 [MARK] Game {game_id}: Marked number {number} on card {card.id} (automatic mode)")
            else:
                # Manual mode - skip automatic marking
                skipped_manual += 1
                logger.debug(f"🎯 [MARK] Game {game_id}: Skipped marking number {number} on card {card.id} (manual mode)")
        
        logger.info(f"🎯 [MARK] Game {game_id}: Marked number {number} on {marked_count}/{real_card_count} real cards (automatic mode), skipped {skipped_manual} manual mode cards")
        print(f"🎯 [MARK] Game {game_id}: Marked number {number} on {marked_count}/{real_card_count} real cards (automatic mode), skipped {skipped_manual} manual mode cards")
        
        # Mark on fake cards (Redis) - treat them the same
        fake_cards = FakeUserGameCard.objects.filter(game_id=game_id, is_winner=False).only('id')
        fake_card_count = fake_cards.count()
        logger.info(f"🎯 [MARK] Game {game_id}: Found {fake_card_count} fake cards to check")
        print(f"🎯 [MARK] Game {game_id}: Found {fake_card_count} fake cards to check")
        
        fake_marked_count = 0
        for card in fake_cards:
            if mark_number_on_card_live(game_id, card.id, number):
                fake_marked_count += 1
                logger.debug(f"🎯 [MARK] Game {game_id}: Marked number {number} on fake card {card.id}")
        
        total_marked = marked_count + fake_marked_count
        logger.info(f"🎯 [MARK] Game {game_id}: Marked number {number} on {fake_marked_count}/{fake_card_count} fake cards")
        logger.info(f"✅ [MARK] Game {game_id}: Total marked: {total_marked} cards (real: {marked_count}, fake: {fake_marked_count})")
        print(f"✅ [MARK] Game {game_id}: Total marked: {total_marked} cards (real: {marked_count}, fake: {fake_marked_count})")
        
        return {'success': True, 'marked_count': total_marked, 'real_marked': marked_count, 'fake_marked': fake_marked_count}
    except Exception as e:
        logger.error(f"❌ [MARK] Game {game_id}: Error marking number {number}: {e}")
        print(f"❌ [MARK] Game {game_id}: Error marking number {number}: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


@shared_task(bind=True, max_retries=2, queue='gameplay')
def task_check_bingo_for_number(self, game_id: int, number: int):
    """
    Check bingo for cards that contain the called number (event-based).
    Only checks cards that have this number - much faster.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Starting bingo check for number {number}")
    print(f"🔍 [BINGO CHECK] Game {game_id}: Starting bingo check for number {number}")
    
    try:
        from .redis_utils import (
            get_game_live_state, get_card_marked_numbers_live,
            set_game_winner, get_called_numbers_from_redis
        )
        from .models import GameCard, FakeUserGameCard
        
        # Check if game already has winner
        state = get_game_live_state(game_id)
        logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Redis state: {state}")
        print(f"🔍 [BINGO CHECK] Game {game_id}: Redis state: {state}")
        
        if state.get('winner_card_id'):
            logger.warning(f"⚠️ [BINGO CHECK] Game {game_id}: Already has winner (card_id: {state.get('winner_card_id')}), skipping")
            print(f"⚠️ [BINGO CHECK] Game {game_id}: Already has winner, skipping")
            return {'skipped': True, 'reason': 'Game already has winner'}
        
        # Get all cards that might have this number
        # Only check cards that could have bingo (have this number)
        called_numbers = get_called_numbers_from_redis(game_id)
        logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Called numbers count: {len(called_numbers) if called_numbers else 0}")
        print(f"🔍 [BINGO CHECK] Game {game_id}: Called numbers count: {len(called_numbers) if called_numbers else 0}")
        
        # Get real cards
        real_cards = GameCard.objects.filter(game_id=game_id, is_winner=False).select_related('user')
        real_card_count = real_cards.count()
        logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Checking {real_card_count} real cards")
        print(f"🔍 [BINGO CHECK] Game {game_id}: Checking {real_card_count} real cards")
        
        # Check each card for bingo (using Redis marked numbers)
        checked_count = 0
        for card in real_cards:
            # Get marked numbers from Redis
            marked = get_card_marked_numbers_live(game_id, card.id)
            logger.debug(f"🔍 [BINGO CHECK] Game {game_id}: Card {card.id} has {len(marked) if marked else 0} marked numbers")
            
            # Only check if card has this number marked
            if number not in marked:
                continue
            
            checked_count += 1
            logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Checking card {card.id} (user: {card.user.id if card.user else 'None'}) for bingo")
            print(f"🔍 [BINGO CHECK] Game {game_id}: Checking card {card.id} for bingo")
            
            # Check if card has bingo (using marked numbers from Redis)
            # Load card layout from DB (one-time per card)
            if not card.card_layout:
                logger.warning(f"⚠️ [BINGO CHECK] Game {game_id}: Card {card.id} has no layout, skipping")
                continue
            
            # Check bingo patterns (pass game_id to check enabled patterns)
            has_bingo, pattern = _check_bingo_from_marked(card.card_layout, marked, game_id)
            logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Card {card.id} bingo check result: has_bingo={has_bingo}, pattern={pattern}")
            print(f"🔍 [BINGO CHECK] Game {game_id}: Card {card.id} bingo check: has_bingo={has_bingo}, pattern={pattern}")
            
            if has_bingo:
                logger.info(f"🎉 [BINGO CHECK] Game {game_id}: BINGO FOUND! Card {card.id}, User {card.user.id}, Pattern: {pattern}")
                print(f"🎉 [BINGO CHECK] Game {game_id}: BINGO FOUND! Card {card.id}, User {card.user.id}, Pattern: {pattern}")
                
                # Try to set winner atomically
                winner_set = set_game_winner(game_id, card.id, card.user.id)
                logger.info(f"🎉 [BINGO CHECK] Game {game_id}: set_game_winner returned: {winner_set}")
                print(f"🎉 [BINGO CHECK] Game {game_id}: set_game_winner returned: {winner_set}")
                
                if winner_set:
                    logger.info(f"✅ [BINGO CHECK] Game {game_id}: Winner set successfully! Triggering finalization...")
                    print(f"✅ [BINGO CHECK] Game {game_id}: Winner set successfully! Triggering finalization...")
                    # Winner set - trigger finalization
                    result = task_finalize_game.delay(game_id)
                    logger.info(f"✅ [BINGO CHECK] Game {game_id}: task_finalize_game scheduled with task_id: {result.id}")
                    print(f"✅ [BINGO CHECK] Game {game_id}: task_finalize_game scheduled with task_id: {result.id}")
                    return {'winner': True, 'card_id': card.id, 'pattern': pattern, 'user_id': card.user.id}
                else:
                    logger.warning(f"⚠️ [BINGO CHECK] Game {game_id}: Winner already set by another process")
                    print(f"⚠️ [BINGO CHECK] Game {game_id}: Winner already set by another process")
        
        logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Checked {checked_count} real cards with number {number}, no winners")
        print(f"🔍 [BINGO CHECK] Game {game_id}: Checked {checked_count} real cards with number {number}, no winners")
        
        # Check fake cards too (same logic)
        fake_cards = FakeUserGameCard.objects.filter(game_id=game_id, is_winner=False).select_related('fake_user')
        fake_card_count = fake_cards.count()
        logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Checking {fake_card_count} fake cards")
        print(f"🔍 [BINGO CHECK] Game {game_id}: Checking {fake_card_count} fake cards")
        
        # CRITICAL FIX: Wait a tiny bit to ensure marking has completed
        # This is a workaround for the race condition - marking and bingo check run in parallel
        import time
        time.sleep(0.2)  # Wait 200ms for marking to complete
        logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Waited for marking to complete, now checking fake cards")
        
        fake_checked_count = 0
        fake_cards_list = list(fake_cards)  # Convert to list to ensure we iterate all
        logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Converted {len(fake_cards_list)} fake cards to list for iteration")
        
        for idx, card in enumerate(fake_cards_list):
            # Get marked numbers from Redis
            marked = get_card_marked_numbers_live(game_id, card.id)
            marked_count = len(marked) if marked else 0
            logger.debug(f"🔍 [BINGO CHECK] Game {game_id}: Fake card {card.id} ({idx+1}/{len(fake_cards_list)}) has {marked_count} marked numbers")
            
            # Only check if card has this number marked
            if number not in marked:
                logger.debug(f"🔍 [BINGO CHECK] Game {game_id}: Fake card {card.id} doesn't have number {number} marked, skipping")
                continue
            
            fake_checked_count += 1
            logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Checking fake card {card.id} ({idx+1}/{len(fake_cards_list)}) for bingo - marked: {marked_count} numbers")
            print(f"🔍 [BINGO CHECK] Game {game_id}: Checking fake card {card.id} for bingo")
            
            if not card.card_layout:
                logger.warning(f"⚠️ [BINGO CHECK] Game {game_id}: Fake card {card.id} has no layout, skipping")
                continue
            
            # CRITICAL: Log marked numbers and layout for debugging
            logger.debug(f"🔍 [BINGO CHECK] Game {game_id}: Fake card {card.id} marked numbers: {sorted(marked) if marked else 'empty'}")
            if card.card_layout and len(card.card_layout) > 0:
                first_row_numbers = [cell.get('number') for cell in card.card_layout[0] if cell.get('number') is not None]
                logger.debug(f"🔍 [BINGO CHECK] Game {game_id}: Fake card {card.id} layout first row numbers: {first_row_numbers}")
            
            # Check bingo patterns (pass game_id to check enabled patterns)
            has_bingo, pattern = _check_bingo_from_marked(card.card_layout, marked, game_id)
            logger.info(f"🔍 [BINGO CHECK] Game {game_id}: Fake card {card.id} bingo check: has_bingo={has_bingo}, pattern={pattern}, marked_count={marked_count}, marked={sorted(marked) if marked else 'empty'}")
            print(f"🔍 [BINGO CHECK] Game {game_id}: Fake card {card.id} bingo: has_bingo={has_bingo}, pattern={pattern}, marked={len(marked)} numbers")
            
            if has_bingo:
                logger.info(f"🎉 [BINGO CHECK] Game {game_id}: FAKE USER BINGO! Card {card.id}, Pattern: {pattern}, Marked: {marked_count} numbers")
                print(f"🎉 [BINGO CHECK] Game {game_id}: FAKE USER BINGO! Card {card.id}, Pattern: {pattern}")
                
                # Fake user winner - set winner but no user_id
                winner_set = set_game_winner(game_id, card.id, None)
                logger.info(f"🎉 [BINGO CHECK] Game {game_id}: set_game_winner (fake) returned: {winner_set}")
                print(f"🎉 [BINGO CHECK] Game {game_id}: set_game_winner (fake) returned: {winner_set}")
                
                if winner_set:
                    logger.info(f"✅ [BINGO CHECK] Game {game_id}: Fake winner set! Triggering finalization...")
                    print(f"✅ [BINGO CHECK] Game {game_id}: Fake winner set! Triggering finalization...")
                    result = task_finalize_game.delay(game_id)
                    logger.info(f"✅ [BINGO CHECK] Game {game_id}: task_finalize_game scheduled with task_id: {result.id}")
                    print(f"✅ [BINGO CHECK] Game {game_id}: task_finalize_game scheduled with task_id: {result.id}")
                    return {'winner': True, 'card_id': card.id, 'pattern': pattern, 'is_fake': True, 'marked_count': marked_count}
                else:
                    logger.warning(f"⚠️ [BINGO CHECK] Game {game_id}: Failed to set fake winner (already set?)")
                    print(f"⚠️ [BINGO CHECK] Game {game_id}: Failed to set fake winner")
        
        logger.info(f"✅ [BINGO CHECK] Game {game_id}: Checked all {fake_card_count} fake cards, checked {fake_checked_count} that had number {number} marked")
        print(f"✅ [BINGO CHECK] Game {game_id}: Checked {fake_checked_count}/{fake_card_count} fake cards")
        
        logger.info(f"✅ [BINGO CHECK] Game {game_id}: No winners found. Checked {checked_count} real + {fake_checked_count} fake cards")
        print(f"✅ [BINGO CHECK] Game {game_id}: No winners found. Checked {checked_count} real + {fake_checked_count} fake cards")
        return {'checked': True, 'no_winners': True, 'real_checked': checked_count, 'fake_checked': fake_checked_count}
    except Exception as e:
        logger.error(f"❌ [BINGO CHECK] Game {game_id}: Error checking bingo for number {number}: {e}")
        print(f"❌ [BINGO CHECK] Game {game_id}: Error checking bingo for number {number}: {e}")
        import traceback
        traceback.print_exc()
        return {'error': str(e)}


def _check_bingo_from_marked(layout, marked_numbers: set, game_id: int = None) -> tuple:
    """
    Check if card has bingo using marked numbers set.
    Returns (has_bingo: bool, pattern: str or None)
    
    CRITICAL: Checks only enabled patterns from GameSettings.
    """
    if not layout or len(marked_numbers) < 5:
        return (False, None)
    
    # Get enabled winning patterns from settings
    from .models import GameSettings
    settings = GameSettings.get_settings(game_id=game_id)
    enabled_patterns = getattr(settings, 'winning_patterns', [])
    
    # If no patterns specified, default to all patterns (backward compatibility)
    if not enabled_patterns:
        enabled_patterns = ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']
    
    enabled_patterns_set = set(enabled_patterns)
    
    # Helper to check if cell is marked
    def is_marked(cell):
        if cell.get('letter') == 'FREE':
            return True
        # CRITICAL FIX: Ensure number comparison works (handle both int and str)
        cell_number = cell.get('number')
        if cell_number is None:
            return False
        # Convert to int for comparison (marked_numbers is set of ints)
        try:
            cell_number_int = int(cell_number)
            return cell_number_int in marked_numbers
        except (ValueError, TypeError):
            return False
    
    # IMPORTANT: If only 'full_card' is enabled, skip all other pattern checks
    only_full_card = enabled_patterns_set == {'full_card'}
    
    # Check horizontal lines (any row) - skip if only full_card is enabled
    if not only_full_card and 'horizontal' in enabled_patterns_set:
        for row_idx, row in enumerate(layout):
            if all(is_marked(cell) for cell in row):
                return (True, f'row_{row_idx}')
    
    # Check vertical lines (any column) - skip if only full_card is enabled
    if not only_full_card and 'vertical' in enabled_patterns_set:
        for col_idx in range(5):
            if all(is_marked(layout[row_idx][col_idx]) for row_idx in range(5)):
                return (True, f'col_{col_idx}')
    
    # Check diagonal (top-left to bottom-right) - skip if only full_card is enabled
    if not only_full_card and 'diagonal' in enabled_patterns_set:
        if all(is_marked(layout[i][i]) for i in range(5)):
            return (True, 'diagonal_1')
        # Check diagonal (top-right to bottom-left)
        if all(is_marked(layout[i][4-i]) for i in range(5)):
            return (True, 'diagonal_2')
    
    # Check corner bingo (4 corners + FREE cell) - skip if only full_card is enabled
    if not only_full_card and 'corner' in enabled_patterns_set:
        corners = [layout[0][0], layout[0][4], layout[4][0], layout[4][4], layout[2][2]]
        if all(is_marked(cell) for cell in corners):
            return (True, 'corner')
    
    # Check full card - ONLY wins if ALL cells are marked
    if 'full_card' in enabled_patterns_set:
        if all(is_marked(cell) for row in layout for cell in row):
            return (True, 'full_card')
    
    return (False, None)


@shared_task(bind=True, max_retries=2, queue='gameplay')
def task_finalize_game(self, game_id: int):
    """
    Finalize game - write final state to database.
    This is the ONLY place that writes to DB during/after gameplay.
    Called after winner is determined.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"🏁 [FINALIZE] Game {game_id}: Starting game finalization")
    print(f"🏁 [FINALIZE] Game {game_id}: Starting game finalization")
    
    try:
        from .redis_utils import (
            get_game_live_state, get_called_numbers_list_from_redis,
            cleanup_game_live_state
        )
        from .models import Game, GameCard, FakeUserGameCard, CalledNumber, Transaction
        from django.db import transaction
        from django.db.models import F
        from decimal import Decimal
        
        # Get final state from Redis
        state = get_game_live_state(game_id)
        called_numbers = get_called_numbers_list_from_redis(game_id)
        
        logger.info(f"🏁 [FINALIZE] Game {game_id}: Redis state: {state}")
        logger.info(f"🏁 [FINALIZE] Game {game_id}: Called numbers count: {len(called_numbers) if called_numbers else 0}")
        print(f"🏁 [FINALIZE] Game {game_id}: Redis state: {state}")
        print(f"🏁 [FINALIZE] Game {game_id}: Called numbers: {called_numbers}")
        
        if not state:
            logger.error(f"❌ [FINALIZE] Game {game_id}: Game state not found in Redis")
            print(f"❌ [FINALIZE] Game {game_id}: Game state not found in Redis")
            return {'error': 'Game state not found in Redis'}
        
        # Get game from DB
        game = Game.objects.get(id=game_id)
        logger.info(f"🏁 [FINALIZE] Game {game_id}: Loaded game from DB, current status: {game.status}, derash_amount: {game.derash_amount}")
        print(f"🏁 [FINALIZE] Game {game_id}: Loaded game from DB, current status: {game.status}, derash_amount: {game.derash_amount}")
        
        # CRITICAL: Recalculate derash before finalization to ensure accurate prize calculation
        # This ensures derash_amount is up-to-date with all cards (real + fake)
        logger.info(f"🏁 [FINALIZE] Game {game_id}: Recalculating derash before finalization")
        print(f"🏁 [FINALIZE] Game {game_id}: Recalculating derash - current derash_amount: {game.derash_amount}")
        game.recalculate_derash()
        game.refresh_from_db()
        logger.info(f"🏁 [FINALIZE] Game {game_id}: Derash recalculated - new derash_amount: {game.derash_amount}, total_derash: {game.total_derash}")
        print(f"🏁 [FINALIZE] Game {game_id}: Derash recalculated - derash_amount: {game.derash_amount}, total_derash: {game.total_derash}")
        
        # Get winner from Redis state
        winner_card_id = state.get('winner_card_id')
        winner_user_id = state.get('winner_user_id')
        
        logger.info(f"🏁 [FINALIZE] Game {game_id}: Winner from Redis - card_id={winner_card_id}, user_id={winner_user_id}")
        print(f"🏁 [FINALIZE] Game {game_id}: Winner from Redis - card_id={winner_card_id}, user_id={winner_user_id}")
        
        # Write final state to DB
        with transaction.atomic():
            # Update game status
            game.status = 'completed'
            game.completed_at = timezone.now()
            game.current_call_count = len(called_numbers)
            logger.info(f"🏁 [FINALIZE] Game {game_id}: Updating game status to 'completed', call_count={len(called_numbers)}")
            
            if winner_card_id:
                # Check if real user or fake user
                if winner_user_id:
                    # Real user winner
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Processing real user winner - card_id={winner_card_id}, user_id={winner_user_id}")
                    print(f"🏁 [FINALIZE] Game {game_id}: Processing real user winner")
                    winner_card = GameCard.objects.get(id=winner_card_id)
                    game.winner = winner_card.user
                    game.winners.add(winner_card.user)
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Set winner in DB - user: {winner_card.user.username} (id: {winner_card.user.id})")
                else:
                    # Fake user winner
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Processing fake user winner - card_id={winner_card_id}")
                    print(f"🏁 [FINALIZE] Game {game_id}: Processing fake user winner")
                    fake_card = FakeUserGameCard.objects.get(id=winner_card_id)
                    # Fake users don't get prizes, but game still ends
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Fake user winner - no prize awarded")
            
            game.save()
            logger.info(f"🏁 [FINALIZE] Game {game_id}: Game saved to DB")
            
            # Create CalledNumber records in DB (for history)
            for num in called_numbers:
                CalledNumber.objects.get_or_create(
                    game=game,
                    number=num,
                    defaults={'letter': CalledNumber.get_letter_for_number(num)}
                )
            
            # Process prizes for real winners (CRITICAL: Must happen before broadcast)
            # CRITICAL: Refresh game inside transaction to get latest derash_amount
            game.refresh_from_db()
            derash_to_award = game.derash_amount if game.derash_amount and game.derash_amount > 0 else Decimal('0')
            logger.info(f"🏁 [FINALIZE] Game {game_id}: Prize pool (inside transaction) - derash_amount={game.derash_amount}, total_derash={game.total_derash}, derash_to_award={derash_to_award}")
            print(f"🏁 [FINALIZE] Game {game_id}: Prize pool - derash_amount={game.derash_amount}, derash_to_award={derash_to_award}")
            
            # CRITICAL: Verify derash is not 0
            if derash_to_award == 0:
                logger.error(f"❌ [FINALIZE] Game {game_id}: derash_to_award is 0! derash_amount={game.derash_amount}")
                print(f"❌ [FINALIZE] Game {game_id}: ERROR - derash_to_award is 0!")
            
            if winner_user_id and derash_to_award > 0:
                winner_cards = GameCard.objects.filter(game=game, is_winner=True)
                real_winners = [c for c in winner_cards if c.user_id]
                
                if real_winners:
                    prize_per_winner = derash_to_award / len(real_winners)
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Awarding prizes - derash_amount={derash_to_award}, real_winners={len(real_winners)}, prize_per_winner={prize_per_winner}")
                    print(f"🏁 [FINALIZE] Game {game_id}: Awarding {prize_per_winner} to {len(real_winners)} real winners")
                    
                    for winner_card in real_winners:
                        winner_card.refresh_from_db()
                        winner_card.user.refresh_from_db()
                        old_balance = winner_card.user.balance
                        # Prize: add to withdrawable_balance if user has deposited >= min_withdraw, else unwithdrawable_balance
                        if winner_card.user.has_withdrawable_active():
                            User.objects.filter(id=winner_card.user.id).update(withdrawable_balance=F('withdrawable_balance') + prize_per_winner)
                        else:
                            User.objects.filter(id=winner_card.user.id).update(unwithdrawable_balance=F('unwithdrawable_balance') + prize_per_winner)
                        winner_card.user.refresh_from_db()
                        new_balance = winner_card.user.balance
                        logger.info(f"🏁 [FINALIZE] Game {game_id}: Awarded {prize_per_winner} to user {winner_card.user.id} ({winner_card.user.username}), balance: {old_balance} -> {new_balance}")
                        print(f"🏁 [FINALIZE] Game {game_id}: User {winner_card.user.username} balance updated: {old_balance} -> {new_balance}")
                        if new_balance != old_balance + prize_per_winner:
                            logger.error(f"❌ [FINALIZE] Game {game_id}: Balance update mismatch! Expected: {old_balance + prize_per_winner}, Got: {new_balance}")
                            print(f"❌ [FINALIZE] Game {game_id}: Balance update mismatch! Expected: {old_balance + prize_per_winner}, Got: {new_balance}")
                        Transaction.objects.create(
                            user=winner_card.user,
                            transaction_type='win',
                            amount=prize_per_winner,
                            game=game,
                            description=f'Won game {game.id}'
                        )
                else:
                    logger.warning(f"⚠️ [FINALIZE] Game {game_id}: No real winners found to award prize")
                    print(f"⚠️ [FINALIZE] Game {game_id}: No real winners found")
            else:
                logger.warning(f"⚠️ [FINALIZE] Game {game_id}: No prize to award - winner_user_id={winner_user_id}, derash={derash_to_award}")
                print(f"⚠️ [FINALIZE] Game {game_id}: No prize to award")
        
        # CRITICAL: Broadcast winner_declared FIRST (frontend listens for this)
        # Get winner card data for broadcast (works for both real and fake users)
        winner_data = None
        if winner_card_id:
            logger.info(f"🏁 [FINALIZE] Game {game_id}: Preparing winner data for broadcast")
            print(f"🏁 [FINALIZE] Game {game_id}: Preparing winner data for broadcast")
            try:
                # Check if real user or fake user winner
                is_fake_winner = (winner_user_id is None)
                
                if is_fake_winner:
                    # Fake user winner
                    from .models import FakeUserGameCard
                    fake_card = FakeUserGameCard.objects.get(id=winner_card_id)
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Loaded fake winner card {winner_card_id}, fake_user: {fake_card.fake_user.name}")
                    print(f"🏁 [FINALIZE] Game {game_id}: Fake user winner - {fake_card.fake_user.name}")
                    
                    # Get called numbers for winner data
                    called_numbers_list = list(CalledNumber.objects.filter(game=game).order_by('called_at').values_list('number', flat=True))
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Got {len(called_numbers_list)} called numbers from DB")
                    
                    # Check bingo pattern using Redis marked numbers
                    from .redis_utils import get_card_marked_numbers_live
                    marked = get_card_marked_numbers_live(game_id, fake_card.id)
                    has_bingo, pattern = _check_bingo_from_marked(fake_card.card_layout, marked, game_id)
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Fake card bingo check - has_bingo={has_bingo}, pattern={pattern}")
                    
                    # Calculate prize (fake users don't get prizes, but show total prize for display)
                    # CRITICAL: Refresh game to get latest derash_amount after recalculation
                    game.refresh_from_db()
                    total_prize_display = float(game.derash_amount) if game.derash_amount and game.derash_amount > 0 else 0.0
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Fake winner - derash_amount={game.derash_amount}, total_derash={game.total_derash}, total_prize_display={total_prize_display}")
                    print(f"🏁 [FINALIZE] Game {game_id}: Fake winner - derash_amount={game.derash_amount}, total_prize_display={total_prize_display}")
                    
                    # CRITICAL: For fake users, show total_prize in the 'prize' field for frontend display
                    # Frontend might be looking at 'prize' not 'total_prize'
                    winner_data = {
                        'winners': [{
                            'winner': {
                                'id': None,
                                'username': fake_card.fake_user.name,
                                'name': fake_card.fake_user.name,
                                'is_fake': True
                            },
                            'username': fake_card.fake_user.name,
                            'is_fake': True,
                            'card_number': fake_card.card_number,
                            'card_id': fake_card.id,
                            'card_layout': fake_card.card_layout,
                            'winning_pattern': pattern if has_bingo else None,
                            'selected_numbers': [],
                            'called_numbers': called_numbers_list,
                            'last_called_number': called_numbers_list[-1] if called_numbers_list else None,
                            'prize': total_prize_display  # Show total prize for display (fake users don't receive it)
                        }],
                        'winner': {
                            'id': None,
                            'username': fake_card.fake_user.name,
                            'name': fake_card.fake_user.name,
                            'is_fake': True
                        },
                        'card_number': fake_card.card_number,
                        'card_id': fake_card.id,
                        'card_layout': fake_card.card_layout,
                        'winning_pattern': pattern if has_bingo else None,
                        'prize': total_prize_display,  # Show total prize for display (fake users don't receive it)
                        'total_prize': total_prize_display,  # Also include in total_prize field
                        'winner_count': 1,
                        'last_called_number': called_numbers_list[-1] if called_numbers_list else None,
                        'called_numbers': called_numbers_list
                    }
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Fake winner data - prize={total_prize_display}, total_prize={total_prize_display}")
                    print(f"🏁 [FINALIZE] Game {game_id}: Fake winner data prepared - prize field: {total_prize_display}")
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Fake winner data prepared successfully")
                    print(f"🏁 [FINALIZE] Game {game_id}: Fake winner data prepared - {fake_card.fake_user.name}")
                else:
                    # Real user winner
                    from .serializers import UserSerializer
                    from .game_logic import check_bingo, get_winning_number
                    
                    winner_card = GameCard.objects.get(id=winner_card_id)
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Loaded winner card {winner_card_id}, user: {winner_card.user.username}")
                    
                    # Get called numbers for winner data (from DB since we just created them)
                    called_numbers_list = list(CalledNumber.objects.filter(game=game).order_by('called_at').values_list('number', flat=True))
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Got {len(called_numbers_list)} called numbers from DB")
                    
                    # CRITICAL: Get marked numbers from Redis (like fake users) for proper winning line display
                    from .redis_utils import get_card_marked_numbers_live
                    marked_numbers = get_card_marked_numbers_live(game_id, winner_card.id)
                    marked_numbers_list = sorted(list(marked_numbers)) if marked_numbers else []
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Got {len(marked_numbers_list)} marked numbers from Redis for winner card")
                    
                    # Check bingo pattern
                    has_bingo, pattern = check_bingo(winner_card, game)
                    winning_number = get_winning_number(winner_card, pattern if has_bingo else None, called_numbers_list)
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Bingo check - has_bingo={has_bingo}, pattern={pattern}, winning_number={winning_number}")
                    
                    # Calculate prize for display (already awarded above)
                    # CRITICAL: Refresh game to get latest derash_amount after recalculation
                    game.refresh_from_db()
                    winner_cards = GameCard.objects.filter(game=game, is_winner=True)
                    real_winners = [c for c in winner_cards if c.user_id]
                    derash_for_display = float(game.derash_amount) if game.derash_amount and game.derash_amount > 0 else 0.0
                    prize_per_winner = float(derash_for_display / len(real_winners)) if real_winners and derash_for_display > 0 else 0.0
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Prize calculation for display - derash_amount={game.derash_amount}, total_derash={game.total_derash}, winners={len(real_winners)}, prize_per_winner={prize_per_winner}")
                    print(f"🏁 [FINALIZE] Game {game_id}: Prize for display - derash_amount={game.derash_amount}, real_winners={len(real_winners)}, prize_per_winner={prize_per_winner}")
                    
                    # CRITICAL: Verify prize is not 0
                    if prize_per_winner == 0.0:
                        logger.error(f"❌ [FINALIZE] Game {game_id}: Prize is 0! derash_amount={game.derash_amount}, real_winners={len(real_winners)}")
                        print(f"❌ [FINALIZE] Game {game_id}: WARNING - Prize is 0! derash_amount={game.derash_amount}")
                    
                    winner_data = {
                        'winners': [{
                            'winner': UserSerializer(winner_card.user).data,
                            'username': winner_card.user.username,
                            'is_fake': False,
                            'card_number': winner_card.card_number,
                            'card_id': winner_card.id,
                            'card_layout': winner_card.card_layout,
                            'winning_pattern': pattern if has_bingo else None,
                            'selected_numbers': marked_numbers_list,  # CRITICAL: Use marked numbers from Redis for winning line
                            'called_numbers': called_numbers_list,
                            'last_called_number': winning_number,
                            'prize': prize_per_winner  # CRITICAL: Ensure this is a float, not Decimal
                        }],
                        'winner': UserSerializer(winner_card.user).data,
                        'card_number': winner_card.card_number,
                        'card_id': winner_card.id,
                        'card_layout': winner_card.card_layout,
                        'winning_pattern': pattern if has_bingo else None,
                        'prize': prize_per_winner,  # CRITICAL: Ensure this is a float, not Decimal
                        'total_prize': derash_for_display,  # Use calculated derash_amount
                        'winner_count': len(real_winners),
                        'last_called_number': winning_number,
                        'called_numbers': called_numbers_list
                    }
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Winner data prepared successfully - prize={prize_per_winner}, total_prize={derash_for_display}")
                    print(f"🏁 [FINALIZE] Game {game_id}: Winner data prepared - winner: {winner_card.user.username}, prize: {prize_per_winner}, total_prize: {derash_for_display}")
                    # CRITICAL: Log the actual data being sent
                    logger.info(f"🏁 [FINALIZE] Game {game_id}: Winner data structure - prize field: {prize_per_winner}, total_prize field: {derash_for_display}")
                    print(f"🏁 [FINALIZE] Game {game_id}: Data structure - prize: {prize_per_winner}, total_prize: {derash_for_display}")
            except Exception as e:
                logger.error(f"❌ [FINALIZE] Game {game_id}: Error preparing winner data: {e}")
                print(f"❌ [FINALIZE] Game {game_id}: Error preparing winner data: {e}")
                import traceback
                traceback.print_exc()
                # Try to create minimal winner data even on error
                try:
                    if winner_user_id:
                        # Real user - create minimal data
                        winner_card = GameCard.objects.get(id=winner_card_id)
                        from .serializers import UserSerializer
                        game.refresh_from_db()
                        derash_for_display = float(game.derash_amount) if game.derash_amount and game.derash_amount > 0 else 0.0
                        winner_cards = GameCard.objects.filter(game=game, is_winner=True)
                        real_winners = [c for c in winner_cards if c.user_id]
                        prize_per_winner = float(derash_for_display / len(real_winners)) if real_winners and derash_for_display > 0 else 0.0
                        logger.info(f"🏁 [FINALIZE] Game {game_id}: Error recovery (real) - derash={derash_for_display}, prize={prize_per_winner}")
                        
                        # Get marked numbers from Redis for winning line
                        from .redis_utils import get_card_marked_numbers_live
                        marked_numbers = get_card_marked_numbers_live(game_id, winner_card.id)
                        marked_numbers_list = sorted(list(marked_numbers)) if marked_numbers else []
                        called_numbers_list = list(CalledNumber.objects.filter(game=game).order_by('called_at').values_list('number', flat=True))
                        winner_data = {
                            'winners': [{
                                'winner': UserSerializer(winner_card.user).data,
                                'username': winner_card.user.username,
                                'is_fake': False,
                                'card_number': winner_card.card_number,
                                'card_id': winner_card.id,
                                'selected_numbers': marked_numbers_list,  # Use marked numbers for winning line
                                'prize': prize_per_winner  # Ensure float
                            }],
                            'winner': UserSerializer(winner_card.user).data,
                            'prize': prize_per_winner,  # Ensure float
                            'total_prize': derash_for_display,
                            'called_numbers': called_numbers_list
                        }
                        logger.info(f"🏁 [FINALIZE] Game {game_id}: Created minimal winner data after error - prize: {prize_per_winner}")
                    else:
                        # Fake user - create minimal data
                        from .models import FakeUserGameCard
                        fake_card = FakeUserGameCard.objects.get(id=winner_card_id)
                        game.refresh_from_db()
                        total_prize_display = float(game.derash_amount) if game.derash_amount and game.derash_amount > 0 else 0.0
                        logger.info(f"🏁 [FINALIZE] Game {game_id}: Error recovery (fake) - derash={game.derash_amount}, total_prize={total_prize_display}")
                        called_numbers_list = list(CalledNumber.objects.filter(game=game).order_by('called_at').values_list('number', flat=True))
                        winner_data = {
                            'winners': [{
                                'winner': {'id': None, 'username': fake_card.fake_user.name, 'is_fake': True},
                                'username': fake_card.fake_user.name,
                                'is_fake': True,
                                'prize': total_prize_display  # Show total prize for display
                            }],
                            'winner': {'id': None, 'username': fake_card.fake_user.name, 'is_fake': True},
                            'prize': total_prize_display,  # Show total prize for display
                            'total_prize': total_prize_display,
                            'called_numbers': called_numbers_list
                        }
                        logger.info(f"🏁 [FINALIZE] Game {game_id}: Created minimal fake winner data after error - total_prize: {total_prize_display}")
                except Exception as e2:
                    logger.error(f"❌ [FINALIZE] Game {game_id}: Failed to create minimal winner data: {e2}")
                    winner_data = None
        else:
            logger.warning(f"⚠️ [FINALIZE] Game {game_id}: No winner data to broadcast (card_id={winner_card_id}, user_id={winner_user_id})")
            print(f"⚠️ [FINALIZE] Game {game_id}: No winner data to broadcast")
        
        # Broadcast winner_declared (frontend listens for this event) - immediately for all winners
        if winner_data:
            logger.info(f"📢 [FINALIZE] Game {game_id}: Broadcasting winner_declared event")
            print(f"📢 [FINALIZE] Game {game_id}: Broadcasting winner_declared event")
            try:
                broadcast_to_game_rooms(game.id, 'winner_declared', winner_data)
                logger.info(f"✅ [FINALIZE] Game {game_id}: winner_declared broadcast successful, prize in data: {winner_data.get('prize', 'N/A')}")
                print(f"✅ [FINALIZE] Game {game_id}: winner_declared broadcast successful")
            except Exception as e:
                logger.error(f"❌ [FINALIZE] Game {game_id}: WebSocket broadcast error (winner_declared): {e}")
                print(f"❌ [FINALIZE] Game {game_id}: WebSocket broadcast error (winner_declared): {e}")
                import traceback
                traceback.print_exc()
        else:
            logger.warning(f"⚠️ [FINALIZE] Game {game_id}: Skipping winner_declared broadcast - no winner_data")
        
        # Broadcast game_ended immediately (players + watchers rooms)
        try:
            broadcast_to_game_rooms(game.id, 'game_ended', {
                'game_id': game.id,
                'status': 'completed',
                'winner_id': winner_user_id,
                'completed_at': game.completed_at.isoformat() if game.completed_at else None
            })
        except Exception as e:
            print(f"WebSocket broadcast error (game_ended): {e}")
        
        # Update aggregate stats (survives prune) so dashboard and user search stay correct
        try:
            from .models import GameCard, GameSettings
            from .stats_utils import record_game_completed
            from decimal import Decimal
            real_count = GameCard.objects.filter(game=game).count()
            settings = GameSettings.get_settings()
            pct = getattr(settings, 'percentage_cut', Decimal('10')) or Decimal('10')
            revenue = (Decimal(str(real_count)) * game.bet_amount * pct) / Decimal('100')
            record_game_completed(game, revenue)
        except Exception as e:
            logger.warning(f"Stats update failed for game {game_id}: {e}")
            print(f"Stats update failed for game {game_id}: {e}")
        
        # CRITICAL: Cleanup ALL Redis state AFTER broadcasting
        # This prevents any scheduled tasks from seeing stale state
        cleanup_game_live_state(game_id)
        
        # Also clean up old cache keys that might exist
        try:
            from .redis_utils import invalidate_game_state_cache, cleanup_game_redis_keys
            invalidate_game_state_cache(game_id)
            cleanup_game_redis_keys(game_id)  # Old cleanup function for backward compatibility
        except (ImportError, AttributeError):
            pass  # Functions may not exist in all versions
        
        logger.info(f"🏁 [FINALIZE] Game {game_id}: Game finalization completed")
        print(f"🏁 [FINALIZE] Game {game_id}: Game finalization completed")
    
    except Exception as e:
        logger.error(f"❌ [FINALIZE] Game {game_id}: Error in task_finalize_game: {e}")
        print(f"Error in task_finalize_game: {e}")
        import traceback
        traceback.print_exc()


@shared_task(bind=True, queue='gameplay')
def task_broadcast_winner(self, game_id: int, winner_data: dict):
    """
    Broadcast winner_declared and game_ended events (used when called with countdown=0, e.g. Redis system winner).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from .models import Game

        game = Game.objects.get(id=game_id)

        logger.info(f"📢 [BROADCAST] Game {game_id}: Broadcasting delayed winner_declared and game_ended events")
        print(f"📢 [BROADCAST] Game {game_id}: Broadcasting delayed winner_declared and game_ended events")

        logger.info(f"📢 [BROADCAST] Game {game_id}: Broadcasting winner_declared with data - prize: {winner_data.get('prize', 'N/A')}, total_prize: {winner_data.get('total_prize', 'N/A')}")
        print(f"📢 [BROADCAST] Game {game_id}: Broadcasting - prize: {winner_data.get('prize', 'N/A')}, total_prize: {winner_data.get('total_prize', 'N/A')}")

        broadcast_to_game_rooms(game.id, 'winner_declared', winner_data)
        logger.info(f"✅ [BROADCAST] Game {game_id}: winner_declared broadcast successful, prize in data: {winner_data.get('prize', 'N/A')}")
        print(f"✅ [BROADCAST] Game {game_id}: winner_declared broadcast successful - prize: {winner_data.get('prize', 'N/A')}")

        try:
            broadcast_to_game_rooms(game.id, 'game_ended', {
                'game_id': game.id,
                'status': 'completed',
                'winner_id': None,  # Fake winner has no user_id
                'completed_at': game.completed_at.isoformat() if game.completed_at else None
            })
            logger.info(f"✅ [BROADCAST] Game {game_id}: game_ended broadcast successful (fake winner)")
            print(f"✅ [BROADCAST] Game {game_id}: game_ended broadcast successful (fake winner)")
        except Exception as e:
            logger.error(f"❌ [BROADCAST] Game {game_id}: WebSocket broadcast error (game_ended): {e}")
            print(f"❌ [BROADCAST] Game {game_id}: WebSocket broadcast error (game_ended): {e}")

        return {'success': True}
    except Exception as e:
        logger.error(f"❌ [BROADCAST] Game {game_id}: WebSocket broadcast error (winner_declared): {e}")
        print(f"❌ [BROADCAST] Game {game_id}: WebSocket broadcast error (winner_declared): {e}")
        import traceback
        traceback.print_exc()
        
        return {'success': False, 'error': str(e)}


@shared_task(bind=True, queue='gameplay')
def task_finalize_redis_system_winner(game_id: int, winner_dict: dict):
    """
    Finalize game when a Redis-only system player wins.
    No DB winner record, no payout. Mark game completed, cleanup Redis, broadcast winner (delayed).
    winner_dict: {card_number, name, card_layout, pattern, marked_numbers} from batch_mark_number_on_system_players_redis.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        from .redis_utils import cleanup_game_live_state, get_called_numbers_list_from_redis
        from .models import CalledNumber
        game = Game.objects.get(id=game_id)
        # CRITICAL: Persist called numbers from Redis to DB BEFORE clearing Redis,
        # so real users can still tick the last number (co-winner) and mark_number finds it in DB.
        called_numbers = get_called_numbers_list_from_redis(game_id)
        if called_numbers:
            for num in called_numbers:
                CalledNumber.objects.get_or_create(
                    game=game,
                    number=num,
                    defaults={'letter': CalledNumber.get_letter_for_number(num)}
                )
            game.current_call_count = len(called_numbers)
        game.status = 'completed'
        game.completed_at = timezone.now()
        game.save(update_fields=['status', 'completed_at', 'current_call_count'])
        # Update aggregate stats (survives prune); Redis-only winner = fake
        try:
            from .models import GameCard, GameSettings
            from .stats_utils import record_game_completed
            from decimal import Decimal
            real_count = GameCard.objects.filter(game=game).count()
            settings = GameSettings.get_settings()
            pct = getattr(settings, 'percentage_cut', Decimal('10')) or Decimal('10')
            revenue = (Decimal(str(real_count)) * game.bet_amount * pct) / Decimal('100')
            record_game_completed(game, revenue, winner_type='fake')
        except Exception as e:
            logger.warning(f"Stats update failed for game {game_id}: {e}")
        cleanup_game_live_state(game_id)
        name = winner_dict.get('name', 'System')
        card_number = winner_dict.get('card_number')
        card_layout = winner_dict.get('card_layout', [])
        pattern = winner_dict.get('pattern')
        marked_numbers = winner_dict.get('marked_numbers') or []
        selected_list = sorted(marked_numbers) if isinstance(marked_numbers, (set, list)) else []
        winner_data = {
            'winners': [{
                'winner': {'id': None, 'username': name, 'name': name, 'is_fake': True},
                'username': name,
                'is_fake': True,
                'card_number': card_number,
                'card_id': None,
                'card_layout': card_layout,
                'winning_pattern': pattern,
                'selected_numbers': selected_list,
                'called_numbers': [],
                'last_called_number': None,
                'prize': 0
            }],
            'winner': {'id': None, 'username': name, 'name': name, 'is_fake': True},
            'card_number': card_number,
            'card_id': None,
            'card_layout': card_layout,
            'winning_pattern': pattern,
            'prize': 0,
            'total_prize': 0,
            'winner_count': 1,
            'last_called_number': None,
            'called_numbers': []
        }
        task_broadcast_winner.apply_async(args=[game_id, winner_data], countdown=0)
        logger.info(f"Redis system winner finalized for game {game_id}: {name}, card {card_number}")
        return {'success': True}
    except Exception as e:
        logger.error(f"task_finalize_redis_system_winner error: {e}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e)}


@shared_task(bind=True, max_retries=2, queue='gameplay')
def task_check_game_status_after_number(self, game_id: int, number: int):
    """
    Check game status after number call to see if game was completed.
    CRITICAL FIX: Separate task to avoid blocking number calling with time.sleep().
    """
    try:
        # Use new Redis-first live state (source of truth)
        from .redis_utils import get_game_live_state
        from .models import GameSettings
        
        # Check game live state from Redis
        state = get_game_live_state(game_id)
        if not state or state.get('status') != 'active' or state.get('winner_card_id'):
            print(f"Game {game_id}: Game completed or has winner after calling number {number}, stopping number calling")
            return {'success': True, 'number': number, 'stopped': True, 'reason': 'Game completed'}
        
        # Game still active, continue calling numbers using new Redis-first task
        settings = GameSettings.get_settings(game_id=game_id)
        time_between_calls = settings.time_between_calls or 3
        
        # Use new Redis-first task (not old task_auto_call_numbers)
        from .tasks import task_call_next_number
        task_call_next_number.apply_async(args=[game_id], countdown=time_between_calls)
        return {'success': True, 'number': number, 'game_still_active': True, 'next_call_scheduled': True}
    except Exception as e:
        print(f"Error in task_check_game_status_after_number: {e}")
        return {'error': str(e)}


@shared_task(bind=True, max_retries=3, queue='registration')
def task_process_registration_rewards(self, user_id: int, is_first_registration: bool):
    """
    Process registration rewards asynchronously (PROMO-SAFE)
    
    This task handles:
    - Registration gift (if first registration)
    - Referral reward (if user has referrer)
    - Transaction records
    - Fraud checks
    
    All operations are wrapped in atomic transaction to prevent partial updates.
    """
    from django.db import transaction
    from .models import User, Transaction, GameSettings
    from .redis_utils import (
        acquire_reward_lock, release_reward_lock,
        acquire_referral_lock, release_referral_lock
    )
    from decimal import Decimal
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        # Acquire reward lock to prevent duplicate processing
        if not acquire_reward_lock(user_id, timeout=30):
            logger.warning(f"Reward lock already held for user {user_id}, skipping")
            return {'error': 'Reward already being processed', 'skipped': True}
        
        try:
            with transaction.atomic():
                # Get fresh user data
                user = User.objects.select_for_update().get(id=user_id)
                
                # Get GameSettings (should be cached, but get fresh if needed)
                game_settings = GameSettings.get_settings()
                # STEP 1: Grant registration gift (if first registration and setting enabled) - bid_amount as reward → unwithdrawable_balance
                if is_first_registration and getattr(game_settings, 'give_register_reward', True):
                    bid_amount = Decimal(str(game_settings.bid_amount))
                    registration_reward = bid_amount
                    from django.db.models import F
                    User.objects.filter(id=user.id).update(unwithdrawable_balance=F('unwithdrawable_balance') + registration_reward)
                    user.refresh_from_db()
                    Transaction.objects.create(
                        user=user,
                        transaction_type='deposit',
                        amount=registration_reward,
                        description='Registration gift'
                    )
                    logger.info(f"✅ Registration gift {registration_reward} given to user {user.telegram_id} (id={user.id})")
                
                # STEP 2: Process referral reward (if applicable)
                # Get fresh user data again to check referral status
                user.refresh_from_db()
                
                if user.referred_by_id and not user.referral_reward_given:
                    referrer_id = user.referred_by_id
                    
                    # Acquire referral lock to prevent spam payouts
                    if not acquire_referral_lock(referrer_id, timeout=60):
                        logger.warning(f"Referral lock already held for referrer {referrer_id}, will retry")
                        # Release reward lock before retry
                        release_reward_lock(user_id)
                        # Retry after 5 seconds
                        raise self.retry(countdown=5, exc=Exception("Referral lock busy"))
                    
                    try:
                        # Get referrer with lock
                        referrer = User.objects.select_for_update().get(id=referrer_id)
                        
                        # Fraud checks
                        if not referrer.phone_number:
                            logger.warning(f"Referrer {referrer.telegram_id} (id={referrer.id}) is not registered (no phone number)")
                        else:
                            # Referral reward is disabled - set to 0, no notification, no transaction
                            referral_reward = Decimal('0')
                            
                            # Mark referral reward as given (even though amount is 0)
                            user.referral_reward_given = True
                            user.save(update_fields=['referral_reward_given'])
                            
                            logger.info(f"⏸️ Referral reward disabled (set to 0, no notification) for referrer {referrer.telegram_id} (id={referrer.id})")
                    finally:
                        # Always release referral lock
                        release_referral_lock(referrer_id)
                elif user.referred_by_id:
                    logger.info(f"Referral reward already given for user {user.telegram_id} (id={user.id})")
                else:
                    logger.info(f"User {user.telegram_id} (id={user.id}) has no referrer")
                
                return {
                    'success': True,
                    'user_id': user_id,
                    'registration_gift_given': is_first_registration,
                    'referral_reward_given': user.referral_reward_given if user.referred_by_id else False
                }
        
        finally:
            # Always release reward lock
            release_reward_lock(user_id)
            
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found in task_process_registration_rewards")
        release_reward_lock(user_id)
        return {'error': f'User {user_id} not found', 'failed': True}
    except Exception as e:
        logger.error(f"Error in task_process_registration_rewards: {e}", exc_info=True)
        release_reward_lock(user_id)
        # Retry up to 3 times
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=5)
        return {'error': str(e), 'failed': True}


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
        
        from .models import GameCard, FakeUser, FakeUserGameCard
        from .fake_user_manager import get_fake_user_count_for_game
        
        # Count real players (only those who have selected cards - GameCard)
        real_player_count = GameCard.objects.filter(game=game).count()
        
        # Count current fake users
        fake_user_count = get_fake_user_count_for_game(game)
        
        # Get minimum and maximum system accounts from settings
        from .models import GameSettings
        settings = GameSettings.get_settings()
        min_system_accounts = getattr(settings, 'system_accounts_min', 15)
        max_system_accounts = getattr(settings, 'system_accounts_max', 30)
        
        # FIRST: Ensure we have at least the minimum number of fake users
        # If we're below minimum, add more (this handles cases where some selections failed)
        if fake_user_count < min_system_accounts:
            # Need to add more fake users to reach minimum
            fake_users_needed = min_system_accounts - fake_user_count
            print(f"Game {game_id}: Only {fake_user_count} fake users, need {fake_users_needed} more to reach minimum {min_system_accounts}")
            
            # Add the needed fake users immediately (synchronously to ensure they're added)
            from .fake_user_manager import get_random_fake_users, get_available_card_numbers_for_fake, create_fake_user_card
            import random
            
            # Get fake users that don't already have cards for this game
            existing_fake_user_ids = set(FakeUserGameCard.objects.filter(game=game).values_list('fake_user_id', flat=True))
            all_fake_users = list(FakeUser.objects.filter(is_active=True).exclude(id__in=existing_fake_user_ids))
            
            if len(all_fake_users) >= fake_users_needed:
                # Select random fake users that don't have cards yet
                fake_users_to_add = random.sample(all_fake_users, fake_users_needed)
                
                # Get available cards
                available_cards = get_available_card_numbers_for_fake(game)
                
                if len(available_cards) >= fake_users_needed:
                    # Add cards for these fake users immediately
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
                                
                                # Broadcast card selection (players + watchers rooms)
                                try:
                                    from .game_logic import get_available_card_numbers
                                    broadcast_to_game_rooms(game.id, 'card_selected', {
                                        'card_number': card_number,
                                        'user_id': None,  # Fake user
                                        'username': fake_user.name,
                                        'is_fake': True,
                                        'available_cards': get_available_card_numbers(game)
                                    })
                                except Exception as e:
                                    print(f"WebSocket broadcast error for adjustment fake user card: {e}")
                                
                                print(f"Added fake user {fake_user.name} with card {card_number} to game {game_id}")
                            except Exception as e:
                                print(f"Error adding fake user {fake_user.name}: {e}")
                    
                    # Refresh fake user count after adding
                    fake_user_count = get_fake_user_count_for_game(game)
                else:
                    print(f"Game {game_id}: Not enough available cards ({len(available_cards)}) to add {fake_users_needed} fake users")
            else:
                print(f"Game {game_id}: Not enough available fake users ({len(all_fake_users)}) to add {fake_users_needed}")
        
        # SECOND: Calculate how many fake users to remove (if we have more than needed)
        # For every real player, remove one fake user, BUT never go below minimum
        # Calculate: fake_users_to_remove = min(real_player_count, fake_user_count - min_system_accounts)
        # This ensures we always keep at least min_system_accounts
        max_removable = max(0, fake_user_count - min_system_accounts)
        fake_users_to_remove = min(real_player_count, max_removable)
        
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
                
                # Broadcast card unselection for removed fake users (players + watchers rooms)
                try:
                    from .game_logic import get_available_card_numbers
                    available_cards = get_available_card_numbers(game)
                    for card in cards_to_remove:
                        broadcast_to_game_rooms(game.id, 'card_selected', {
                            'card_number': None,  # None means unselected
                            'user_id': None,
                            'username': card.fake_user.name,
                            'is_fake': True,
                            'available_cards': available_cards
                        })
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
                
                # Broadcast all unselections (players + watchers rooms)
                try:
                    from .game_logic import get_available_card_numbers
                    available_cards = get_available_card_numbers(game)
                    for card in fake_cards:
                        broadcast_to_game_rooms(game.id, 'card_selected', {
                            'card_number': None,
                            'user_id': None,
                            'username': card.fake_user.name,
                            'is_fake': True,
                            'available_cards': available_cards
                        })
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

