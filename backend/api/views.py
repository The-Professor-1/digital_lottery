from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.db.models import Q, Sum
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import Game, GameCard, CalledNumber, Deposit, Transaction, User, Transfer
from .serializers import (
    UserSerializer, GameSerializer, GameCardSerializer, GameCardDetailSerializer,
    DepositSerializer, TransactionSerializer, SelectCardSerializer, MarkNumberSerializer,
    CreateGameSerializer, CallNumberSerializer, CalledNumberSerializer
)
from .game_logic import (
    create_game_card, call_number, mark_number_on_card, claim_bingo,
    start_game as start_game_logic, get_available_card_numbers
)
from .auth_utils import get_user_from_token
from .phone_utils import normalize_phone_number, find_user_by_phone

channel_layer = get_channel_layer()


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """User API endpoints"""
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user profile"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def balance(self, request):
        """Get current user balance"""
        # Refresh user from database to get latest balance
        request.user.refresh_from_db()
        balance_value = float(request.user.balance)
        # Return both formats for compatibility
        return Response({
            'balance': balance_value,
            'user_id': request.user.id,
            'username': request.user.username
        })


@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint to wake machines and verify app is running"""
    return Response({'status': 'ok', 'message': 'Service is healthy'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def authenticate_telegram(request):
    """Authenticate user from Telegram Web App init data"""
    init_data = request.data.get('init_data', '')
    token = request.data.get('token', '')  # Fallback for backward compatibility
    
    # Try initData verification first
    if init_data:
        from api.telegram_auth import verify_telegram_init_data, get_or_create_user_from_telegram
        
        verified_data = verify_telegram_init_data(init_data)
        if verified_data and verified_data.get('user'):
            user = get_or_create_user_from_telegram(verified_data['user'])
            if user:
                # Generate JWT token for the user
                from api.auth_utils import generate_jwt_token
                jwt_token = generate_jwt_token(user)
                serializer = UserSerializer(user)
                return Response({
                    **serializer.data,
                    'token': jwt_token
                })
    
    # Fallback to token-based auth (for backward compatibility)
    if token:
        user = get_user_from_token(token)
        if user:
            serializer = UserSerializer(user)
            return Response(serializer.data)
    
    return Response({'error': 'Invalid init_data or token'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([AllowAny])
def telegram_register(request):
    """Register/authenticate user from Telegram Web App initData"""
    init_data = request.data.get('initData') or request.data.get('init_data', '')
    
    if not init_data:
        return Response({'error': 'initData required'}, status=status.HTTP_400_BAD_REQUEST)
    
    from api.telegram_auth import verify_telegram_init_data, get_or_create_user_from_telegram
    
    verified_data = verify_telegram_init_data(init_data)
    if not verified_data or not verified_data.get('user'):
        return Response({'error': 'Invalid initData signature'}, status=status.HTTP_401_UNAUTHORIZED)
    
    user = get_or_create_user_from_telegram(verified_data['user'])
    if not user:
        return Response({'error': 'Failed to create user'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Generate JWT token
    from api.auth_utils import generate_jwt_token
    jwt_token = generate_jwt_token(user)
    
    serializer = UserSerializer(user)
    return Response({
        'status': 'ok',
        'user_id': user.id,
        'user': serializer.data,
        'token': jwt_token
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def wallet_info(request):
    """Get user wallet balance and recent transactions"""
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')[:10]
    
    return Response({
        'balance': float(request.user.balance),
        'transactions': TransactionSerializer(transactions, many=True).data
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def transfer(request):
    """Transfer money to another user by phone number"""
    to_phone = request.data.get('to_phone', '')
    amount = request.data.get('amount')
    
    if not to_phone or not amount:
        return Response(
            {'error': 'to_phone and amount are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
        
        # Minimum transfer amount (if needed)
        if amount < 1:
            return Response(
                {'error': 'Minimum transfer amount is 1 ETB'},
                status=status.HTTP_400_BAD_REQUEST
            )
    except (ValueError, TypeError):
        return Response(
            {'error': 'Invalid amount'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check balance
    if request.user.balance < amount:
        return Response(
            {'error': 'Insufficient balance'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Normalize phone number (remove 251 country code and add 0)
    normalized_phone = normalize_phone_number(to_phone)
    
    # Find recipient by phone number with backward compatibility
    recipient = find_user_by_phone(to_phone)
    if not recipient:
        return Response(
            {'error': 'User with this phone number not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if recipient.id == request.user.id:
        return Response(
            {'error': 'Cannot transfer to yourself'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Refresh users from DB to get latest balance
    request.user.refresh_from_db()
    recipient.refresh_from_db()
    
    # Perform transfer: First deduct from sender, then add to recipient
    from decimal import Decimal
    amount_decimal = Decimal(str(amount))
    
    # Deduct from sender balance FIRST
    request.user.balance = Decimal(str(request.user.balance)) - amount_decimal
    request.user.save()
    
    # Then add to recipient balance
    recipient.balance = Decimal(str(recipient.balance)) + amount_decimal
    recipient.save()
    
    # Refresh recipient from DB to ensure we have the latest balance
    recipient.refresh_from_db()
    
    # Create Transfer record
    transfer = Transfer.objects.create(
        from_user=request.user,
        to_user=recipient,
        amount=amount_decimal
    )
    
    # Create transaction records
    Transaction.objects.create(
        user=request.user,
        transaction_type='transfer',
        amount=-amount_decimal,  # Negative for sender
        transfer=transfer,
        description=f'Transfer to {recipient.username} ({normalized_phone})'
    )
    
    Transaction.objects.create(
        user=recipient,
        transaction_type='transfer',
        amount=amount_decimal,
        transfer=transfer,
        description=f'Transfer from {request.user.username}'
    )
    
    # Send notification to recipient
    try:
        if recipient.telegram_id:
            from telegram_bot.notifications import send_notification_sync
            import logging
            logger = logging.getLogger(__name__)
            
            # Get the final balance after transfer
            final_balance = recipient.balance
            message = (
                f"💰 ገንዘብ ተቀብለዋል!\n\n"
                f"መጠን: {amount} ብር\n"
                f"ከ: {request.user.username}\n"
                f"አዲስ ሂሳብዎ: {final_balance} ብር"
            )
            logger.info(f"Attempting to send transfer notification to recipient {recipient.telegram_id} (username: {recipient.username})")
            result, _ = send_notification_sync(recipient.telegram_id, message)
            if result:
                logger.info(f"Successfully sent transfer notification to recipient {recipient.telegram_id} (username: {recipient.username})")
            else:
                logger.warning(f"Failed to send transfer notification to recipient {recipient.telegram_id} (username: {recipient.username})")
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Recipient {recipient.username} (ID: {recipient.id}) has no telegram_id, cannot send notification")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error sending transfer notification to recipient {recipient.username} (telegram_id: {recipient.telegram_id}): {e}", exc_info=True)
    
    return Response({
        'success': True,
        'message': f'Transferred {amount} ETB to {recipient.username}',
        'new_balance': float(request.user.balance)
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_notify(request):
    """Send notification to user via Telegram bot"""
    telegram_id = request.data.get('telegram_id')
    message = request.data.get('message', '')
    
    if not telegram_id or not message:
        return Response(
            {'error': 'telegram_id and message are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return Response(
            {'error': 'Invalid telegram_id'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    from telegram_bot.notifications import send_notification_sync
    success, _ = send_notification_sync(telegram_id, message)
    
    if success:
        return Response({
            'success': True,
            'message': 'Notification sent'
        })
    else:
        return Response(
            {'error': 'Failed to send notification'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class GameViewSet(viewsets.ReadOnlyModelViewSet):
    """Game API endpoints"""
    queryset = Game.objects.all()
    serializer_class = GameSerializer
    permission_classes = [AllowAny]  # Allow unauthenticated access for testing

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current active or waiting game"""
        try:
            from django.core.cache import cache
            from .auto_game_manager import check_and_create_new_game
            from .models import GameSettings
            
            # PHASE 2 OPTIMIZATION #1: Multi-level caching with different TTLs
            # Level 1: Short-term cache (1-2 seconds) - Game state (status, basic info)
            # Level 2: Medium-term cache (5 seconds) - Full game data
            # Level 3: Long-term cache (30-60 seconds) - Static settings
            
            cache_key = 'game:current'
            cache_key_state = f'game:current:state:{cache_key}'  # For state-only cache
            
            # Try short-term state cache first (1 second TTL)
            # Wrap in try-except to handle Redis connection failures gracefully
            try:
                cached_state = cache.get(cache_key_state)
                if cached_state:
                    game_id = cached_state.get('id')
                    status = cached_state.get('status')
                    if game_id and status == 'active':
                        # Active game - try full data cache
                        cached_data = cache.get(cache_key)
                        if cached_data:
                            return Response(cached_data)
            except Exception as cache_error:
                # Redis connection failed - log and continue without cache
                print(f"WARNING: Cache read failed (will continue without cache): {cache_error}")
            
            # Try medium-term full data cache (5 seconds)
            try:
                cached_data = cache.get(cache_key)
            except Exception as cache_error:
                # Redis connection failed - continue without cache
                print(f"WARNING: Cache read failed (will continue without cache): {cache_error}")
                cached_data = None
            game = None
            
            if cached_data is not None:
                # Check if game still exists and is still current
                game_id = cached_data.get('id')
                if game_id:
                    # Use only() to fetch minimal fields for validation
                    game = Game.objects.filter(id=game_id).only('id', 'status', 'created_at').first()
                    if game and game.status in ['active', 'waiting']:
                        # For active games, return cached data immediately (5-second cache)
                        if game.status == 'active':
                            # Also cache state for faster future checks
                            cache.set(cache_key_state, {'id': game_id, 'status': 'active'}, 1)
                            return Response(cached_data)
                        # For waiting games, continue to check fake users below
            
            # Cache miss or waiting game - fetch from database with optimized query
            if not game:
                # OPTIMIZATION #5: Use select_related and prefetch_related for efficient queries
                game = Game.objects.filter(
                    Q(status='active') | Q(status='waiting')
                ).select_related('winner').prefetch_related('winners').order_by('-created_at').first()
            
            # If no game exists, create a new one
            # CRITICAL: Only create new game if the last completed game finished at least 8 seconds ago
            # This ensures users have time to see the winner banner before a new game is created
            if not game:
                from django.utils import timezone
                from datetime import timedelta
                
                # Check when the last game completed
                last_completed = Game.objects.filter(status='completed').order_by('-completed_at').first()
                
                if last_completed and last_completed.completed_at:
                    time_since_completion = timezone.now() - last_completed.completed_at
                    # Don't create new game if winner banner is still showing (8 seconds)
                    # Add 2 seconds buffer for navigation
                    min_time_since_completion = 10  # 8s banner + 2s buffer
                    
                    if time_since_completion.total_seconds() < min_time_since_completion:
                        # Too soon after completion, return 404 to let frontend handle it
                        return Response({'message': 'No active game'}, status=status.HTTP_404_NOT_FOUND)
                
                # Safe to create new game now
                game = check_and_create_new_game()
                if not game:
                    return Response({'message': 'No active game'}, status=status.HTTP_404_NOT_FOUND)
            
            # Update bet_amount for waiting games to match current settings (if no cards selected yet)
            if game.status == 'waiting' and game.gamecards.count() == 0:
                try:
                    settings = GameSettings.get_settings()
                    if game.bet_amount != settings.bid_amount:
                        game.bet_amount = settings.bid_amount
                        game.save(update_fields=['bet_amount'])
                        # Invalidate cache when game is updated
                        try:
                            cache.delete(cache_key)
                        except Exception:
                            pass  # Ignore cache errors
                except Exception as e:
                    print(f"ERROR: Failed to get settings for bet_amount update: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Ensure fake users are added if system accounts are enabled (for waiting games)
            settings = None
            if game.status == 'waiting':
                try:
                    settings = GameSettings.get_settings()
                    # Use getattr to safely check allow_system_account
                    allow_system_account = getattr(settings, 'allow_system_account', False)
                    if allow_system_account:
                        try:
                            from .fake_user_manager import get_fake_user_count_for_game
                            from .auto_game_manager import add_fake_users_to_game_immediately
                            fake_count = get_fake_user_count_for_game(game)
                            if fake_count == 0:
                                # Add fake users immediately when game is fetched
                                add_fake_users_to_game_immediately(game)
                                # Refresh game and recalculate derash
                                game.refresh_from_db()
                                game.recalculate_derash()
                                # Invalidate cache to get updated game data
                                try:
                                    cache.delete(cache_key)
                                except Exception:
                                    pass  # Ignore cache errors
                        except Exception as e:
                            # If fake user addition fails (e.g., migration not run), log and continue
                            print(f"ERROR: Failed to add fake users to game {game.id}: {e}")
                            import traceback
                            traceback.print_exc()
                            # Continue without fake users - don't crash the endpoint
                except Exception as e:
                    # If settings retrieval fails, log and continue
                    print(f"ERROR: Failed to get settings in current() endpoint: {e}")
                    import traceback
                    traceback.print_exc()
                    # Try to get settings again for timer check
                    try:
                        settings = GameSettings.get_settings()
                    except:
                        settings = None
            
            # Check if timer has elapsed and automatically start game
            # IMPORTANT: Only check timer if fake users have finished selecting (if enabled)
            if game.created_at and settings:
                from django.utils import timezone
                from datetime import timedelta
                elapsed_time = timezone.now() - game.created_at
                timer_seconds = getattr(settings, 'card_selection_timer', 30)
                
                # CRITICAL: Also check grace period to prevent premature starts
                # The grace period ensures users have time to see winner banner and navigate to card selection
                min_game_age_seconds = 10  # 10 second grace period (8s banner + 2s buffer)
                game_age = elapsed_time.total_seconds()
                
                # Only start if BOTH conditions are met:
                # 1. Card selection timer has elapsed
                # 2. Game is old enough (grace period passed)
                if elapsed_time.total_seconds() >= timer_seconds and game_age >= min_game_age_seconds:
                    from .game_logic import start_game
                    from .fake_user_manager import get_fake_user_count_for_game
                    
                    # When timer runs down, always start the game (no matter the player count)
                    # This ensures game starts consistently when timer expires
                    # Note: start_game() will also check grace period, but we check here too to avoid unnecessary calls
                    success = start_game(game)
                    if success:
                        game.refresh_from_db()
                        # Broadcast game started
                        try:
                            from channels.layers import get_channel_layer
                            from asgiref.sync import async_to_sync
                            channel_layer = get_channel_layer()
                            async_to_sync(channel_layer.group_send)(
                                f'game_{game.id}',
                                {
                                    'type': 'game_started',
                                    'data': {
                                        'game_id': game.id,
                                        'started_at': game.started_at.isoformat() if game.started_at else None
                                    }
                                }
                            )
                        except Exception as e:
                            print(f"WebSocket broadcast error: {e}")
                        
                        # Start automatic number calling via NEW Redis-first task
                        # CRITICAL: Use new task_call_next_number instead of old task_auto_call_numbers
                        from .redis_utils import initialize_game_live_state, cleanup_game_live_state
                        from .models import GameSettings
                        from celery import current_app
                        
                        # Clean up any stale state and initialize fresh
                        cleanup_game_live_state(game.id)
                        settings = GameSettings.get_settings()
                        call_interval = settings.time_between_calls or 3
                        
                        # CRITICAL: Verify initialization succeeded
                        init_success = initialize_game_live_state(game.id, "active", call_interval)
                        if not init_success:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.error(f"❌ [AUTO-START] Game {game.id}: Failed to initialize Redis state!")
                            print(f"❌ [AUTO-START] Game {game.id}: Failed to initialize Redis state!")
                            # Don't schedule task if Redis init failed - skip to next iteration
                            success = False
                        else:
                            # Verify state was set (double-check)
                            from .redis_utils import get_game_live_state
                            verify_state = get_game_live_state(game.id)
                            if not verify_state or len(verify_state) == 0:
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.error(f"❌ [AUTO-START] Game {game.id}: Redis state verification failed!")
                                print(f"❌ [AUTO-START] Game {game.id}: Redis state verification failed!")
                                # Don't schedule task if state not verified
                                success = False
                            else:
                                import logging
                                logger = logging.getLogger(__name__)
                                logger.info(f"✅ [AUTO-START] Game {game.id}: Redis state initialized and verified: {verify_state}")
                                print(f"✅ [AUTO-START] Game {game.id}: Redis state initialized and verified")
                                
                                # Schedule first call with 3-second delay using explicit task name
                                try:
                                    # Get task by explicit name
                                    task = current_app.tasks.get('api.tasks.task_call_next_number')
                                    if not task:
                                        # Fallback: try importing directly
                                        from .tasks import task_call_next_number
                                        task = task_call_next_number
                                        print(f"⚠️ Auto-started Game {game.id}: Task not found by name, using direct import")
                                    
                                    result = task.apply_async(args=[game.id], countdown=3)
                                    print(f"✅ Auto-started Game {game.id}: Scheduled first number call in 3 seconds (task_id: {result.id}, task_name: {result.name})")
                                    success = True
                                except Exception as e:
                                    print(f"❌ ERROR: Failed to schedule task_call_next_number for auto-started game {game.id}: {e}")
                                    import traceback
                                    traceback.print_exc()
                                    # Fallback
                                    try:
                                        from .tasks import task_call_next_number
                                        task_call_next_number.delay(game.id)
                                        print(f"⚠️ Auto-started Game {game.id}: Used fallback delay() method")
                                        success = True
                                    except Exception as e2:
                                        print(f"❌ CRITICAL: Both apply_async and delay failed for auto-started game: {e2}")
                                        import traceback
                                        traceback.print_exc()
                                        success = False
                elif elapsed_time.total_seconds() >= timer_seconds and game_age < min_game_age_seconds:
                    # Timer elapsed but grace period not passed - log and skip
                    print(f"Game {game.id}: Timer elapsed ({elapsed_time.total_seconds():.1f}s) but grace period not passed ({game_age:.1f}s < {min_game_age_seconds}s). Waiting...")
                    success = False
        
            # Refresh game before returning
            game.refresh_from_db()
            
            # Recalculate derash for WAITING games to ensure accuracy
            # For ACTIVE games, verify consistency but don't recalculate (to avoid desync)
            if game.status == 'waiting':
                # Recalculate derash for waiting games to ensure accuracy
                # This ensures derash includes fake users even when game is waiting
                game.recalculate_derash()
                game.refresh_from_db()
            elif game.status == 'active':
                # For active games, verify consistency between derash and player count
                # If there's a mismatch, fix it (but this should rarely happen)
                from decimal import Decimal
                from .models import GameSettings
                settings = GameSettings.get_settings()
                bid_amount = Decimal(str(settings.bid_amount))
                percentage_cut = Decimal(str(settings.percentage_cut))
                
                # Get actual player count
                actual_player_count = game.total_players
                
                # Calculate expected derash based on actual player count
                expected_derash = (Decimal(str(actual_player_count)) * bid_amount) - ((Decimal(str(actual_player_count)) * bid_amount * percentage_cut) / Decimal('100'))
                
                # Check if derash matches player count (allow small rounding differences)
                if abs(game.derash_amount - expected_derash) > Decimal('0.01'):
                    # Mismatch detected - fix it
                    print(f"WARNING: Derash/player count mismatch in active game {game.id}. Players: {actual_player_count}, Derash: {game.derash_amount}, Expected: {expected_derash}. Fixing...")
                    game.derash_amount = expected_derash
                    game.save(update_fields=['derash_amount'])
                    game.refresh_from_db()
            
            serializer = self.get_serializer(game)
            game_data = serializer.data
            
            # PHASE 2 OPTIMIZATION #1: Multi-level caching
            # Cache state (minimal data) for 1 second - for quick status checks
            # Wrap in try-except to handle Redis connection failures gracefully
            try:
                cache.set(cache_key_state, {
                    'id': game.id,
                    'status': game.status,
                    'created_at': game.created_at.isoformat() if game.created_at else None
                }, 1)
                
                # Cache full game data for 5 seconds (medium-term cache)
                cache.set(cache_key, game_data, 5)
            except Exception as cache_error:
                # Redis connection failed - log but don't crash
                print(f"WARNING: Cache write failed (game data still returned): {cache_error}")
            
            return Response(game_data)
        except Exception as e:
            # Log the full error for debugging
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            error_trace = traceback.format_exc()
            logger.error(f"ERROR in /api/games/current/: {str(e)}\n{error_trace}")
            print(f"ERROR in /api/games/current/: {str(e)}")
            print(error_trace)
            
            # Try to return a graceful error response
            # If we can at least get a game, return it even if there was an error
            try:
                game = Game.objects.filter(
                    Q(status='active') | Q(status='waiting')
                ).order_by('-created_at').first()
                if game:
                    serializer = self.get_serializer(game)
                    return Response(serializer.data)
            except:
                pass
            
            # If all else fails, return a 500 error with details
            return Response(
                {'error': 'Internal server error while fetching game', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def select_card(self, request, pk=None):
        """User selects a card for a game"""
        try:
            game = self.get_object()
            
            # Require authentication - no anonymous users allowed
            if not request.user.is_authenticated:
                return Response(
                    {'error': 'Authentication required. Please login through Telegram.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            user = request.user
            # Refresh user from database to get latest balance
            user.refresh_from_db()
            # Allow card reselection - create_game_card will handle it
            
            if game.status != 'waiting':
                return Response(
                    {'error': 'Game is not accepting card selections'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            serializer = SelectCardSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {'error': 'Invalid card number', 'details': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            card_number = serializer.validated_data['card_number']
            
            # Validate card number against settings
            from .models import GameSettings
            settings = GameSettings.get_settings()
            if card_number < 1 or card_number > settings.total_cards:
                return Response(
                    {'error': f'Card number must be between 1 and {settings.total_cards}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Race condition protection: Try to lock card selection with Redis
            from .redis_utils import lock_card_selection, release_card_lock
            lock_success, locked_by = lock_card_selection(card_number, user.id)
            if not lock_success:
                return Response(
                    {'error': f'ይህ ካርቴላ ተይዟል!'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                # Check if user already has this exact card (unselection case)
                existing_card = GameCard.objects.filter(game=game, user=user, card_number=card_number).first()
                
                if existing_card:
                    # User is unselecting the same card - refund and delete
                    from decimal import Decimal
                    from .models import Transaction
                    
                    # Refund the bet amount
                    bet_amount = Decimal(str(game.bet_amount))
                    user.balance = Decimal(str(user.balance)) + bet_amount
                    user.save()
                    
                    # Delete the card first
                    existing_card.delete()
                    
                    # Recalculate derash instead of manually subtracting
                    # This ensures fake users are included in the calculation
                    game.recalculate_derash()
                    
                    # Create refund transaction
                    Transaction.objects.create(
                        user=user,
                        transaction_type='bet',
                        amount=bet_amount,
                        game=game,
                        description=f'Refund for unselecting card {card_number} in game {game.id}'
                    )
                    
                    # CRITICAL: Add one fake user back when real player unselects card
                    try:
                        from .fake_user_manager import adjust_fake_users_for_real_player_change
                        adjust_fake_users_for_real_player_change(game, is_selection=False)
                    except Exception as e:
                        print(f"Error adjusting fake users on card unselection: {e}")
                    
                    # Invalidate game cache when derash changes
                    from django.core.cache import cache as django_cache
                    if django_cache:
                        django_cache.delete('game:current')
                    
                    # Broadcast card unselection
                    try:
                        from .game_logic import get_available_card_numbers
                        async_to_sync(channel_layer.group_send)(
                            f'game_{game.id}',
                            {
                                'type': 'card_selected',
                                'data': {
                                    'card_number': None,  # Indicates unselection
                                    'user_id': user.id,
                                    'username': user.username,
                                    'available_cards': get_available_card_numbers(game)
                                }
                            }
                        )
                    except Exception as e:
                        print(f"WebSocket broadcast error: {e}")
                    
                    # Release card lock on unselection
                    from .redis_utils import release_card_lock
                    release_card_lock(card_number)
                    
                    # Return success with no card (unselected)
                    return Response({
                        'unselected': True,
                        'message': 'Card unselected and refunded',
                        'balance': float(user.balance)
                    }, status=status.HTTP_200_OK)
                
                # User is selecting a card (new or different) - create card directly
                # Use create_game_card which handles payment and validation
                from .game_logic import create_game_card
                
                try:
                    # IMPORTANT: Create real user card FIRST to reserve the card number
                    # This prevents fake users from selecting the same card
                    card = create_game_card(game, user, card_number)
                    
                    # CRITICAL: Remove one fake user when real player selects card
                    # This happens AFTER card is created to ensure real user card is stable
                    try:
                        from .fake_user_manager import adjust_fake_users_for_real_player_change
                        adjust_fake_users_for_real_player_change(game, is_selection=True)
                    except Exception as e:
                        print(f"Error adjusting fake users on card selection: {e}")
                    
                    # Card already created above - just refresh and recalculate
                    # Refresh game to get latest state (including fake users)
                    game.refresh_from_db()
                    
                    # Recalculate derash to include both real and fake users
                    game.recalculate_derash()
                    
                    # Serialize the card
                    serializer = GameCardSerializer(card)
                    # Include balance in response for real-time update
                    user.refresh_from_db()
                    response_data = serializer.data
                    response_data['balance'] = float(user.balance)
                    # Include available cards in response (includes fake user cards)
                    from .game_logic import get_available_card_numbers
                    response_data['available_cards'] = get_available_card_numbers(game)
                    
                    # Broadcast card selection via WebSocket
                    try:
                        async_to_sync(channel_layer.group_send)(
                            f'game_{game.id}',
                            {
                                'type': 'card_selected',
                                'data': {
                                    'card_number': card_number,
                                    'user_id': user.id,
                                    'username': user.username,
                                    'available_cards': response_data['available_cards']
                                }
                            }
                        )
                    except Exception as e:
                        print(f"WebSocket broadcast error: {e}")
                    
                    return Response(response_data, status=status.HTTP_201_CREATED)
                except ValueError as e:
                    # Validation error - re-raise to be caught by outer handler
                    raise
            except ValueError as e:
                # Release lock on error
                from .redis_utils import release_card_lock
                release_card_lock(card_number)
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                # Release lock on error
                from .redis_utils import release_card_lock
                release_card_lock(card_number)
                import traceback
                print(f"Error creating card: {e}")
                print(traceback.format_exc())
                return Response(
                    {'error': str(e), 'type': type(e).__name__},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            finally:
                # Ensure lock is released after card creation (or on any exception)
                # Note: Lock will auto-expire after 2 seconds anyway, but explicit release is cleaner
                pass
        except Exception as e:
            import traceback
            print(f"Error in select_card: {e}")
            print(traceback.format_exc())
            return Response(
                {'error': str(e), 'type': type(e).__name__},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def my_card(self, request, pk=None):
        """Get user's card for current game"""
        from django.core.cache import cache
        
        game = self.get_object()
        
        # Require authentication - no anonymous users allowed
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required. Please login through Telegram.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        user = request.user
        
        # Try to get from cache first
        cache_key = f'card:{game.id}:{user.id}'
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)
        
        # Cache miss - fetch from database
        card = GameCard.objects.filter(game=game, user=user).first()
        
        if not card:
            return Response({'message': 'No card selected for this game'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = GameCardDetailSerializer(card)
        card_data = serializer.data
        
        # Cache the card data for 2 seconds (short TTL for real-time updates)
        cache.set(cache_key, card_data, 2)
        
        return Response(card_data)

    @action(detail=True, methods=['get'])
    def available_cards(self, request, pk=None):
        """Get list of available card numbers"""
        game = self.get_object()
        available = get_available_card_numbers(game)
        return Response({'available_cards': available})


class GameCardViewSet(viewsets.ReadOnlyModelViewSet):
    """Game Card API endpoints"""
    queryset = GameCard.objects.all()
    serializer_class = GameCardDetailSerializer
    permission_classes = [AllowAny]  # Allow for testing

    @action(detail=True, methods=['post'])
    def mark_number(self, request, pk=None):
        """Mark a number on user's card when called"""
        card = self.get_object()
        
        # Require authentication - no anonymous users allowed
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required. Please login through Telegram.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Verify card belongs to authenticated user
        if card.user != request.user:
            return Response(
                {'error': 'This card does not belong to you'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = MarkNumberSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        number = serializer.validated_data['number']
        
        # Check if number was called in the game (REDIS-FIRST: check Redis, not DB)
        game = card.game
        from .redis_utils import get_called_numbers_from_redis
        called_numbers = get_called_numbers_from_redis(game.id)
        
        # If Redis unavailable, fallback to DB (shouldn't happen, but safety)
        if called_numbers is None:
            if not CalledNumber.objects.filter(game=game, number=number).exists():
                return Response(
                    {'error': 'This number has not been called yet'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        elif number not in called_numbers:
            return Response(
                {'error': 'This number has not been called yet'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Mark number on card
        success = mark_number_on_card(card, number)
        
        if success:
            serializer = GameCardDetailSerializer(card)
            return Response(serializer.data)
        else:
            return Response(
                {'error': 'Number not found on your card'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def update_mode(self, request, pk=None):
        """Update game mode (manual/automatic) for user's card"""
        card = self.get_object()
        
        # Require authentication
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required. Please login through Telegram.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Verify card belongs to authenticated user
        if card.user != request.user:
            return Response(
                {'error': 'This card does not belong to you'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        mode = request.data.get('mode', '').strip().lower()
        if mode not in ['manual', 'automatic']:
            return Response(
                {'error': 'Invalid mode. Must be "manual" or "automatic"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if automatic mode is enabled
        from .models import GameSettings
        settings = GameSettings.get_settings()
        if mode == 'automatic' and not settings.automatic_mode_enabled:
            return Response(
                {'error': 'Automatic mode is disabled by administrator'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update mode_history
        mode_history = card.mode_history or []
        mode_history.append({
            'mode': mode,
            'timestamp': timezone.now().isoformat()
        })
        card.mode_history = mode_history
        card.save(update_fields=['mode_history'])
        
        return Response({
            'success': True,
            'mode': mode,
            'message': f'Mode updated to {mode}'
        }, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['post'])
    def claim_bingo(self, request, pk=None):
        """User claims BINGO"""
        card = self.get_object()
        
        # Require authentication - no anonymous users allowed
        if not request.user.is_authenticated:
            return Response(
                {'error': 'Authentication required. Please login through Telegram.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Verify card belongs to authenticated user
        if card.user != request.user:
            return Response(
                {'error': 'This card does not belong to you'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        game = card.game
        
        # Check if game is active OR was just completed (within 1 second) to allow simultaneous claims
        # The claim_bingo function will handle the detailed validation
        if game.status not in ['active', 'completed']:
            return Response(
                {'error': 'Game is not active'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If game is completed, check if it was very recent (within 1 second)
        if game.status == 'completed':
            from datetime import timedelta
            if game.completed_at:
                time_since_completion = timezone.now() - game.completed_at
                if time_since_completion > timedelta(seconds=1):
                    return Response(
                        {'error': 'በሌላ ተጫዋች ተቀድመዋል!'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                # Game completed but no timestamp, reject
                return Response(
                    {'error': 'በሌላ ተጫዋች ተቀድመዋል!'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Process BINGO claim
        # Refresh card from database to get latest state
        card.refresh_from_db()
        
        try:
            success, winning_pattern = claim_bingo(card, game)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            import traceback
            print(f"Error in claim_bingo: {e}")
            print(traceback.format_exc())
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        if success:
            # Refresh game and card to get latest state
            game.refresh_from_db()
            card.refresh_from_db()
            
            # Get current winners from Redis (may not include all yet, but gives immediate response)
            from .redis_utils import get_bingo_winners
            from .game_logic import check_bingo
            
            redis_winners = get_bingo_winners(game.id)
            winner_card_ids = [w['card_id'] for w in redis_winners] if redis_winners else [card.id]
            
            # Get winner cards from database
            all_winner_cards = list(GameCard.objects.filter(
                id__in=winner_card_ids,
                game=game,
                is_winner=True
            ).select_related('user'))
            
            # If no cards yet, use current card
            if not all_winner_cards:
                all_winner_cards = [card]
            
            winner_count = len(all_winner_cards)
            total_prize = game.total_derash
            prize_per_winner = float(total_prize) / winner_count if winner_count > 0 else 0.0
            
            # CRITICAL FIX: Get the actual winning number (the number that completed the bingo)
            # This is the number that should be highlighted, not just the last number called
            from .redis_utils import get_called_numbers_list_from_redis
            from .game_logic import get_winning_number
            called_numbers_list = get_called_numbers_list_from_redis(game.id)
            
            # Find the number that completed the bingo pattern
            winning_number = get_winning_number(card, winning_pattern, called_numbers_list)
            if not winning_number:
                # Fallback to last called number if we can't determine the winning number
                winning_number = called_numbers_list[-1] if called_numbers_list else None
            
            # Prepare all winners data with their cards
            winners_data = []
            for winner_card in all_winner_cards:
                # Recalculate winning pattern for each card
                has_bingo, pattern = check_bingo(winner_card, game)
                # Find winning number for this card's pattern
                card_winning_number = get_winning_number(winner_card, pattern if has_bingo else winning_pattern, called_numbers_list)
                if not card_winning_number:
                    card_winning_number = winning_number  # Use primary winner's number as fallback
                
                winners_data.append({
                    'winner': UserSerializer(winner_card.user).data,
                    'card_number': winner_card.card_number,
                    'card_id': winner_card.id,
                    'card_layout': winner_card.card_layout,
                    'winning_pattern': pattern if has_bingo else winning_pattern,
                    'prize': prize_per_winner,
                    'last_called_number': card_winning_number,  # The number that completed this card's bingo
                    'called_numbers': called_numbers_list
                })
            
            # Broadcast all winners with card info (async task will rebroadcast after 1 second with final count)
            try:
                async_to_sync(channel_layer.group_send)(
                    f'game_{game.id}',
                    {
                        'type': 'winner_declared',
                        'data': {
                            'winners': winners_data,
                            'winner': UserSerializer(card.user).data,  # Primary winner for backward compatibility
                            'card_number': card.card_number,
                            'card_id': card.id,
                            'card_layout': card.card_layout,
                            'winning_pattern': winning_pattern,
                            'prize': prize_per_winner,
                            'total_prize': float(total_prize),
                            'winner_count': winner_count,
                            'last_called_number': winning_number,  # The number that completed the bingo
                            'called_numbers': called_numbers_list
                        }
                    }
                )
            except Exception as e:
                print(f"WebSocket broadcast error: {e}")
            
            # CRITICAL FIX: Also broadcast game_ended event to ensure all users see the game as completed
            # This ensures the frontend properly redirects after the winner banner
            try:
                game.refresh_from_db()  # Ensure we have the latest game status
                if game.status == 'completed':
                    async_to_sync(channel_layer.group_send)(
                        f'game_{game.id}',
                        {
                            'type': 'game_ended',
                            'data': {
                                'game_id': game.id,
                                'status': 'completed',
                                'completed_at': game.completed_at.isoformat() if game.completed_at else None,
                                'winner': UserSerializer(card.user).data,
                                'winner_count': winner_count
                            }
                        }
                    )
            except Exception as e:
                print(f"WebSocket broadcast error (game_ended): {e}")
            
            # Note: Final prize distribution and rebroadcast happens in async task after 1 second
            
            return Response({
                'success': True,
                'message': 'BINGO! You won!',
                'prize': prize_per_winner,
                'total_prize': float(total_prize),
                'winner_count': winner_count,
                'winners': winners_data,
                'winner': UserSerializer(card.user).data,
                'note': 'Final prize may adjust if more winners join within 1 second'
            })
        else:
            return Response(
                {'error': 'Invalid BINGO claim. Pattern not complete. Make sure you have marked all numbers in a line.'},
                status=status.HTTP_400_BAD_REQUEST
            )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def deposit(request):
    """Submit deposit request"""
    amount = request.data.get('amount')
    bank_text = request.data.get('bank_text', '')
    
    if not amount or not bank_text:
        return Response(
            {'error': 'Amount and bank_text are required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except (ValueError, TypeError):
        return Response(
            {'error': 'Invalid amount'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    deposit = Deposit.objects.create(
        user=request.user,
        amount=amount,
        bank_text=bank_text,
        status='pending'
    )
    
    serializer = DepositSerializer(deposit)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def withdraw(request):
    """Request withdrawal"""
    amount = request.data.get('amount')
    
    if not amount:
        return Response(
            {'error': 'Amount is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except (ValueError, TypeError):
        return Response(
            {'error': 'Invalid amount'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if request.user.balance < amount:
        return Response(
            {'error': 'በቂ ሂሳብ የሎትም'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # For now, just create a transaction record
    # In production, create a withdrawal request model
    transaction = Transaction.objects.create(
        user=request.user,
        transaction_type='withdraw',
        amount=amount,
        description=f'Withdrawal request: {amount}'
    )
    
    # Deduct balance (in production, hold it until admin approves)
    from decimal import Decimal
    request.user.balance = Decimal(str(request.user.balance)) - Decimal(str(amount))
    request.user.save()
    
    serializer = TransactionSerializer(transaction)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


# Admin API endpoints
@api_view(['GET'])
@permission_classes([IsAdminUser])
def pending_deposits(request):
    """Get pending deposits for admin"""
    deposits = Deposit.objects.filter(status='pending').order_by('-created_at')
    serializer = DepositSerializer(deposits, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def verify_deposit(request, deposit_id):
    """Admin verifies deposit by matching texts"""
    deposit = get_object_or_404(Deposit, id=deposit_id)
    admin_text = request.data.get('admin_text', '')
    
    if not admin_text:
        return Response(
            {'error': 'admin_text is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    deposit.admin_text = admin_text
    
    if deposit.match_texts():
        deposit.status = 'approved'
        deposit.matched_at = timezone.now()
        deposit.save()
        
        # Credit user balance
        from decimal import Decimal
        deposit.user.balance = Decimal(str(deposit.user.balance)) + Decimal(str(deposit.amount))
        deposit.user.save()
        
        # Create transaction
        Transaction.objects.create(
            user=deposit.user,
            transaction_type='deposit',
            amount=deposit.amount,
            deposit=deposit,
            description=f'Deposit approved - Match ID: {deposit.id}'
        )
        
        serializer = DepositSerializer(deposit)
        return Response(serializer.data)
    else:
        return Response(
            {'error': 'Texts do not match'},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['POST'])
@permission_classes([IsAdminUser])
def create_game(request):
    """Admin creates a new game"""
    serializer = CreateGameSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    bet_amount = serializer.validated_data['bet_amount']
    
    game = Game.objects.create(
        status='waiting',
        bet_amount=bet_amount,
        derash_amount=0
    )
    
    serializer = GameSerializer(game)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([AllowAny])  # Allow automatic start from frontend
def start_game(request, game_id):
    """Start a game (can be called by admin or automatically)"""
    try:
        game = get_object_or_404(Game, id=game_id)
        
        # Check if game is already active
        if game.status == 'active':
            serializer = GameSerializer(game)
            return Response(serializer.data)
        
        # Check if game is completed
        if game.status == 'completed':
            return Response(
                {'error': 'Game is already completed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Allow starting game even without players - users can watch
        # if game.gamecards.count() == 0:
        #     return Response(
        #         {'error': 'Cannot start game without players'},
        #         status=status.HTTP_400_BAD_REQUEST
        #     )
        
        success = start_game_logic(game)
        
        if success:
            # Refresh game from database
            game.refresh_from_db()
            
            # CRITICAL: Clean up any stale Redis state from previous games
            # This ensures a fresh start even if previous game didn't clean up properly
            from .redis_utils import cleanup_game_live_state
            cleanup_game_live_state(game.id)
            
            # Broadcast game started
            try:
                async_to_sync(channel_layer.group_send)(
                    f'game_{game.id}',
                    {
                        'type': 'game_started',
                        'data': {
                            'game_id': game.id,
                            'started_at': game.started_at.isoformat() if game.started_at else None
                        }
                    }
                )
            except Exception as e:
                print(f"WebSocket broadcast error: {e}")
            
            # Initialize Redis live state (Redis-first architecture)
            from .redis_utils import initialize_game_live_state
            from .models import GameSettings
            settings = GameSettings.get_settings()
            call_interval = settings.time_between_calls or 3
            
            # Initialize Redis as source of truth for this game (fresh state)
            # CRITICAL: Verify initialization succeeded before scheduling tasks
            init_success = initialize_game_live_state(game.id, "active", call_interval)
            if not init_success:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"❌ [START GAME] Game {game.id}: Failed to initialize Redis state!")
                print(f"❌ [START GAME] Game {game.id}: Failed to initialize Redis state!")
                return Response(
                    {'error': 'Failed to initialize game state'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Verify state was set (double-check)
            from .redis_utils import get_game_live_state
            verify_state = get_game_live_state(game.id)
            if not verify_state or len(verify_state) == 0:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"❌ [START GAME] Game {game.id}: Redis state verification failed - state is empty after initialization!")
                print(f"❌ [START GAME] Game {game.id}: Redis state verification failed!")
                return Response(
                    {'error': 'Game state initialization failed'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"✅ [START GAME] Game {game.id}: Redis state initialized and verified: {verify_state}")
            print(f"✅ [START GAME] Game {game.id}: Redis state initialized and verified")
            
            # Start automatic number calling via NEW Redis-first task
            # This is freeze-proof: fast, no locks, no DB queries during gameplay
            # CRITICAL: Schedule first call with 3-second delay to match frontend countdown
            # CRITICAL: Use explicit task name to ensure Celery can find and route it
            from celery import current_app
            try:
                # Get task by explicit name
                task = current_app.tasks.get('api.tasks.task_call_next_number')
                if not task:
                    # Fallback: try importing directly
                    from .tasks import task_call_next_number
                    task = task_call_next_number
                    print(f"⚠️ Game {game.id}: Task not found by name, using direct import")
                
                result = task.apply_async(args=[game.id], countdown=3)
                print(f"✅ Game {game.id}: Scheduled first number call in 3 seconds (task_id: {result.id}, task_name: {result.name})")
                # Also log to Django logger for better visibility
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Game {game.id}: Scheduled task_call_next_number with task_id {result.id}, countdown=3, task_name={result.name}")
            except Exception as e:
                print(f"❌ ERROR: Failed to schedule task_call_next_number for game {game.id}: {e}")
                import traceback
                traceback.print_exc()
                # Fallback: try direct delay
                try:
                    from .tasks import task_call_next_number
                    task_call_next_number.delay(game.id)
                    print(f"⚠️ Game {game.id}: Used fallback delay() method")
                except Exception as e2:
                    print(f"❌ CRITICAL: Both apply_async and delay failed: {e2}")
                    import traceback
                    traceback.print_exc()
            
            serializer = GameSerializer(game)
            return Response(serializer.data)
        else:
            return Response(
                {'error': 'Cannot start game. Game may not be in waiting status or has no players.'},
                status=status.HTTP_400_BAD_REQUEST
            )
    except Exception as e:
        import traceback
        print(f"Error in start_game endpoint: {e}")
        print(traceback.format_exc())
        return Response(
            {'error': str(e), 'type': type(e).__name__},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAdminUser])
def call_number_admin(request, game_id):
    """Admin calls a number in a game"""
    game = get_object_or_404(Game, id=game_id)
    
    if game.status != 'active':
        return Response(
            {'error': 'Game is not active'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = CallNumberSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    number = serializer.validated_data['number']
    
    try:
        from .tasks import task_call_number
        
        # Trigger background task to call number
        task = task_call_number.delay(game_id, number)
        
        # Wait for result with timeout
        try:
            result = task.get(timeout=5)  # 5 second timeout
            if result.get('error'):
                return Response({'error': result['error']}, status=status.HTTP_400_BAD_REQUEST)
            
            # CRITICAL FIX: Always return number and letter, even if called_number query fails
            # Get the called number from database or use result data
            called_number = CalledNumber.objects.filter(game=game, number=number).first()
            if called_number:
                serializer = CalledNumberSerializer(called_number)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            else:
                # Fallback: Use result data or get letter from number
                letter = result.get('letter')
                if not letter:
                    # Get letter from number if not in result
                    letter = CalledNumber.get_letter_for_number(number)
                
                return Response({
                    'number': result.get('number', number),
                    'letter': letter or CalledNumber.get_letter_for_number(number),
                    'call_count': result.get('call_count', game.current_call_count)
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            # Task started but result not available yet - get number and letter from request
            # CRITICAL FIX: Always return number and letter, even if task result unavailable
            from .models import CalledNumber
            letter = CalledNumber.get_letter_for_number(number)
            return Response({
                'number': number,
                'letter': letter,
                'message': 'Number call initiated',
                'task_id': task.id
            }, status=status.HTTP_202_ACCEPTED)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@csrf_exempt
def restart_game(request):
    """Restart game endpoint - sends message, optionally refunds/cancels game (Admin only)"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        from decimal import Decimal
        from .models import GameSettings, Transaction, AdminMessage
        from django.utils import timezone
        from datetime import timedelta
        import time
        
        # Parse JSON body
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        message = body.get('message', '').strip()
        refund = body.get('refund', False)
        cancel = body.get('cancel', False)
        
        # Get settings
        settings = GameSettings.get_settings()
        
        # Get current active or waiting game
        current_game = Game.objects.filter(status__in=['waiting', 'active']).first()
        
        if not current_game:
            return JsonResponse({
                'error': 'No active or waiting game found'
            }, status=404)
        
        game_id = current_game.id
        bet_amount = current_game.bet_amount
        
        # Create admin message if provided
        admin_message = None
        if message:
            admin_message = AdminMessage.objects.create(
                game=current_game,
                message=message,
                show_refund=refund,
                show_cancel=cancel,
                expires_at=timezone.now() + timedelta(minutes=5)
            )
            
            # Broadcast message to all players via WebSocket
            try:
                async_to_sync(channel_layer.group_send)(
                    f'game_{game_id}',
                    {
                        'type': 'admin_message',
                        'data': {
                            'message': message,
                            'refund': refund,
                            'cancel': cancel
                        }
                    }
                )
            except Exception as e:
                print(f"WebSocket broadcast error: {e}")
        
        # If both refund and cancel are True, wait 5 seconds then process
        if refund and cancel and message:
            # Use Celery task instead of threading for better reliability
            from .tasks import task_refund_and_cancel_game
            task_refund_and_cancel_game.apply_async(args=[game_id, bet_amount], countdown=5)
            
            return JsonResponse({
                'message': 'Message sent. Refund and cancel will be processed in 5 seconds.',
                'message_sent': True
            }, status=200)
        
        # If only refund (no cancel)
        elif refund:
            cards = GameCard.objects.filter(game=current_game).select_related('user')
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
                    description=f'Refund for game {game_id}'
                )
                refunded_count += 1
            
            if admin_message:
                admin_message.refund_processed = True
                admin_message.save()
            
            return JsonResponse({
                'message': f'Message sent and refunded {refunded_count} player(s).',
                'refunded_count': refunded_count
            }, status=200)
        
        # If only cancel (no refund)
        elif cancel:
            # If there's a message, wait 3 seconds then cancel (similar to refund+cancel)
            if message:
                # Use Celery task to cancel game after delay
                from .tasks import task_cancel_game
                task_cancel_game.apply_async(args=[game_id], countdown=3)
                
                return JsonResponse({
                    'message': 'Message sent. Game will be cancelled in 3 seconds.',
                    'message_sent': True
                }, status=200)
            else:
                # No message, cancel immediately
                # Update admin_message first before deleting the game
                if admin_message:
                    admin_message.cancel_processed = True
                    admin_message.save()
                
                # Delete the game (this will cascade delete related objects like AdminMessage if CASCADE is set)
                current_game.delete()
                
                # Create new game
                new_game = Game.objects.create(
                    status='waiting',
                    bet_amount=settings.bid_amount,
                    derash_amount=Decimal('0.00')
                )
                
                from .serializers import GameSerializer
                return JsonResponse({
                    'message': 'Game cancelled. New game created.',
                    'new_game': GameSerializer(new_game).data
                }, status=200)
        
        # Just send message (no refund, no cancel)
        else:
            return JsonResponse({
                'message': 'Message sent to players.',
                'message_sent': True
            }, status=200)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse(
            {'error': str(e)},
            status=500
        )


@csrf_exempt
def send_telegram_message(request):
    """Send message to all users via Telegram bot, optionally add balance"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        from decimal import Decimal
        from .models import Transaction
        from telegram_bot.notifications import send_notification_sync
        
        # Parse JSON body
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        message = body.get('message', '').strip()
        amount = Decimal(str(body.get('amount', 0) or 0))
        
        if not message:
            return JsonResponse({
                'error': 'Message is required'
            }, status=400)
        
        # Create broadcast message record
        from .models import BroadcastMessage, BroadcastMessageRecipient
        from django.utils import timezone
        
        broadcast = BroadcastMessage.objects.create(
            message_text=message,
            amount_added=amount if amount > 0 else None,
            sent_by=request.user if request.user.is_authenticated else None
        )
        
        # Get all users with telegram_id
        users = User.objects.filter(telegram_id__isnull=False)
        sent_count = 0
        credited_count = 0
        
        for user in users:
            try:
                # Send message and get message_id
                success, message_id = send_notification_sync(user.telegram_id, message)
                
                if success and message_id:
                    # Store recipient record with message_id for deletion
                    BroadcastMessageRecipient.objects.create(
                        broadcast=broadcast,
                        user=user,
                        telegram_id=user.telegram_id,
                        message_id=message_id
                    )
                    sent_count += 1
                elif success:
                    # Message sent but no message_id (shouldn't happen, but handle gracefully)
                    sent_count += 1
                
                # Add balance if amount > 0
                if amount > 0:
                    user.refresh_from_db()
                    user.balance = Decimal(str(user.balance)) + amount
                    user.save()
                    
                    Transaction.objects.create(
                        user=user,
                        transaction_type='deposit',
                        amount=amount,
                        description=f'Admin credit: {message[:50]}'
                    )
                    credited_count += 1
            except Exception as e:
                print(f"Error sending to user {user.id}: {e}")
                continue
        
        return JsonResponse({
            'message': f'Message sent to {sent_count} user(s)',
            'sent_count': sent_count,
            'credited_count': credited_count if amount > 0 else 0,
            'broadcast_id': broadcast.id
        }, status=200)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse(
            {'error': str(e)},
            status=500
        )


@csrf_exempt
def delete_broadcast_messages(request, broadcast_id):
    """Delete all messages from a broadcast"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        from .models import BroadcastMessage, BroadcastMessageRecipient
        from telegram import Bot
        from django.conf import settings
        from django.utils import timezone
        
        broadcast = BroadcastMessage.objects.get(id=broadcast_id)
        recipients = BroadcastMessageRecipient.objects.filter(
            broadcast=broadcast,
            deleted=False
        )
        
        if not recipients.exists():
            return JsonResponse({
                'message': 'No messages to delete (already deleted or none sent)',
                'deleted_count': 0
            }, status=200)
        
        # Delete messages via Telegram API
        token = settings.TELEGRAM_BOT_TOKEN
        if not token:
            return JsonResponse({'error': 'TELEGRAM_BOT_TOKEN not set'}, status=500)
        
        bot = Bot(token=token)
        deleted_count = 0
        failed_count = 0
        
        for recipient in recipients:
            try:
                # Delete message via Telegram API
                bot.delete_message(
                    chat_id=recipient.telegram_id,
                    message_id=recipient.message_id
                )
                # Mark as deleted
                recipient.deleted = True
                recipient.deleted_at = timezone.now()
                recipient.save()
                deleted_count += 1
            except Exception as e:
                # Message might already be deleted, or user blocked bot, etc.
                print(f"Error deleting message for user {recipient.user.id}: {e}")
                failed_count += 1
                # Still mark as deleted to avoid retrying
                recipient.deleted = True
                recipient.deleted_at = timezone.now()
                recipient.save()
        
        return JsonResponse({
            'message': f'Deleted {deleted_count} message(s)',
            'deleted_count': deleted_count,
            'failed_count': failed_count
        }, status=200)
        
    except BroadcastMessage.DoesNotExist:
        return JsonResponse({'error': 'Broadcast not found'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse(
            {'error': str(e)},
            status=500
        )


@csrf_exempt
def send_individual_message(request):
    """Send message to a specific user via Telegram bot by phone number or user ID"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        from .phone_utils import find_user_by_phone
        from telegram_bot.notifications import send_notification_sync
        
        # Parse JSON body
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        phone_number = body.get('phone_number', '').strip()
        user_id = body.get('user_id', '').strip()
        message = body.get('message', '').strip()
        
        if not message:
            return JsonResponse({
                'error': 'Message is required'
            }, status=400)
        
        if not phone_number and not user_id:
            return JsonResponse({
                'error': 'Either phone_number or user_id is required'
            }, status=400)
        
        # Find user
        user = None
        if user_id:
            try:
                user_id_int = int(user_id)
                user = User.objects.filter(id=user_id_int).first()
                if not user:
                    return JsonResponse({
                        'error': f'User with ID {user_id} not found'
                    }, status=404)
            except (ValueError, TypeError):
                return JsonResponse({
                    'error': 'Invalid user_id format'
                }, status=400)
        elif phone_number:
            user = find_user_by_phone(phone_number)
            if not user:
                return JsonResponse({
                    'error': f'User with phone number {phone_number} not found'
                }, status=404)
        
        # Check if user has telegram_id
        if not user.telegram_id:
            return JsonResponse({
                'error': f'User {user.username or user.id} does not have a Telegram ID (not registered via Telegram bot)'
            }, status=400)
        
        # Send message
        success, _ = send_notification_sync(user.telegram_id, message)
        
        if success:
            return JsonResponse({
                'success': True,
                'message': f'Message sent to user {user.username or user.id} (Telegram ID: {user.telegram_id})',
                'user_id': user.id,
                'username': user.username,
                'telegram_id': user.telegram_id
            }, status=200)
        else:
            return JsonResponse({
                'error': 'Failed to send message. Please check if the user has blocked the bot or if there is a network issue.'
            }, status=500)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse(
            {'error': str(e)},
            status=500
        )


@api_view(['POST'])
@permission_classes([AllowAny])  # Allow frontend to end game when no winner
def end_game(request, game_id):
    """End a game (can be called by admin or automatically when all numbers called)"""
    game = get_object_or_404(Game, id=game_id)
    
    if game.status != 'active':
        return Response(
            {'error': 'Game is not active'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if all 75 numbers have been called
    called_count = CalledNumber.objects.filter(game=game).count()
    if called_count < 75:
        return Response(
            {'error': 'Cannot end game. Not all numbers have been called yet.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # End game without winner
    game.status = 'completed'
    game.completed_at = timezone.now()
    # game.winner remains None if no one won
    game.save()
    
    # Cleanup Redis keys for this game
    from .redis_utils import cleanup_game_redis_keys
    cleanup_game_redis_keys(game.id)
    
    # Broadcast game ended
    try:
        async_to_sync(channel_layer.group_send)(
            f'game_{game.id}',
            {
                'type': 'game_ended',
                'data': {
                    'game_id': game.id,
                    'completed_at': game.completed_at.isoformat(),
                    'no_winner': True
                }
            }
        )
    except Exception as e:
        print(f"WebSocket broadcast error: {e}")
    
    serializer = GameSerializer(game)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_user_phone(request):
    """Update user phone number"""
    phone_number = request.data.get('phone_number', '').strip()
    
    if not phone_number:
        return Response({'error': 'Phone number required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Normalize phone number (remove 251 country code and add 0)
    normalized_phone = normalize_phone_number(phone_number)
    
    user = request.user
    user.phone_number = normalized_phone
    user.save()
    
    serializer = UserSerializer(user)
    return Response({
        'status': 'ok',
        'user': serializer.data
    })


@api_view(['GET'])
def admin_users_list(request):
    """Get list of all registered users with statistics"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    users = User.objects.filter(telegram_id__isnull=False).order_by('-created_at')
    
    users_data = []
    for user in users:
        # Get user statistics
        games_played = Game.objects.filter(gamecards__user=user).distinct().count()
        wins = Game.objects.filter(winner=user).count()
        deposits = Transaction.objects.filter(user=user, transaction_type='deposit').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        withdrawals = Transaction.objects.filter(user=user, transaction_type='withdrawal').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        users_data.append({
            'id': user.id,
            'username': user.username,
            'telegram_id': user.telegram_id,
            'phone_number': user.phone_number or '',
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'balance': float(user.balance),
            'games_played': games_played,
            'wins': wins,
            'total_deposits': float(deposits),
            'total_withdrawals': float(withdrawals),
            'created_at': user.created_at.isoformat(),
        })
    
    return Response({'users': users_data})


@api_view(['GET'])
def admin_user_detail(request, user_id):
    """Get detailed user information including transaction history"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    user = get_object_or_404(User, id=user_id)
    
    # Get user statistics
    games_played = Game.objects.filter(gamecards__user=user).distinct()
    wins = Game.objects.filter(winner=user)
    deposits = Transaction.objects.filter(user=user, transaction_type='deposit').order_by('-created_at')[:50]
    withdrawals = Transaction.objects.filter(user=user, transaction_type='withdrawal').order_by('-created_at')[:50]
    bets = Transaction.objects.filter(user=user, transaction_type='bet').order_by('-created_at')[:50]
    prizes = Transaction.objects.filter(user=user, transaction_type='prize').order_by('-created_at')[:50]
    
    from .serializers import TransactionSerializer
    
    return Response({
        'user': UserSerializer(user).data,
        'statistics': {
            'games_played': games_played.count(),
            'wins': wins.count(),
            'total_deposits': float(Transaction.objects.filter(user=user, transaction_type='deposit').aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')),
            'total_withdrawals': float(Transaction.objects.filter(user=user, transaction_type='withdrawal').aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')),
        },
        'transactions': {
            'deposits': TransactionSerializer(deposits, many=True).data,
            'withdrawals': TransactionSerializer(withdrawals, many=True).data,
            'bets': TransactionSerializer(bets, many=True).data,
            'prizes': TransactionSerializer(prizes, many=True).data,
        },
        'games': [{'id': g.id, 'status': g.status, 'created_at': g.created_at.isoformat()} for g in games_played[:20]]
    })


@api_view(['PUT', 'PATCH'])
def admin_user_edit(request, user_id):
    """Edit user information"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    user = get_object_or_404(User, id=user_id)
    
    # Allow editing balance, phone_number, username, first_name, last_name
    if 'balance' in request.data:
        user.balance = Decimal(str(request.data['balance']))
    if 'phone_number' in request.data:
        # Normalize phone number (remove 251 country code and add 0)
        normalized_phone = normalize_phone_number(request.data['phone_number'])
        user.phone_number = normalized_phone
    if 'username' in request.data:
        user.username = request.data['username']
    if 'first_name' in request.data:
        user.first_name = request.data['first_name']
    if 'last_name' in request.data:
        user.last_name = request.data['last_name']
    
    user.save()
    
    serializer = UserSerializer(user)
    return Response(serializer.data)


@api_view(['POST'])
def admin_users_delete(request):
    """Delete one or multiple users"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    user_ids = request.data.get('user_ids', [])
    
    if not user_ids or not isinstance(user_ids, list):
        return Response({'error': 'user_ids array required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Prevent deleting superusers
    users_to_delete = User.objects.filter(id__in=user_ids).exclude(is_superuser=True)
    deleted_count = users_to_delete.count()
    
    # Delete users
    users_to_delete.delete()
    
    return Response({
        'message': f'Successfully deleted {deleted_count} user(s)',
        'deleted_count': deleted_count
    })
