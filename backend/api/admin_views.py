from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import datetime, timedelta
from .models import Deposit, Game, CalledNumber, Transaction, User, DepositRequest, WithdrawRequest, GameSettings, Transfer, AdminMessage, SecondAdmin
from django.contrib.auth.hashers import make_password, check_password
from .game_logic import call_number, start_game
from .phone_utils import normalize_phone_number, find_user_by_phone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from telegram_bot.notifications import send_notification_sync
from decimal import Decimal
import json
import calendar

channel_layer = get_channel_layer()


def get_calendar_periods(now):
    """
    Calculate calendar-based date periods (weeks and months).
    Returns a dictionary with all period boundaries.
    """
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Yesterday
    yesterday_start = today_start - timedelta(days=1)
    yesterday_end = today_start
    
    # Current week (Monday to Sunday)
    # Get the day of the week (Monday=0, Sunday=6)
    days_since_monday = now.weekday()
    week_start = today_start - timedelta(days=days_since_monday)
    week_end = week_start + timedelta(days=6)
    week_end = week_end.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Last week (Monday to Sunday of previous week)
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start - timedelta(microseconds=1)
    
    # Current month (1st to last day of current month)
    month_start = today_start.replace(day=1)
    # Get last day of current month
    last_day_of_month = calendar.monthrange(now.year, now.month)[1]
    month_end = today_start.replace(day=last_day_of_month, hour=23, minute=59, second=59, microsecond=999999)
    
    # Last month (1st to last day of previous month)
    if now.month == 1:
        # If current month is January, last month is December of previous year
        last_month_start = datetime(now.year - 1, 12, 1, 0, 0, 0, 0, now.tzinfo)
        last_day_of_last_month = calendar.monthrange(now.year - 1, 12)[1]
        last_month_end = datetime(now.year - 1, 12, last_day_of_last_month, 23, 59, 59, 999999, now.tzinfo)
    else:
        last_month_start = today_start.replace(month=now.month - 1, day=1)
        last_day_of_last_month = calendar.monthrange(now.year, now.month - 1)[1]
        last_month_end = today_start.replace(month=now.month - 1, day=last_day_of_last_month, hour=23, minute=59, second=59, microsecond=999999)
    
    return {
        'today_start': today_start,
        'today_end': today_end,
        'yesterday_start': yesterday_start,
        'yesterday_end': yesterday_end,
        'week_start': week_start,
        'week_end': week_end,
        'last_week_start': last_week_start,
        'last_week_end': last_week_end,
        'month_start': month_start,
        'month_end': month_end,
        'last_month_start': last_month_start,
        'last_month_end': last_month_end,
    }


def format_large_number(value):
    """Format large numbers with k, M, etc. (e.g., 1000 -> 1k, 1500 -> 1.5k)"""
    if value is None:
        return '0'
    
    value = float(value)
    
    if value >= 1000000:
        return f"{value / 1000000:.1f}M".rstrip('0').rstrip('.')
    elif value >= 1000:
        return f"{value / 1000:.1f}k".rstrip('0').rstrip('.')
    else:
        return f"{value:.0f}"


@staff_member_required
def admin_dashboard(request):
    """Admin dashboard view with statistics"""
    now = timezone.now()
    
    # Get calendar-based date periods
    periods = get_calendar_periods(now)
    today_start = periods['today_start']
    today_end = periods['today_end']
    yesterday_start = periods['yesterday_start']
    yesterday_end = periods['yesterday_end']
    week_start = periods['week_start']
    week_end = periods['week_end']
    last_week_start = periods['last_week_start']
    last_week_end = periods['last_week_end']
    month_start = periods['month_start']
    month_end = periods['month_end']
    last_month_start = periods['last_month_start']
    last_month_end = periods['last_month_end']
    
    # Games played statistics
    games_today = Game.objects.filter(created_at__gte=today_start, created_at__lte=today_end).count()
    games_yesterday = Game.objects.filter(created_at__gte=yesterday_start, created_at__lt=yesterday_end).count()
    games_week = Game.objects.filter(created_at__gte=week_start, created_at__lte=week_end).count()
    games_last_week = Game.objects.filter(created_at__gte=last_week_start, created_at__lte=last_week_end).count()
    games_month = Game.objects.filter(created_at__gte=month_start, created_at__lte=month_end).count()
    games_last_month = Game.objects.filter(created_at__gte=last_month_start, created_at__lte=last_month_end).count()
    games_total = Game.objects.count()
    
    # Revenue statistics (percentage cut from each game)
    settings = GameSettings.get_settings()
    percentage_cut = settings.percentage_cut
    
    # Calculate revenue from completed games
    completed_games = Game.objects.filter(status='completed')
    
    def calculate_revenue(games_queryset):
        total = Decimal('0')
        for game in games_queryset:
            total_collected = game.derash_amount
            if total_collected > 0:
                cut = (total_collected * percentage_cut) / Decimal('100')
                total += cut
        return total
    
    revenue_today = calculate_revenue(completed_games.filter(completed_at__gte=today_start, completed_at__lte=today_end))
    revenue_yesterday = calculate_revenue(completed_games.filter(completed_at__gte=yesterday_start, completed_at__lt=yesterday_end))
    revenue_week = calculate_revenue(completed_games.filter(completed_at__gte=week_start, completed_at__lte=week_end))
    revenue_last_week = calculate_revenue(completed_games.filter(completed_at__gte=last_week_start, completed_at__lte=last_week_end))
    revenue_month = calculate_revenue(completed_games.filter(completed_at__gte=month_start, completed_at__lte=month_end))
    revenue_last_month = calculate_revenue(completed_games.filter(completed_at__gte=last_month_start, completed_at__lte=last_month_end))
    revenue_total = calculate_revenue(completed_games)
    
    # Pending requests (limit to 5 for initial display)
    pending_deposits = DepositRequest.objects.filter(status='pending').order_by('-created_at')[:5]
    pending_withdraws = WithdrawRequest.objects.filter(status='pending').order_by('-created_at')[:5]
    
    # Approved requests (limit to 5 for initial display)
    approved_deposits = DepositRequest.objects.filter(status='approved').order_by('-created_at')[:5]
    approved_withdraws = WithdrawRequest.objects.filter(status='approved').order_by('-created_at')[:5]
    
    # Active games
    active_games = Game.objects.filter(status__in=['waiting', 'active']).order_by('-created_at')
    
    # Game settings
    game_settings = GameSettings.get_settings()
    
    # Get today's games with details for clickable total games
    today_games = Game.objects.filter(created_at__gte=today_start).order_by('-created_at')
    today_games_data = []
    for game in today_games:
        # Count automatic vs manual mode usage
        automatic_count = 0
        manual_count = 0
        for card in game.gamecards.all():
            mode_history = card.mode_history or []
            # Check if user used automatic mode at any point
            has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
            if has_automatic:
                automatic_count += 1
            else:
                manual_count += 1
        
        # Get winner phone numbers
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        # Also check winners (ManyToMany)
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        today_games_data.append({
            'game': game,
            'players': game.total_players,
            'bid_amount': game.bet_amount,
            'automatic_count': automatic_count,
            'manual_count': manual_count,
            'winner_phones': winner_phones,
        })
    
    # Get game details for the game detail section (max 200, newest first)
    all_games_detail = Game.objects.all().order_by('-created_at')[:200]
    games_detail_data = []
    for game in all_games_detail:
        # Get winner phone numbers
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        # Count automatic vs manual mode usage
        automatic_count = 0
        manual_count = 0
        for card in game.gamecards.all():
            mode_history = card.mode_history or []
            has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
            if has_automatic:
                automatic_count += 1
            else:
                manual_count += 1
        
        games_detail_data.append({
            'game': game,
            'players': game.total_players,
            'bid_amount': game.bet_amount,
            'derash_amount': game.derash_amount,
            'automatic_count': automatic_count,
            'manual_count': manual_count,
            'winner_phones': winner_phones,
            'called_numbers': list(game.called_numbers.all().values_list('number', flat=True)),
        })
    
    # Get recent transfers
    recent_transfers = Transfer.objects.all().order_by('-created_at')[:50]
    
    # Calculate total statistics
    # Count total automatic and manual games played (at game card level)
    from .models import GameCard
    all_cards = GameCard.objects.all()
    total_automatic_games = 0
    total_manual_games = 0
    
    for card in all_cards:
        mode_history = card.mode_history or []
        # Check if user used automatic mode at any point
        has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
        if has_automatic:
            total_automatic_games += 1
        else:
            total_manual_games += 1
    
    # Get all registered users (with telegram_id - registered through bot) with statistics
    registered_users_raw = User.objects.filter(telegram_id__isnull=False).order_by('-created_at')
    
    registered_users = []
    total_deposits = Decimal('0')  # Sum deposits from registered users list
    for user in registered_users_raw:
        games_played = Game.objects.filter(gamecards__user=user).distinct().count()
        wins = Game.objects.filter(winner=user).count()
        user_total_deposits = Transaction.objects.filter(user=user, transaction_type='deposit').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        user_total_withdrawals = Transaction.objects.filter(user=user, transaction_type='withdraw').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        # Sum this user's deposits to the total
        total_deposits += user_total_deposits
        
        registered_users.append({
            'user': user,
            'games_played': games_played,
            'wins': wins,
            'total_deposits': user_total_deposits,
            'total_withdrawals': user_total_withdrawals,
        })
    
    # Calculate total withdrawals - note: transaction_type is 'withdraw' not 'withdrawal'
    total_withdrawals = Transaction.objects.filter(transaction_type='withdraw').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    
    # Total balance - sum all users' balances (same pattern, no filtering)
    total_balance = User.objects.aggregate(
        total=Sum('balance')
    )['total'] or Decimal('0')
    
    # Format revenue values for display
    revenue_today_formatted = format_large_number(revenue_today)
    revenue_yesterday_formatted = format_large_number(revenue_yesterday)
    revenue_week_formatted = format_large_number(revenue_week)
    revenue_last_week_formatted = format_large_number(revenue_last_week)
    revenue_month_formatted = format_large_number(revenue_month)
    revenue_last_month_formatted = format_large_number(revenue_last_month)
    
    # Date range strings for display
    today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    week_end = today_end
    month_end = today_end
    
    date_today = f"{today_start.strftime('%Y-%m-%d')} to {today_end.strftime('%Y-%m-%d')}"
    date_yesterday = f"{yesterday_start.strftime('%Y-%m-%d')} to {yesterday_end.strftime('%Y-%m-%d')}"
    date_week = f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}"
    date_last_week = f"{last_week_start.strftime('%Y-%m-%d')} to {last_week_end.strftime('%Y-%m-%d')}"
    date_month = f"{month_start.strftime('%Y-%m-%d')} to {month_end.strftime('%Y-%m-%d')}"
    date_last_month = f"{last_month_start.strftime('%Y-%m-%d')} to {last_month_end.strftime('%Y-%m-%d')}"
    
    # Count totals for show more functionality
    pending_deposits_count = DepositRequest.objects.filter(status='pending').count()
    pending_withdraws_count = WithdrawRequest.objects.filter(status='pending').count()
    approved_deposits_count = DepositRequest.objects.filter(status='approved').count()
    approved_withdraws_count = WithdrawRequest.objects.filter(status='approved').count()
    
    # Get second admin credentials (if exists)
    try:
        second_admin = SecondAdmin.objects.first()
        second_admin_username = second_admin.username if second_admin else ''
    except Exception:
        # Handle case where SecondAdmin table doesn't exist yet (migration not run)
        second_admin_username = ''
    
    context = {
        'games_today': games_today,
        'games_yesterday': games_yesterday,
        'games_week': games_week,
        'games_last_week': games_last_week,
        'games_month': games_month,
        'games_last_month': games_last_month,
        'games_total': games_total,
        'revenue_today': revenue_today,
        'revenue_yesterday': revenue_yesterday,
        'revenue_week': revenue_week,
        'revenue_last_week': revenue_last_week,
        'revenue_month': revenue_month,
        'revenue_last_month': revenue_last_month,
        'revenue_total': revenue_total,
        'revenue_today_formatted': revenue_today_formatted,
        'revenue_yesterday_formatted': revenue_yesterday_formatted,
        'revenue_week_formatted': revenue_week_formatted,
        'revenue_last_week_formatted': revenue_last_week_formatted,
        'revenue_month_formatted': revenue_month_formatted,
        'revenue_last_month_formatted': revenue_last_month_formatted,
        'date_today': date_today,
        'date_yesterday': date_yesterday,
        'date_week': date_week,
        'date_last_week': date_last_week,
        'date_month': date_month,
        'date_last_month': date_last_month,
        'pending_deposits': pending_deposits,
        'pending_withdraws': pending_withdraws,
        'approved_deposits': approved_deposits,
        'approved_withdraws': approved_withdraws,
        'pending_deposits_count': pending_deposits_count,
        'pending_withdraws_count': pending_withdraws_count,
        'approved_deposits_count': approved_deposits_count,
        'approved_withdraws_count': approved_withdraws_count,
        'active_games': active_games,
        'game_settings': game_settings,
        'registered_users': registered_users,
        'today_games_data': today_games_data,
        'games_detail_data': games_detail_data,
        'recent_transfers': recent_transfers,
        'total_automatic_games': total_automatic_games,
        'total_manual_games': total_manual_games,
        'total_deposits': total_deposits,
        'total_withdrawals': total_withdrawals,
        'total_balance': total_balance,
        'second_admin_username': second_admin_username,
    }
    return render(request, 'admin/dashboard.html', context)


@require_http_methods(["GET"])
def search_user(request):
    """Search user by phone number"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    phone = request.GET.get('phone', '').strip()
    if not phone:
        return JsonResponse({'error': 'Phone number required'}, status=400)
    
    # Normalize phone number (remove 251 country code and add 0)
    normalized_phone = normalize_phone_number(phone)
    
    try:
        # Search by phone number with backward compatibility
        user = find_user_by_phone(phone)
        
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)
        
        # Get user statistics
        games_played = Game.objects.filter(gamecards__user=user).distinct().count()
        deposits = DepositRequest.objects.filter(user=user, status='approved')
        withdrawals = WithdrawRequest.objects.filter(user=user, status='approved')
        
        deposit_history = deposits.values('amount', 'platform', 'created_at')[:10]
        withdraw_history = withdrawals.values('amount', 'platform', 'created_at')[:10]
        
        return JsonResponse({
            'user': {
                'id': user.id,
                'username': user.username,
                'telegram_id': user.telegram_id,
                'phone_number': user.phone_number,
                'balance': float(user.balance),
                'created_at': user.created_at.isoformat(),
            },
            'games_played': games_played,
            'deposit_history': list(deposit_history),
            'withdraw_history': list(withdraw_history),
        })
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
@require_http_methods(["POST"])
def verify_deposit_api(request, deposit_id):
    """API endpoint for deposit verification"""
    try:
        deposit = Deposit.objects.get(id=deposit_id)
        data = json.loads(request.body)
        admin_text = data.get('admin_text', '')
        
        if not admin_text:
            return JsonResponse({'error': 'admin_text is required'}, status=400)
        
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
            from .models import Transaction
            Transaction.objects.create(
                user=deposit.user,
                transaction_type='deposit',
                amount=deposit.amount,
                deposit=deposit,
                description=f'Deposit approved - Match ID: {deposit.id}'
            )
            
            # Send notification to user via Telegram bot
            if deposit.user.telegram_id:
                message = (
                    f"✅ ገንዘቡ ገቢ ሆኗል!\n\n"
                    f"መጠን: {deposit.amount} ብር\n"
                    f"አዲስ ሂሳብዎ: {deposit.user.balance} ብር"
                )
                send_notification_sync(deposit.user.telegram_id, message)
            
            return JsonResponse({
                'success': True,
                'message': 'Deposit approved and credited'
            })
        else:
            # Reject deposit
            deposit.status = 'rejected'
            deposit.save()
            
            # Send rejection notification
            if deposit.user.telegram_id:
                message = (
                    f"❌ የገንዘብ ማስገባት ጥያቄዎ ተቀባይነት አላገኘም።\n\n"
                    f"መጠን: {deposit.amount} ብር\n"
                    f"እባክዎ እንደገና ይሞክሩ።"
                )
                send_notification_sync(deposit.user.telegram_id, message)
            
            return JsonResponse({
                'success': False,
                'error': 'Texts do not match'
            }, status=400)
    except Deposit.DoesNotExist:
        return JsonResponse({'error': 'Deposit not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
@require_http_methods(["POST"])
def call_number_api(request, game_id):
    """API endpoint for calling a number - now uses Celery background task"""
    try:
        from .tasks import task_call_number
        
        game = Game.objects.get(id=game_id)
        data = json.loads(request.body)
        number = data.get('number')
        
        if not number:
            return JsonResponse({'error': 'number is required'}, status=400)
        
        # Trigger background task to call number
        task = task_call_number.delay(game_id, number)
        
        # Wait for result with timeout (non-blocking for client, but ensures task starts)
        try:
            result = task.get(timeout=5)  # 5 second timeout
            if result.get('error'):
                return JsonResponse({'error': result['error']}, status=400)
            
            return JsonResponse({
                'success': True,
                'number': result.get('number'),
                'letter': result.get('letter'),
                'call_count': result.get('call_count', 0),
                'task_id': task.id
            })
        except Exception as e:
            # Task started but result not available yet - return success
            # The task will complete in background
            return JsonResponse({
                'success': True,
                'message': 'Number call initiated',
                'task_id': task.id
            })
    except Game.DoesNotExist:
        return JsonResponse({'error': 'Game not found'}, status=404)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def approve_deposit_request_api(request, deposit_id):
    """API endpoint to approve a deposit request"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        deposit_request = DepositRequest.objects.get(id=deposit_id, status='pending')
        
        deposit_request.status = 'approved'
        deposit_request.processed_at = timezone.now()
        # Only set processed_by if user is staff (second admin doesn't have a User object)
        deposit_request.processed_by = request.user if request.user.is_staff else None
        deposit_request.save()
        
        # Credit user balance
        deposit_request.user.balance = Decimal(str(deposit_request.user.balance)) + Decimal(str(deposit_request.amount))
        deposit_request.user.save()
        
        # Create transaction
        Transaction.objects.create(
            user=deposit_request.user,
            transaction_type='deposit',
            amount=deposit_request.amount,
            description=f'Deposit approved - {deposit_request.platform} - Request ID: {deposit_request.id}'
        )
        
        # Send notification
        try:
            from telegram_bot.notifications import send_notification_sync
            send_notification_sync(
                deposit_request.user.telegram_id,
                f"✅ ገንዘቡ ገቢ ሆኗል!\n\n"
                f"💰 መጠን: {deposit_request.amount} ብር\n"
                f"🏦 ወደ: {deposit_request.platform}\n\n"
                f"በሂሳብዎ ላይ ያለውን ለመመልከት /balance ይጫኑ።"
            )
        except:
            pass
        
        return JsonResponse({'success': True, 'message': 'Deposit approved and credited'})
    except DepositRequest.DoesNotExist:
        return JsonResponse({'error': 'Deposit request not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def reject_deposit_request_api(request, deposit_id):
    """API endpoint to reject a deposit request"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        deposit_request = DepositRequest.objects.get(id=deposit_id, status='pending')
        deposit_request.status = 'rejected'
        deposit_request.processed_at = timezone.now()
        # Only set processed_by if user is staff (second admin doesn't have a User object)
        deposit_request.processed_by = request.user if request.user.is_staff else None
        deposit_request.save()
        
        # Send notification
        try:
            from telegram_bot.notifications import send_notification_sync
            send_notification_sync(
                deposit_request.user.telegram_id,
                f"❌ የገንዘብ ማስገቢያ ጥያቄዎ ተቀባይነት አላገኘም።\n\n"
                f"እባክዎ እንደገና ይሞክሩ።"
            )
        except:
            pass
        
        return JsonResponse({'success': True, 'message': 'Deposit request rejected'})
    except DepositRequest.DoesNotExist:
        return JsonResponse({'error': 'Deposit request not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def approve_withdraw_request_api(request, withdraw_id):
    """API endpoint to approve a withdraw request"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        withdraw_request = WithdrawRequest.objects.get(id=withdraw_id, status='pending')
        
        # Check balance
        if withdraw_request.user.balance < withdraw_request.amount:
            return JsonResponse({'error': 'Insufficient balance'}, status=400)
        
        withdraw_request.status = 'approved'
        withdraw_request.processed_at = timezone.now()
        # Only set processed_by if user is staff (second admin doesn't have a User object)
        withdraw_request.processed_by = request.user if request.user.is_staff else None
        withdraw_request.save()
        
        # Deduct from user balance
        withdraw_request.user.balance = Decimal(str(withdraw_request.user.balance)) - Decimal(str(withdraw_request.amount))
        withdraw_request.user.save()
        
        # Create transaction
        Transaction.objects.create(
            user=withdraw_request.user,
            transaction_type='withdraw',
            amount=withdraw_request.amount,
            description=f'Withdrawal approved - {withdraw_request.platform} - Request ID: {withdraw_request.id}'
        )
        
        # Send notification
        try:
            from telegram_bot.notifications import send_notification_sync
            send_notification_sync(
                withdraw_request.user.telegram_id,
                f"✅ ገንዘቡ ወጭ ተደርጓል!\n\n"
                f"💰 መጠን: {withdraw_request.amount} ብር\n"
                f"🏦 ወደ: {withdraw_request.platform}\n"
                f"📋 ሂሳብ ባለቤት: {withdraw_request.account_holder_name}\n"
                f"📋 ሂሳብ ቁጥር: {withdraw_request.account_number}\n\n"
            )
        except:
            pass
        
        return JsonResponse({'success': True, 'message': 'Withdrawal approved'})
    except WithdrawRequest.DoesNotExist:
        return JsonResponse({'error': 'Withdraw request not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def reject_withdraw_request_api(request, withdraw_id):
    """API endpoint to reject a withdraw request"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        withdraw_request = WithdrawRequest.objects.get(id=withdraw_id, status='pending')
        withdraw_request.status = 'rejected'
        withdraw_request.processed_at = timezone.now()
        # Only set processed_by if user is staff (second admin doesn't have a User object)
        withdraw_request.processed_by = request.user if request.user.is_staff else None
        withdraw_request.save()
        
        # Send notification
        try:
            from telegram_bot.notifications import send_notification_sync
            send_notification_sync(
                withdraw_request.user.telegram_id,
                f"❌ የገንዘብ ማውጣት ጥያቄዎ ተቀባይነት አላገኘም።\n\n"
                f"እባክዎ እንደገና ይሞክሩ።"
            )
        except:
            pass
        
        return JsonResponse({'success': True, 'message': 'Withdraw request rejected'})
    except WithdrawRequest.DoesNotExist:
        return JsonResponse({'error': 'Withdraw request not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def game_settings_api(request):
    """API endpoint to get and update game settings"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    settings = GameSettings.get_settings()
    
    if request.method == 'GET':
        return JsonResponse({
            'bid_amount': float(settings.bid_amount),
            'card_selection_timer': settings.card_selection_timer,
            'time_between_calls': settings.time_between_calls,
            'total_cards': settings.total_cards,
            'min_withdraw': float(settings.min_withdraw),
            'percentage_cut': float(settings.percentage_cut),
            'automatic_mode_enabled': settings.automatic_mode_enabled,
            'deposit_accounts': settings.deposit_accounts,
            'support_phone': settings.support_phone,
        })
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        try:
            if 'bid_amount' in data:
                settings.bid_amount = Decimal(str(data['bid_amount']))
            if 'card_selection_timer' in data:
                settings.card_selection_timer = int(data['card_selection_timer'])
            if 'time_between_calls' in data:
                settings.time_between_calls = int(data['time_between_calls'])
            if 'total_cards' in data:
                settings.total_cards = int(data['total_cards'])
            if 'min_withdraw' in data:
                settings.min_withdraw = Decimal(str(data['min_withdraw']))
            if 'percentage_cut' in data:
                settings.percentage_cut = Decimal(str(data['percentage_cut']))
            if 'automatic_mode_enabled' in data:
                settings.automatic_mode_enabled = bool(data['automatic_mode_enabled'])
            if 'deposit_accounts' in data:
                settings.deposit_accounts = data['deposit_accounts']
            if 'support_phone' in data:
                settings.support_phone = data['support_phone'].strip()
            
            settings.save()
            
            return JsonResponse({'success': True, 'message': 'Settings updated'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


@staff_member_required
@require_http_methods(["GET", "POST"])
def second_admin_credentials_api(request):
    """API endpoint to get and set second admin credentials"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    
    if request.method == 'GET':
        try:
            second_admin = SecondAdmin.objects.first()
            if second_admin:
                return JsonResponse({
                    'username': second_admin.username,
                    'has_password': bool(second_admin.password)
                })
        except Exception:
            pass
        return JsonResponse({'username': '', 'has_password': False})
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
            
            if not username:
                return JsonResponse({'error': 'Username is required'}, status=400)
            
            try:
                second_admin, created = SecondAdmin.objects.get_or_create(pk=1)
                second_admin.username = username
                
                if password:
                    second_admin.password = make_password(password)
                
                second_admin.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Second admin credentials updated successfully'
                })
            except Exception as db_error:
                # Handle case where SecondAdmin table doesn't exist
                return JsonResponse({
                    'error': 'Database table not ready. Please run migrations first.'
                }, status=500)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)


def second_admin_login(request):
    """Login view for second admin"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username', '').strip()
            password = data.get('password', '').strip()
            
            if not username or not password:
                return JsonResponse({'error': 'Username and password are required'}, status=400)
            
            try:
                second_admin = SecondAdmin.objects.get(username=username)
                if check_password(password, second_admin.password):
                    # Set session and save explicitly
                    request.session['second_admin_authenticated'] = True
                    request.session['second_admin_username'] = username
                    request.session.set_expiry(86400)  # 24 hours
                    request.session.save()  # Explicitly save session
                    return JsonResponse({'success': True, 'redirect': '/secondadmin'})
                else:
                    return JsonResponse({'error': 'Invalid credentials'}, status=401)
            except SecondAdmin.DoesNotExist:
                return JsonResponse({'error': 'Invalid credentials'}, status=401)
            except Exception as db_error:
                # Handle case where SecondAdmin table doesn't exist
                return JsonResponse({
                    'error': 'Database table not ready. Please run migrations first.'
                }, status=500)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    # GET request - show login page
    return render(request, 'admin/second_admin_login.html')


def second_admin_logout(request):
    """Logout view for second admin"""
    request.session.pop('second_admin_authenticated', None)
    request.session.pop('second_admin_username', None)
    return JsonResponse({'success': True, 'redirect': '/secondadmin/login'})


def second_admin_dashboard(request):
    """Second admin dashboard view with full access except delete users, call number, and second admin credentials"""
    # Check authentication - redirect to login if not authenticated
    if not request.session.get('second_admin_authenticated'):
        return redirect('second-admin-login')
    
    # Same data as main dashboard but with limitations
    now = timezone.now()
    
    # Get calendar-based date periods
    periods = get_calendar_periods(now)
    today_start = periods['today_start']
    today_end = periods['today_end']
    yesterday_start = periods['yesterday_start']
    yesterday_end = periods['yesterday_end']
    week_start = periods['week_start']
    week_end = periods['week_end']
    last_week_start = periods['last_week_start']
    last_week_end = periods['last_week_end']
    month_start = periods['month_start']
    month_end = periods['month_end']
    last_month_start = periods['last_month_start']
    last_month_end = periods['last_month_end']
    
    # Games played statistics
    games_today = Game.objects.filter(created_at__gte=today_start, created_at__lte=today_end).count()
    games_yesterday = Game.objects.filter(created_at__gte=yesterday_start, created_at__lt=yesterday_end).count()
    games_week = Game.objects.filter(created_at__gte=week_start, created_at__lte=week_end).count()
    games_last_week = Game.objects.filter(created_at__gte=last_week_start, created_at__lte=last_week_end).count()
    games_month = Game.objects.filter(created_at__gte=month_start, created_at__lte=month_end).count()
    games_last_month = Game.objects.filter(created_at__gte=last_month_start, created_at__lte=last_month_end).count()
    games_total = Game.objects.count()
    
    # Revenue statistics
    settings = GameSettings.get_settings()
    percentage_cut = settings.percentage_cut
    completed_games = Game.objects.filter(status='completed')
    
    def calculate_revenue(games_queryset):
        total = Decimal('0')
        for game in games_queryset:
            total_collected = game.derash_amount
            if total_collected > 0:
                cut = (total_collected * percentage_cut) / Decimal('100')
                total += cut
        return total
    
    revenue_today = calculate_revenue(completed_games.filter(completed_at__gte=today_start, completed_at__lte=today_end))
    revenue_yesterday = calculate_revenue(completed_games.filter(completed_at__gte=yesterday_start, completed_at__lt=yesterday_end))
    revenue_week = calculate_revenue(completed_games.filter(completed_at__gte=week_start, completed_at__lte=week_end))
    revenue_last_week = calculate_revenue(completed_games.filter(completed_at__gte=last_week_start, completed_at__lte=last_week_end))
    revenue_month = calculate_revenue(completed_games.filter(completed_at__gte=month_start, completed_at__lte=month_end))
    revenue_last_month = calculate_revenue(completed_games.filter(completed_at__gte=last_month_start, completed_at__lte=last_month_end))
    revenue_total = calculate_revenue(completed_games)
    
    # Pending requests (limit to 5 for initial display)
    pending_deposits = DepositRequest.objects.filter(status='pending').order_by('-created_at')[:5]
    pending_withdraws = WithdrawRequest.objects.filter(status='pending').order_by('-created_at')[:5]
    
    # Approved requests (limit to 5 for initial display)
    approved_deposits = DepositRequest.objects.filter(status='approved').order_by('-created_at')[:5]
    approved_withdraws = WithdrawRequest.objects.filter(status='approved').order_by('-created_at')[:5]
    
    # Active games (can start/end but NOT call number)
    active_games = Game.objects.filter(status__in=['waiting', 'active']).order_by('-created_at')
    
    # Game settings
    game_settings = GameSettings.get_settings()
    
    # Get today's games with winner info (limit to 5 for initial display)
    today_games_all = Game.objects.filter(created_at__gte=today_start).order_by('-created_at')
    today_games_count = today_games_all.count()
    today_games = today_games_all[:5]  # Limit to 5 for initial display
    today_games_data = []
    for game in today_games:
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        automatic_count = 0
        manual_count = 0
        for card in game.gamecards.all():
            mode_history = card.mode_history or []
            has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
            if has_automatic:
                automatic_count += 1
            else:
                manual_count += 1
        
        today_games_data.append({
            'game': game,
            'players': game.total_players,
            'bid_amount': game.bet_amount,
            'automatic_count': automatic_count,
            'manual_count': manual_count,
            'winner_phones': winner_phones,
        })
    
    # Get game details for the game detail section (max 200, newest first)
    all_games_detail = Game.objects.all().order_by('-created_at')[:200]
    games_detail_data = []
    for game in all_games_detail:
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        automatic_count = 0
        manual_count = 0
        for card in game.gamecards.all():
            mode_history = card.mode_history or []
            has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
            if has_automatic:
                automatic_count += 1
            else:
                manual_count += 1
        
        games_detail_data.append({
            'game': game,
            'players': game.total_players,
            'bid_amount': game.bet_amount,
            'derash_amount': game.derash_amount,
            'automatic_count': automatic_count,
            'manual_count': manual_count,
            'winner_phones': winner_phones,
            'called_numbers': list(game.called_numbers.all().values_list('number', flat=True)),
        })
    
    # Get recent transfers
    recent_transfers = Transfer.objects.all().order_by('-created_at')[:50]
    
    # Calculate total automatic and manual games
    from .models import GameCard
    all_cards = GameCard.objects.all()
    total_automatic_games = 0
    total_manual_games = 0
    
    for card in all_cards:
        mode_history = card.mode_history or []
        has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
        if has_automatic:
            total_automatic_games += 1
        else:
            total_manual_games += 1
    
    # Get registered users (can edit but NOT delete)
    registered_users_raw = User.objects.filter(telegram_id__isnull=False).order_by('-created_at')
    registered_users = []
    for user in registered_users_raw:
        games_played = Game.objects.filter(gamecards__user=user).distinct().count()
        wins = Game.objects.filter(winner=user).count()
        user_total_deposits = Transaction.objects.filter(user=user, transaction_type='deposit').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        user_total_withdrawals = Transaction.objects.filter(user=user, transaction_type='withdraw').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        registered_users.append({
            'user': user,
            'games_played': games_played,
            'wins': wins,
            'total_deposits': user_total_deposits,
            'total_withdrawals': user_total_withdrawals,
        })
    
    # Financial statistics
    total_deposits = Transaction.objects.filter(transaction_type='deposit').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    total_withdrawals = Transaction.objects.filter(transaction_type='withdraw').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    total_balance = User.objects.aggregate(
        total=Sum('balance')
    )['total'] or Decimal('0')
    
    # Format revenue
    revenue_today_formatted = format_large_number(revenue_today)
    revenue_yesterday_formatted = format_large_number(revenue_yesterday)
    revenue_week_formatted = format_large_number(revenue_week)
    revenue_last_week_formatted = format_large_number(revenue_last_week)
    revenue_month_formatted = format_large_number(revenue_month)
    revenue_last_month_formatted = format_large_number(revenue_last_month)
    
    # Date range strings for display (using calendar periods)
    date_today = f"{today_start.strftime('%Y-%m-%d')} to {today_end.strftime('%Y-%m-%d')}"
    date_yesterday = f"{yesterday_start.strftime('%Y-%m-%d')} to {yesterday_end.strftime('%Y-%m-%d')}"
    date_week = f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}"
    date_last_week = f"{last_week_start.strftime('%Y-%m-%d')} to {last_week_end.strftime('%Y-%m-%d')}"
    date_month = f"{month_start.strftime('%Y-%m-%d')} to {month_end.strftime('%Y-%m-%d')}"
    date_last_month = f"{last_month_start.strftime('%Y-%m-%d')} to {last_month_end.strftime('%Y-%m-%d')}"
    
    # Count totals for show more functionality
    pending_deposits_count = DepositRequest.objects.filter(status='pending').count()
    pending_withdraws_count = WithdrawRequest.objects.filter(status='pending').count()
    approved_deposits_count = DepositRequest.objects.filter(status='approved').count()
    approved_withdraws_count = WithdrawRequest.objects.filter(status='approved').count()
    
    context = {
        'games_today': games_today,
        'games_yesterday': games_yesterday,
        'games_week': games_week,
        'games_last_week': games_last_week,
        'games_month': games_month,
        'games_last_month': games_last_month,
        'games_total': games_total,
        'revenue_today': revenue_today,
        'revenue_yesterday': revenue_yesterday,
        'revenue_week': revenue_week,
        'revenue_last_week': revenue_last_week,
        'revenue_month': revenue_month,
        'revenue_last_month': revenue_last_month,
        'revenue_total': revenue_total,
        'revenue_today_formatted': revenue_today_formatted,
        'revenue_yesterday_formatted': revenue_yesterday_formatted,
        'revenue_week_formatted': revenue_week_formatted,
        'revenue_last_week_formatted': revenue_last_week_formatted,
        'revenue_month_formatted': revenue_month_formatted,
        'revenue_last_month_formatted': revenue_last_month_formatted,
        'date_today': date_today,
        'date_yesterday': date_yesterday,
        'date_week': date_week,
        'date_last_week': date_last_week,
        'date_month': date_month,
        'date_last_month': date_last_month,
        'pending_deposits': pending_deposits,
        'pending_withdraws': pending_withdraws,
        'approved_deposits': approved_deposits,
        'approved_withdraws': approved_withdraws,
        'pending_deposits_count': pending_deposits_count,
        'pending_withdraws_count': pending_withdraws_count,
        'approved_deposits_count': approved_deposits_count,
        'approved_withdraws_count': approved_withdraws_count,
        'active_games': active_games,
        'game_settings': game_settings,
        'registered_users': registered_users,
        'today_games_data': today_games_data,
        'today_games_count': today_games_count,  # Total count for "show more" functionality
        'games_detail_data': games_detail_data,
        'recent_transfers': recent_transfers,
        'total_deposits': total_deposits,
        'total_withdrawals': total_withdrawals,
        'total_balance': total_balance,
        'total_automatic_games': total_automatic_games,
        'total_manual_games': total_manual_games,
    }
    return render(request, 'admin/second_admin_dashboard.html', context)


@staff_member_required
@require_http_methods(["GET"])
def admin_dashboard_api(request):
    """API endpoint to get dashboard data as JSON for real-time updates"""
    now = timezone.now()
    
    # Get calendar-based date periods
    periods = get_calendar_periods(now)
    today_start = periods['today_start']
    today_end = periods['today_end']
    yesterday_start = periods['yesterday_start']
    yesterday_end = periods['yesterday_end']
    week_start = periods['week_start']
    week_end = periods['week_end']
    last_week_start = periods['last_week_start']
    last_week_end = periods['last_week_end']
    month_start = periods['month_start']
    month_end = periods['month_end']
    last_month_start = periods['last_month_start']
    last_month_end = periods['last_month_end']
    
    # Games played statistics
    games_today = Game.objects.filter(created_at__gte=today_start, created_at__lte=today_end).count()
    games_yesterday = Game.objects.filter(created_at__gte=yesterday_start, created_at__lt=yesterday_end).count()
    games_week = Game.objects.filter(created_at__gte=week_start, created_at__lte=week_end).count()
    games_last_week = Game.objects.filter(created_at__gte=last_week_start, created_at__lte=last_week_end).count()
    games_month = Game.objects.filter(created_at__gte=month_start, created_at__lte=month_end).count()
    games_last_month = Game.objects.filter(created_at__gte=last_month_start, created_at__lte=last_month_end).count()
    games_total = Game.objects.count()
    
    # Revenue statistics
    settings = GameSettings.get_settings()
    percentage_cut = settings.percentage_cut
    completed_games = Game.objects.filter(status='completed')
    
    def calculate_revenue(games_queryset):
        total = Decimal('0')
        for game in games_queryset:
            total_collected = game.derash_amount
            if total_collected > 0:
                cut = (total_collected * percentage_cut) / Decimal('100')
                total += cut
        return total
    
    revenue_today = calculate_revenue(completed_games.filter(completed_at__gte=today_start, completed_at__lte=today_end))
    revenue_yesterday = calculate_revenue(completed_games.filter(completed_at__gte=yesterday_start, completed_at__lt=yesterday_end))
    revenue_week = calculate_revenue(completed_games.filter(completed_at__gte=week_start, completed_at__lte=week_end))
    revenue_last_week = calculate_revenue(completed_games.filter(completed_at__gte=last_week_start, completed_at__lte=last_week_end))
    revenue_month = calculate_revenue(completed_games.filter(completed_at__gte=month_start, completed_at__lte=month_end))
    revenue_last_month = calculate_revenue(completed_games.filter(completed_at__gte=last_month_start, completed_at__lte=last_month_end))
    revenue_total = calculate_revenue(completed_games)
    
    # Date range strings for display (using calendar periods)
    
    date_today = f"{today_start.strftime('%Y-%m-%d')} to {today_end.strftime('%Y-%m-%d')}"
    date_yesterday = f"{yesterday_start.strftime('%Y-%m-%d')} to {yesterday_end.strftime('%Y-%m-%d')}"
    date_week = f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}"
    date_last_week = f"{last_week_start.strftime('%Y-%m-%d')} to {last_week_end.strftime('%Y-%m-%d')}"
    date_month = f"{month_start.strftime('%Y-%m-%d')} to {month_end.strftime('%Y-%m-%d')}"
    date_last_month = f"{last_month_start.strftime('%Y-%m-%d')} to {last_month_end.strftime('%Y-%m-%d')}"
    
    # Pending requests (limit to 5 for initial display)
    pending_deposits = DepositRequest.objects.filter(status='pending').order_by('-created_at')[:5]
    pending_withdraws = WithdrawRequest.objects.filter(status='pending').order_by('-created_at')[:5]
    
    # Approved requests (limit to 5 for initial display)
    approved_deposits = DepositRequest.objects.filter(status='approved').order_by('-created_at')[:5]
    approved_withdraws = WithdrawRequest.objects.filter(status='approved').order_by('-created_at')[:5]
    
    # Count totals for show more functionality
    pending_deposits_count = DepositRequest.objects.filter(status='pending').count()
    pending_withdraws_count = WithdrawRequest.objects.filter(status='pending').count()
    approved_deposits_count = DepositRequest.objects.filter(status='approved').count()
    approved_withdraws_count = WithdrawRequest.objects.filter(status='approved').count()
    
    # Active games
    active_games = Game.objects.filter(status__in=['waiting', 'active']).order_by('-created_at')
    
    # Today's games (limit to 5 for initial display)
    today_games_all = Game.objects.filter(created_at__gte=today_start).order_by('-created_at')
    today_games_count = today_games_all.count()
    today_games = today_games_all[:5]  # Limit to 5 for initial display
    today_games_data = []
    for game in today_games:
        automatic_count = 0
        manual_count = 0
        for card in game.gamecards.all():
            mode_history = card.mode_history or []
            has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
            if has_automatic:
                automatic_count += 1
            else:
                manual_count += 1
        
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        today_games_data.append({
            'id': game.id,
            'players': game.total_players,
            'bid_amount': float(game.bet_amount),
            'automatic_count': automatic_count,
            'manual_count': manual_count,
            'winner_phones': winner_phones,
            'status': game.status,
            'created_at': game.created_at.strftime('%H:%M'),
        })
    
    # Registered users
    registered_users_raw = User.objects.filter(telegram_id__isnull=False).order_by('-created_at')
    registered_users = []
    total_deposits = Decimal('0')
    for user in registered_users_raw:
        games_played = Game.objects.filter(gamecards__user=user).distinct().count()
        wins = Game.objects.filter(winner=user).count()
        user_total_deposits = Transaction.objects.filter(user=user, transaction_type='deposit').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        user_total_withdrawals = Transaction.objects.filter(user=user, transaction_type='withdraw').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        total_deposits += user_total_deposits
        
        registered_users.append({
            'id': user.id,
            'username': user.username,
            'telegram_id': user.telegram_id,
            'phone_number': user.phone_number or '-',
            'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or '-',
            'balance': float(user.balance),
            'games_played': games_played,
            'wins': wins,
            'total_deposits': float(user_total_deposits),
            'total_withdrawals': float(user_total_withdrawals),
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Financial statistics
    total_withdrawals = Transaction.objects.filter(transaction_type='withdraw').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    total_balance = User.objects.aggregate(
        total=Sum('balance')
    )['total'] or Decimal('0')
    
    # Game mode statistics
    from .models import GameCard
    all_cards = GameCard.objects.all()
    total_automatic_games = 0
    total_manual_games = 0
    for card in all_cards:
        mode_history = card.mode_history or []
        has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
        if has_automatic:
            total_automatic_games += 1
        else:
            total_manual_games += 1
    
    # Active games data
    active_games_data = []
    for game in active_games:
        active_games_data.append({
            'id': game.id,
            'status': game.status,
            'players': game.total_players,
            'derash_amount': float(game.derash_amount),
        })
    
    # Pending deposits data
    pending_deposits_data = []
    for deposit in pending_deposits:
        pending_deposits_data.append({
            'id': deposit.id,
            'username': deposit.user.username,
            'amount': float(deposit.amount),
            'platform': deposit.platform,
            'deposit_text': deposit.deposit_text,
            'photo_file_id': deposit.photo_file_id or None,
            'created_at': deposit.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Pending withdraws data
    pending_withdraws_data = []
    for withdraw in pending_withdraws:
        pending_withdraws_data.append({
            'id': withdraw.id,
            'username': withdraw.user.username,
            'amount': float(withdraw.amount),
            'platform': withdraw.platform,
            'account_holder_name': withdraw.account_holder_name,
            'account_number': withdraw.account_number,
            'created_at': withdraw.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Approved deposits data
    approved_deposits_data = []
    for deposit in approved_deposits:
        approved_deposits_data.append({
            'id': deposit.id,
            'username': deposit.user.username,
            'amount': float(deposit.amount),
            'platform': deposit.platform,
            'deposit_text': deposit.deposit_text,
            'photo_file_id': deposit.photo_file_id or None,
            'created_at': deposit.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Approved withdraws data
    approved_withdraws_data = []
    for withdraw in approved_withdraws:
        approved_withdraws_data.append({
            'id': withdraw.id,
            'username': withdraw.user.username,
            'amount': float(withdraw.amount),
            'platform': withdraw.platform,
            'account_holder_name': withdraw.account_holder_name,
            'account_number': withdraw.account_number,
            'created_at': withdraw.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    return JsonResponse({
        'games_today': games_today,
        'games_yesterday': games_yesterday,
        'games_week': games_week,
        'games_last_week': games_last_week,
        'games_month': games_month,
        'games_last_month': games_last_month,
        'games_total': games_total,
        'revenue_today': float(revenue_today),
        'revenue_yesterday': float(revenue_yesterday),
        'revenue_week': float(revenue_week),
        'revenue_last_week': float(revenue_last_week),
        'revenue_month': float(revenue_month),
        'revenue_last_month': float(revenue_last_month),
        'revenue_total': float(revenue_total),
        'revenue_today_formatted': format_large_number(revenue_today),
        'revenue_yesterday_formatted': format_large_number(revenue_yesterday),
        'revenue_week_formatted': format_large_number(revenue_week),
        'revenue_last_week_formatted': format_large_number(revenue_last_week),
        'revenue_month_formatted': format_large_number(revenue_month),
        'revenue_last_month_formatted': format_large_number(revenue_last_month),
        'date_today': date_today,
        'date_yesterday': date_yesterday,
        'date_week': date_week,
        'date_last_week': date_last_week,
        'date_month': date_month,
        'date_last_month': date_last_month,
        'total_deposits': float(total_deposits),
        'total_withdrawals': float(total_withdrawals),
        'total_balance': float(total_balance),
        'total_automatic_games': total_automatic_games,
        'total_manual_games': total_manual_games,
        'active_games': active_games_data,
        'today_games': today_games_data,
        'today_games_count': today_games_count,  # Total count for "show more" functionality
        'registered_users': registered_users,
        'pending_deposits': pending_deposits_data,
        'pending_withdraws': pending_withdraws_data,
        'approved_deposits': approved_deposits_data,
        'approved_withdraws': approved_withdraws_data,
        'pending_deposits_count': pending_deposits_count,
        'pending_withdraws_count': pending_withdraws_count,
        'approved_deposits_count': approved_deposits_count,
        'approved_withdraws_count': approved_withdraws_count,
    })


@require_http_methods(["GET"])
def second_admin_dashboard_api(request):
    """API endpoint for second admin dashboard data - full access except delete users, call number, and second admin credentials"""
    # Check authentication
    if not request.session.get('second_admin_authenticated'):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    # Same logic as main dashboard
    now = timezone.now()
    
    # Get calendar-based date periods
    periods = get_calendar_periods(now)
    today_start = periods['today_start']
    today_end = periods['today_end']
    yesterday_start = periods['yesterday_start']
    yesterday_end = periods['yesterday_end']
    week_start = periods['week_start']
    week_end = periods['week_end']
    last_week_start = periods['last_week_start']
    last_week_end = periods['last_week_end']
    month_start = periods['month_start']
    month_end = periods['month_end']
    last_month_start = periods['last_month_start']
    last_month_end = periods['last_month_end']
    
    games_today = Game.objects.filter(created_at__gte=today_start, created_at__lte=today_end).count()
    games_yesterday = Game.objects.filter(created_at__gte=yesterday_start, created_at__lt=yesterday_end).count()
    games_week = Game.objects.filter(created_at__gte=week_start, created_at__lte=week_end).count()
    games_last_week = Game.objects.filter(created_at__gte=last_week_start, created_at__lte=last_week_end).count()
    games_month = Game.objects.filter(created_at__gte=month_start, created_at__lte=month_end).count()
    games_last_month = Game.objects.filter(created_at__gte=last_month_start, created_at__lte=last_month_end).count()
    games_total = Game.objects.count()
    
    settings = GameSettings.get_settings()
    percentage_cut = settings.percentage_cut
    completed_games = Game.objects.filter(status='completed')
    
    def calculate_revenue(games_queryset):
        total = Decimal('0')
        for game in games_queryset:
            total_collected = game.derash_amount
            if total_collected > 0:
                cut = (total_collected * percentage_cut) / Decimal('100')
                total += cut
        return total
    
    revenue_today = calculate_revenue(completed_games.filter(completed_at__gte=today_start, completed_at__lte=today_end))
    revenue_yesterday = calculate_revenue(completed_games.filter(completed_at__gte=yesterday_start, completed_at__lt=yesterday_end))
    revenue_week = calculate_revenue(completed_games.filter(completed_at__gte=week_start, completed_at__lte=week_end))
    revenue_last_week = calculate_revenue(completed_games.filter(completed_at__gte=last_week_start, completed_at__lte=last_week_end))
    revenue_month = calculate_revenue(completed_games.filter(completed_at__gte=month_start, completed_at__lte=month_end))
    revenue_last_month = calculate_revenue(completed_games.filter(completed_at__gte=last_month_start, completed_at__lte=last_month_end))
    revenue_total = calculate_revenue(completed_games)
    
    # Date range strings for display (using calendar periods)
    
    date_today = f"{today_start.strftime('%Y-%m-%d')} to {today_end.strftime('%Y-%m-%d')}"
    date_yesterday = f"{yesterday_start.strftime('%Y-%m-%d')} to {yesterday_end.strftime('%Y-%m-%d')}"
    date_week = f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}"
    date_last_week = f"{last_week_start.strftime('%Y-%m-%d')} to {last_week_end.strftime('%Y-%m-%d')}"
    date_month = f"{month_start.strftime('%Y-%m-%d')} to {month_end.strftime('%Y-%m-%d')}"
    date_last_month = f"{last_month_start.strftime('%Y-%m-%d')} to {last_month_end.strftime('%Y-%m-%d')}"
    
    # Pending requests (limit to 5 for initial display)
    pending_deposits = DepositRequest.objects.filter(status='pending').order_by('-created_at')[:5]
    pending_withdraws = WithdrawRequest.objects.filter(status='pending').order_by('-created_at')[:5]
    
    # Approved requests (limit to 5 for initial display)
    approved_deposits = DepositRequest.objects.filter(status='approved').order_by('-created_at')[:5]
    approved_withdraws = WithdrawRequest.objects.filter(status='approved').order_by('-created_at')[:5]
    
    # Count totals for show more functionality
    pending_deposits_count = DepositRequest.objects.filter(status='pending').count()
    pending_withdraws_count = WithdrawRequest.objects.filter(status='pending').count()
    approved_deposits_count = DepositRequest.objects.filter(status='approved').count()
    approved_withdraws_count = WithdrawRequest.objects.filter(status='approved').count()
    
    active_games = Game.objects.filter(status__in=['waiting', 'active']).order_by('-created_at')
    active_games_data = []
    for game in active_games:
        active_games_data.append({
            'id': game.id,
            'status': game.status,
            'players': game.total_players,
            'derash_amount': float(game.derash_amount),
        })
    
    # Get today's games - check if all games are requested
    today_games_all = Game.objects.filter(created_at__gte=today_start).order_by('-created_at')
    today_games_count = today_games_all.count()
    # Check if 'all' parameter is passed to return all games
    show_all = request.GET.get('all', 'false').lower() == 'true'
    today_games = today_games_all if show_all else today_games_all[:5]  # Limit to 5 for initial display, or all if requested
    today_games_data = []
    for game in today_games:
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        automatic_count = 0
        manual_count = 0
        for card in game.gamecards.all():
            mode_history = card.mode_history or []
            has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
            if has_automatic:
                automatic_count += 1
            else:
                manual_count += 1
        
        today_games_data.append({
            'id': game.id,
            'players': game.total_players,
            'bid_amount': float(game.bet_amount),
            'automatic_count': automatic_count,
            'manual_count': manual_count,
            'winner_phones': winner_phones,
            'status': game.status,
            'created_at': game.created_at.strftime('%H:%M'),
        })
    
    registered_users_raw = User.objects.filter(telegram_id__isnull=False).order_by('-created_at')
    registered_users = []
    for user in registered_users_raw:
        games_played = Game.objects.filter(gamecards__user=user).distinct().count()
        wins = Game.objects.filter(winner=user).count()
        user_total_deposits = Transaction.objects.filter(user=user, transaction_type='deposit').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        user_total_withdrawals = Transaction.objects.filter(user=user, transaction_type='withdraw').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        registered_users.append({
            'id': user.id,
            'username': user.username,
            'telegram_id': user.telegram_id,
            'phone_number': user.phone_number or '-',
            'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or '-',
            'balance': float(user.balance),
            'games_played': games_played,
            'wins': wins,
            'total_deposits': float(user_total_deposits),
            'total_withdrawals': float(user_total_withdrawals),
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Pending deposits data
    pending_deposits_data = []
    for deposit in pending_deposits:
        pending_deposits_data.append({
            'id': deposit.id,
            'username': deposit.user.username,
            'amount': float(deposit.amount),
            'platform': deposit.platform,
            'deposit_text': deposit.deposit_text,
            'photo_file_id': deposit.photo_file_id or None,
            'created_at': deposit.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Pending withdraws data
    pending_withdraws_data = []
    for withdraw in pending_withdraws:
        pending_withdraws_data.append({
            'id': withdraw.id,
            'username': withdraw.user.username,
            'amount': float(withdraw.amount),
            'platform': withdraw.platform,
            'account_holder_name': withdraw.account_holder_name,
            'account_number': withdraw.account_number,
            'created_at': withdraw.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Approved deposits data
    approved_deposits_data = []
    for deposit in approved_deposits:
        approved_deposits_data.append({
            'id': deposit.id,
            'username': deposit.user.username,
            'amount': float(deposit.amount),
            'platform': deposit.platform,
            'deposit_text': deposit.deposit_text,
            'photo_file_id': deposit.photo_file_id or None,
            'created_at': deposit.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Approved withdraws data
    approved_withdraws_data = []
    for withdraw in approved_withdraws:
        approved_withdraws_data.append({
            'id': withdraw.id,
            'username': withdraw.user.username,
            'amount': float(withdraw.amount),
            'platform': withdraw.platform,
            'account_holder_name': withdraw.account_holder_name,
            'account_number': withdraw.account_number,
            'created_at': withdraw.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    total_deposits = Transaction.objects.filter(transaction_type='deposit').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    total_withdrawals = Transaction.objects.filter(transaction_type='withdraw').aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0')
    total_balance = User.objects.aggregate(
        total=Sum('balance')
    )['total'] or Decimal('0')
    
    # Calculate total automatic and manual games
    from .models import GameCard
    all_cards = GameCard.objects.all()
    total_automatic_games = 0
    total_manual_games = 0
    for card in all_cards:
        mode_history = card.mode_history or []
        has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
        if has_automatic:
            total_automatic_games += 1
        else:
            total_manual_games += 1
    
    return JsonResponse({
        'games_today': games_today,
        'games_yesterday': games_yesterday,
        'games_week': games_week,
        'games_last_week': games_last_week,
        'games_month': games_month,
        'games_last_month': games_last_month,
        'games_total': games_total,
        'revenue_today': float(revenue_today),
        'revenue_yesterday': float(revenue_yesterday),
        'revenue_week': float(revenue_week),
        'revenue_last_week': float(revenue_last_week),
        'revenue_month': float(revenue_month),
        'revenue_last_month': float(revenue_last_month),
        'revenue_total': float(revenue_total),
        'revenue_today_formatted': format_large_number(revenue_today),
        'revenue_yesterday_formatted': format_large_number(revenue_yesterday),
        'revenue_week_formatted': format_large_number(revenue_week),
        'revenue_last_week_formatted': format_large_number(revenue_last_week),
        'revenue_month_formatted': format_large_number(revenue_month),
        'revenue_last_month_formatted': format_large_number(revenue_last_month),
        'date_today': date_today,
        'date_yesterday': date_yesterday,
        'date_week': date_week,
        'date_last_week': date_last_week,
        'date_month': date_month,
        'date_last_month': date_last_month,
        'total_deposits': float(total_deposits),
        'total_withdrawals': float(total_withdrawals),
        'total_balance': float(total_balance),
        'total_automatic_games': total_automatic_games,
        'total_manual_games': total_manual_games,
        'active_games': active_games_data,
        'today_games': today_games_data,
        'today_games_count': today_games_count,  # Total count for "show more" functionality
        'registered_users': registered_users,
        'pending_deposits': pending_deposits_data,
        'pending_withdraws': pending_withdraws_data,
        'approved_deposits': approved_deposits_data,
        'approved_withdraws': approved_withdraws_data,
        'pending_deposits_count': pending_deposits_count,
        'pending_withdraws_count': pending_withdraws_count,
        'approved_deposits_count': approved_deposits_count,
        'approved_withdraws_count': approved_withdraws_count,
    })


@require_http_methods(["GET"])
def refresh_deposits_withdrawals_api(request):
    """API endpoint to refresh only deposit/withdrawal sections"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    # Get all requests (no limit for refresh/show more functionality)
    pending_deposits = DepositRequest.objects.filter(status='pending').order_by('-created_at')
    pending_withdraws = WithdrawRequest.objects.filter(status='pending').order_by('-created_at')
    
    # Approved requests (no limit for refresh/show more functionality)
    approved_deposits = DepositRequest.objects.filter(status='approved').order_by('-created_at')
    approved_withdraws = WithdrawRequest.objects.filter(status='approved').order_by('-created_at')
    
    # Count totals for show more functionality
    pending_deposits_count = DepositRequest.objects.filter(status='pending').count()
    pending_withdraws_count = WithdrawRequest.objects.filter(status='pending').count()
    approved_deposits_count = DepositRequest.objects.filter(status='approved').count()
    approved_withdraws_count = WithdrawRequest.objects.filter(status='approved').count()
    
    # Pending deposits data
    pending_deposits_data = []
    for deposit in pending_deposits:
        pending_deposits_data.append({
            'id': deposit.id,
            'username': deposit.user.username,
            'amount': float(deposit.amount),
            'platform': deposit.platform,
            'deposit_text': deposit.deposit_text,
            'photo_file_id': deposit.photo_file_id or None,
            'created_at': deposit.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Pending withdraws data
    pending_withdraws_data = []
    for withdraw in pending_withdraws:
        pending_withdraws_data.append({
            'id': withdraw.id,
            'username': withdraw.user.username,
            'amount': float(withdraw.amount),
            'platform': withdraw.platform,
            'account_holder_name': withdraw.account_holder_name,
            'account_number': withdraw.account_number,
            'created_at': withdraw.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Approved deposits data
    approved_deposits_data = []
    for deposit in approved_deposits:
        approved_deposits_data.append({
            'id': deposit.id,
            'username': deposit.user.username,
            'amount': float(deposit.amount),
            'platform': deposit.platform,
            'deposit_text': deposit.deposit_text,
            'photo_file_id': deposit.photo_file_id or None,
            'created_at': deposit.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # Approved withdraws data
    approved_withdraws_data = []
    for withdraw in approved_withdraws:
        approved_withdraws_data.append({
            'id': withdraw.id,
            'username': withdraw.user.username,
            'amount': float(withdraw.amount),
            'platform': withdraw.platform,
            'account_holder_name': withdraw.account_holder_name,
            'account_number': withdraw.account_number,
            'created_at': withdraw.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    return JsonResponse({
        'pending_deposits': pending_deposits_data,
        'pending_withdraws': pending_withdraws_data,
        'approved_deposits': approved_deposits_data,
        'approved_withdraws': approved_withdraws_data,
        'pending_deposits_count': pending_deposits_count,
        'pending_withdraws_count': pending_withdraws_count,
        'approved_deposits_count': approved_deposits_count,
        'approved_withdraws_count': approved_withdraws_count,
    })


@staff_member_required
@require_http_methods(["GET"])
def get_deposit_photo(request, deposit_id):
    """Get deposit photo from Telegram file_id"""
    try:
        deposit = DepositRequest.objects.get(id=deposit_id)
        
        if not deposit.photo_file_id:
            from django.http import JsonResponse
            return JsonResponse({'error': 'No photo available'}, status=404)
        
        # Use Telegram Bot API to get file URL
        from django.conf import settings
        import requests
        
        bot_token = settings.TELEGRAM_BOT_TOKEN
        if not bot_token:
            from django.http import JsonResponse
            return JsonResponse({'error': 'Telegram bot token not configured'}, status=500)
        
        # Get file info from Telegram
        file_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={deposit.photo_file_id}"
        try:
            response = requests.get(file_url, timeout=10)
        except requests.RequestException as e:
            from django.http import JsonResponse
            return JsonResponse({'error': f'Failed to connect to Telegram: {str(e)}'}, status=500)
        
        if response.status_code != 200:
            from django.http import JsonResponse
            return JsonResponse({'error': 'Failed to get file from Telegram'}, status=500)
        
        try:
            file_info = response.json()
        except ValueError:
            from django.http import JsonResponse
            return JsonResponse({'error': 'Invalid response from Telegram'}, status=500)
        
        if not file_info.get('ok'):
            error_description = file_info.get('description', 'Unknown error')
            from django.http import JsonResponse
            return JsonResponse({'error': f'File not found in Telegram: {error_description}'}, status=404)
        
        file_path = file_info['result'].get('file_path')
        if not file_path:
            from django.http import JsonResponse
            return JsonResponse({'error': 'File path not found in Telegram response'}, status=404)
        
        photo_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        
        # Try to fetch the image and return it directly
        # This avoids CORS issues and provides better error handling
        try:
            img_response = requests.get(photo_url, timeout=10, stream=True)
            if img_response.status_code == 200:
                from django.http import HttpResponse
                response = HttpResponse(img_response.content, content_type=img_response.headers.get('Content-Type', 'image/jpeg'))
                response['Content-Disposition'] = f'inline; filename="deposit_{deposit_id}.jpg"'
                return response
            else:
                from django.http import JsonResponse
                return JsonResponse({'error': f'Failed to fetch image from Telegram: HTTP {img_response.status_code}'}, status=500)
        except requests.RequestException as e:
            from django.http import JsonResponse
            return JsonResponse({'error': f'Failed to fetch image: {str(e)}'}, status=500)
        
    except DepositRequest.DoesNotExist:
        from django.http import JsonResponse
        return JsonResponse({'error': 'Deposit not found'}, status=404)
    except Exception as e:
        from django.http import JsonResponse
        import traceback
        return JsonResponse({'error': f'Error loading photo: {str(e)}'}, status=500)