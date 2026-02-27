from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum, Count, Q, Prefetch, F
from django.db.models.functions import Coalesce
from datetime import datetime, timedelta
from .models import Deposit, Game, CalledNumber, Transaction, User, DepositRequest, WithdrawRequest, GameSettings, Transfer, AdminMessage, SecondAdmin, BroadcastMessage, FailedDepositRequest
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


def _get_new_starts_count_for_context():
    """Return current 24h-window register count for dashboard. When Redis has no window or count 0, fall back to users created today (DB) so the admin sees a sensible number."""
    try:
        from .redis_utils import get_new_starts_window_count
        data = get_new_starts_window_count()
        count = data.get('count', 0)
        window_end_ts = data.get('window_end_ts')
        # When Redis window was never set or expired, and count is 0, show DB "users created today" so admin sees activity
        if count == 0 and window_end_ts is None:
            return _get_users_created_today_count()
        return count
    except Exception:
        return _get_users_created_today_count()


def _get_users_created_today_count():
    """Return number of users (with telegram_id) created today (calendar day, server timezone)."""
    try:
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return User.objects.filter(telegram_id__isnull=False, created_at__gte=today_start).count()
    except Exception:
        return 0


@csrf_exempt
@require_http_methods(["POST"])
def admin_dashboard_login(request):
    """Inline login for admin dashboard: authenticate with Django auth (staff only), return JSON."""
    from django.contrib.auth import authenticate, login
    try:
        data = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        data = {}
    username = data.get('username') or request.POST.get('username', '').strip()
    password = data.get('password') or request.POST.get('password', '')
    if not username or not password:
        return JsonResponse({'error': 'Username and password required'}, status=400)
    user = authenticate(request, username=username, password=password)
    # Fallback: some deployments use custom auth backends; try direct User lookup + check_password
    if user is None:
        try:
            u = User.objects.get(username=username)
            if u.check_password(password) and (u.is_staff or u.is_superuser) and u.is_active:
                user = u
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            pass
    if user is not None and (user.is_staff or user.is_superuser):
        login(request, user)
        return JsonResponse({'success': True, 'message': 'Logged in'})
    return JsonResponse({'error': 'Invalid credentials or not a staff user'}, status=401)


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
    """Admin dashboard view with statistics - PHASE 3 OPTIMIZED with caching"""
    from django.core.cache import cache
    
    # PHASE 3 OPTIMIZATION: Cache dashboard data for 60 seconds
    cache_key = 'admin:dashboard:data'
    cached_data = cache.get(cache_key)
    
    if cached_data:
        # Return cached data (much faster)
        return render(request, 'admin/dashboard.html', cached_data)
    
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
    
    # PHASE 3 OPTIMIZATION: Use select_related and prefetch_related for game queries
    # Games played statistics - optimized with single query where possible
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
    
    # Calculate revenue from completed games - OPTIMIZED with aggregation
    from .models import GameCard
    
    def calculate_revenue(games_queryset):
        """
        Calculate revenue from games, excluding fake users.
        Revenue = (real_users_count * bet_amount) * percentage_cut / 100
        Only counts real users who paid - fake users don't generate revenue
        OPTIMIZED: Uses aggregation instead of per-game queries
        """
        # Use aggregation to count GameCards per game and calculate revenue in one query
        # Annotate games with real_users_count using aggregation
        games_with_counts = games_queryset.annotate(
            real_users_count=Count('gamecards', distinct=True)
        ).filter(real_users_count__gt=0)
        
        # Calculate total revenue using aggregation
        # Note: Cannot use .only() with annotations, so we iterate normally
        total = Decimal('0')
        for game in games_with_counts:
            total_collected = Decimal(str(game.real_users_count)) * game.bet_amount
            cut = (total_collected * percentage_cut) / Decimal('100')
            total += cut
        return total
    
    completed_games = Game.objects.filter(status='completed')
    
    # OPTIMIZED: Cache revenue calculations for 5 minutes to avoid recalculating
    from django.core.cache import cache as revenue_cache
    revenue_cache_key_prefix = 'admin_revenue_'
    
    def get_cached_revenue(key_suffix, queryset):
        cache_key = f'{revenue_cache_key_prefix}{key_suffix}'
        cached = revenue_cache.get(cache_key)
        if cached is not None:
            return cached
        result = calculate_revenue(queryset)
        revenue_cache.set(cache_key, result, 300)  # Cache for 5 minutes
        return result
    
    revenue_today = get_cached_revenue('today', completed_games.filter(completed_at__gte=today_start, completed_at__lte=today_end))
    revenue_yesterday = get_cached_revenue('yesterday', completed_games.filter(completed_at__gte=yesterday_start, completed_at__lt=yesterday_end))
    revenue_week = get_cached_revenue('week', completed_games.filter(completed_at__gte=week_start, completed_at__lte=week_end))
    revenue_last_week = get_cached_revenue('last_week', completed_games.filter(completed_at__gte=last_week_start, completed_at__lte=last_week_end))
    revenue_month = get_cached_revenue('month', completed_games.filter(completed_at__gte=month_start, completed_at__lte=month_end))
    revenue_last_month = get_cached_revenue('last_month', completed_games.filter(completed_at__gte=last_month_start, completed_at__lte=last_month_end))
    revenue_total = get_cached_revenue('total', completed_games)
    
    # PHASE 3 OPTIMIZATION: Use select_related to avoid N+1 queries
    # Pending requests (limit to 5 for initial display)
    pending_deposits = DepositRequest.objects.select_related('user').filter(status='pending').order_by('-created_at')[:5]
    pending_withdraws = WithdrawRequest.objects.select_related('user').filter(status='pending').order_by('-created_at')[:5]
    
    # Approved requests (limit to 5 for initial display)
    approved_deposits = DepositRequest.objects.select_related('user').filter(status='approved').order_by('-created_at')[:5]
    approved_withdraws = WithdrawRequest.objects.select_related('user').filter(status='approved').order_by('-created_at')[:5]
    
    # PHASE 3 OPTIMIZATION: Use select_related and prefetch_related for active games
    # Active games - prefetch winner and winners to avoid N+1 queries
    active_games = Game.objects.filter(status__in=['waiting', 'active']).select_related('winner').prefetch_related('winners').order_by('-created_at')
    
    # Game settings
    game_settings = GameSettings.get_settings()
    # Ensure new fields exist with defaults (for backward compatibility if migration not run)
    if not hasattr(game_settings, 'system_accounts_min'):
        game_settings.system_accounts_min = 15
    if not hasattr(game_settings, 'system_accounts_max'):
        game_settings.system_accounts_max = 30
    if not hasattr(game_settings, 'winning_patterns') or not game_settings.winning_patterns:
        game_settings.winning_patterns = ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']
    
    # Get today's games with details - OPTIMIZED: Limited to 50 most recent games
    from .fake_user_manager import get_fake_user_count_for_game
    from .models import FakeUserGameCard
    
    # Limit to 10 most recent games to avoid processing hundreds of games
    today_games = Game.objects.filter(created_at__gte=today_start).order_by('-created_at')[:10].prefetch_related(
        'gamecards',
        'winners',
        Prefetch('called_numbers', queryset=CalledNumber.objects.all().only('number'))
    ).select_related('winner').annotate(
        fake_user_count=Count('fake_cards', distinct=True)
    )
    
    today_games_data = []
    for game in today_games:
        # REMOVED: Automatic/manual counting per game (too expensive - JSON parsing for each card)
        # This was causing major slowdown when processing many games
        # If needed, can be calculated on-demand or cached separately
        
        # Get winner phone numbers - use prefetched winners
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        # Also check winners (ManyToMany) - use prefetched
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        # Count real and system users - use prefetched gamecards count and annotated fake count
        real_users_count = game.gamecards.count()
        system_users_count = game.fake_user_count or 0
        
        today_games_data.append({
            'game': game,
            'players': game.total_players,
            'bid_amount': game.bet_amount,
            'automatic_count': 0,  # Removed expensive calculation
            'manual_count': 0,  # Removed expensive calculation
            'winner_phones': winner_phones,
            'real_users': real_users_count,
            'system_users': system_users_count,
        })
    
    # Get game details for the game detail section - OPTIMIZED: Limited to 10 most recent games
    # Reduced from 200 to 10 to improve performance
    all_games_detail = Game.objects.all().order_by('-created_at')[:10].prefetch_related(
        'gamecards',
        'winners',
        Prefetch('called_numbers', queryset=CalledNumber.objects.all().only('number'))
    ).select_related('winner').annotate(
        fake_user_count=Count('fake_cards', distinct=True)
    )
    
    games_detail_data = []
    for game in all_games_detail:
        # Get winner phone numbers - use prefetched winners
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        # REMOVED: Automatic/manual counting per game (too expensive - JSON parsing for each card)
        # This was causing major slowdown when processing many games
        
        # Use prefetched called_numbers - limit to last 10 to avoid loading all 75
        called_numbers_list = [cn.number for cn in game.called_numbers.all()[:10]]
        
        games_detail_data.append({
            'game': game,
            'players': game.total_players,
            'bid_amount': game.bet_amount,
            'derash_amount': game.derash_amount,
            'automatic_count': 0,  # Removed expensive calculation
            'manual_count': 0,  # Removed expensive calculation
            'winner_phones': winner_phones,
            'called_numbers': called_numbers_list,
        })
    
    # Get recent transfers
    recent_transfers = Transfer.objects.all().order_by('-created_at')[:10]
    
    # Calculate total statistics - OPTIMIZED: Use only() to limit fields, cache result
    from .models import GameCard
    from django.core.cache import cache
    
    # Cache this expensive calculation for 5 minutes
    cache_key = 'admin_total_automatic_manual_games'
    cached_result = cache.get(cache_key)
    
    # PHASE 3 FIX: Validate cached result before unpacking
    if cached_result is not None and isinstance(cached_result, (tuple, list)) and len(cached_result) == 2:
        total_automatic_games, total_manual_games = cached_result
    else:
        # Use only() to limit fields loaded, but regular queryset (no iterator to avoid cursor issues)
        all_cards = GameCard.objects.only('mode_history')
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
        
        # Cache for 5 minutes (300 seconds)
        cache.set(cache_key, (total_automatic_games, total_manual_games), 300)
    
    # Get registered users - OPTIMIZED: Limited to 20 most recent users
    # Reduced from all users to improve performance
    registered_users_raw = User.objects.filter(telegram_id__isnull=False).order_by('-created_at')[:20].annotate(
        games_played=Count('gamecards__game', distinct=True),
        wins=Count('won_games', distinct=True),
        user_total_deposits=Sum('transactions__amount', filter=Q(transactions__transaction_type='deposit')),
        user_total_withdrawals=Sum('transactions__amount', filter=Q(transactions__transaction_type='withdraw'))
    )
    
    registered_users = []
    for user in registered_users_raw:
        games_played = user.games_played or 0
        wins = user.wins or 0
        user_total_deposits = user.user_total_deposits or Decimal('0')
        user_total_withdrawals = user.user_total_withdrawals or Decimal('0')
        
        registered_users.append({
            'user': user,
            'games_played': games_played,
            'wins': wins,
            'total_deposits': user_total_deposits,
            'total_withdrawals': user_total_withdrawals,
        })
    
    # Financial statistics - Calculate from ALL registered users (not just the limited display list)
    # Sum deposits and withdrawals from all registered users' transactions
    all_registered_users = User.objects.filter(telegram_id__isnull=False)
    total_deposits = Transaction.objects.filter(
        transaction_type='deposit',
        user__in=all_registered_users
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_withdrawals = Transaction.objects.filter(
        transaction_type='withdraw',
        user__in=all_registered_users
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    
    # Total balance - sum unwithdrawable + withdrawable
    total_balance = User.objects.aggregate(
        total=Sum(F('unwithdrawable_balance') + F('withdrawable_balance'))
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
        'new_starts_count_in_window': _get_new_starts_count_for_context(),
        'users_created_today': _get_users_created_today_count(),
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
        'recent_broadcasts': BroadcastMessage.objects.all().order_by('-created_at')[:5].select_related('sent_by').prefetch_related('recipients'),
    }
    
    # PHASE 3 OPTIMIZATION: Cache the context for 60 seconds
    # Convert QuerySets to lists for caching (QuerySets can't be cached directly)
    cacheable_context = context.copy()
    cacheable_context['pending_deposits'] = list(pending_deposits)
    cacheable_context['pending_withdraws'] = list(pending_withdraws)
    cacheable_context['approved_deposits'] = list(approved_deposits)
    cacheable_context['approved_withdraws'] = list(approved_withdraws)
    cacheable_context['active_games'] = list(active_games)
    cacheable_context['today_games_data'] = today_games_data  # Already a list
    cacheable_context['games_detail_data'] = games_detail_data  # Already a list
    cacheable_context['recent_broadcasts'] = list(context['recent_broadcasts'])
    
    # Cache for 60 seconds
    cache.set(cache_key, cacheable_context, 60)
    
    return render(request, 'admin/dashboard.html', context)


@require_http_methods(["GET"])
def search_user(request):
    """Search user by phone number or Telegram username."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    query = (request.GET.get('phone') or request.GET.get('q') or request.GET.get('username') or '').strip()
    if not query:
        return JsonResponse({'error': 'Phone number or username required'}, status=400)
    try:
        user = None
        # Search by Telegram username (with or without @)
        username_query = query.lstrip('@')
        if username_query:
            user = User.objects.filter(telegram_id__isnull=False, username__icontains=username_query).first()
        if not user:
            user = find_user_by_phone(query)
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)
        games_played = getattr(user, 'total_games_played', None)
        total_deposits = getattr(user, 'total_deposits_amount', None)
        total_withdrawals = getattr(user, 'total_withdrawals_amount', None)
        if games_played is None:
            games_played = Game.objects.filter(gamecards__user=user).distinct().count()
        # Compute wins from Game table (same as dashboard) so count is correct (distinct games)
        won_game_ids = set(Game.objects.filter(winner=user).values_list('id', flat=True))
        won_game_ids |= set(Game.winners.through.objects.filter(user=user).values_list('game_id', flat=True))
        total_wins = len(won_game_ids)
        if total_deposits is None:
            total_deposits = Transaction.objects.filter(user=user, transaction_type='deposit').aggregate(s=Sum('amount'))['s'] or Decimal('0')
        if total_withdrawals is None:
            total_withdrawals = Transaction.objects.filter(user=user, transaction_type='withdraw').aggregate(s=Sum('amount'))['s'] or Decimal('0')
        total_deposits = total_deposits or Decimal('0')
        total_withdrawals = total_withdrawals or Decimal('0')
        deposits = DepositRequest.objects.filter(user=user, status='approved')
        withdrawals = WithdrawRequest.objects.filter(user=user, status='approved')
        deposit_history = deposits.values('amount', 'platform', 'created_at')[:10]
        withdraw_history = withdrawals.values('amount', 'platform', 'created_at')[:10]
        from .user_utils import update_user_withdrawal_approval
        update_user_withdrawal_approval(user)
        user.refresh_from_db()
        return JsonResponse({
            'user': {
                'id': user.id,
                'username': user.username,
                'telegram_id': user.telegram_id,
                'phone_number': user.phone_number,
                'balance': float(user.balance),
                'created_at': user.created_at.isoformat(),
                'withdrawal_approved': user.withdrawal_approved,
            },
            'games_played': games_played,
            'total_wins': total_wins,
            'total_deposits': float(total_deposits),
            'total_withdrawals': float(total_withdrawals),
            'deposit_history': list(deposit_history),
            'withdraw_history': list(withdraw_history),
        })
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _parse_cbe_tx(tx_str):
    if not tx_str or len(tx_str.strip()) < 9:
        return None, None
    s = tx_str.strip().upper()
    if not s.startswith('FT') or len(s) < 9:
        return None, None
    return s[:-8], s[-8:]


@require_http_methods(["GET"])
def search_transaction(request):
    """Search by CBE (FT...) or Telebirr reference to see if already in CbeReceipt/TelebirrReceipt or in a request."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    tx = (request.GET.get('tx') or request.GET.get('transaction_number') or '').strip()
    if not tx:
        return JsonResponse({'error': 'Transaction number required'}, status=400)
    from .models import CbeReceipt, TelebirrReceipt
    ref, suffix = _parse_cbe_tx(tx)
    result = {'transaction_number': tx, 'found': False, 'valid_format': False, 'platform': None}
    if ref and suffix:
        result['platform'] = 'CBE'
        result['valid_format'] = True
        cbe = CbeReceipt.objects.filter(reference=ref, account_suffix=suffix).select_related('user').first()
        if cbe:
            result['found'] = True
            result['status'] = 'approved' if cbe.user_id else 'blocked'
            result['created_at'] = cbe.created_at.isoformat()
            if cbe.user_id:
                result['user_id'] = cbe.user_id
                result['username'] = cbe.user.username
                result['amount'] = float(cbe.amount)
            else:
                result['note'] = 'Manually added (block only)'
    else:
        # Telebirr: reference is the full string (e.g. DBK10S886V)
        if len(tx) >= 3:
            result['platform'] = 'Telebirr'
            result['valid_format'] = True
            tr = TelebirrReceipt.objects.filter(reference=tx).select_related('user').first()
            if tr:
                result['found'] = True
                result['status'] = 'approved' if tr.user_id else 'blocked'
                result['created_at'] = tr.created_at.isoformat()
                if tr.user_id:
                    result['user_id'] = tr.user_id
                    result['username'] = tr.user.username
                    result['amount'] = float(tr.amount)
                else:
                    result['note'] = 'Manually added (block only)'
    if not result['found']:
        dr = DepositRequest.objects.filter(transaction_reference__iexact=tx).select_related('user').first()
        if dr:
            result['found'] = True
            result['status'] = dr.status
            result['platform'] = result['platform'] or dr.platform
            result['user_id'] = dr.user_id
            result['username'] = dr.user.username
            result['amount'] = float(dr.amount)
            result['request_id'] = dr.id
            result['created_at'] = dr.created_at.isoformat()
    return JsonResponse(result)


@csrf_exempt
@require_http_methods(["POST"])
def add_cbe_receipt_ref_api(request):
    """Add a CBE transaction number to CbeReceipt (block-only: user=null, amount=0) so it cannot be reused. Use when a deposit was approved manually but the ref was not saved."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        body = json.loads(request.body) if request.body else {}
        tx = (body.get('transaction_number') or body.get('tx') or '').strip()
        if not tx:
            return JsonResponse({'error': 'transaction_number required'}, status=400)
        ref, suffix = _parse_cbe_tx(tx)
        if not ref or not suffix:
            return JsonResponse({'error': 'Invalid CBE transaction format (e.g. FT26048WBS7024627387)'}, status=400)
        from .models import CbeReceipt
        if CbeReceipt.objects.filter(reference=ref, account_suffix=suffix).exists():
            return JsonResponse({'error': 'This transaction number is already saved'}, status=400)
        CbeReceipt.objects.create(reference=ref, account_suffix=suffix, user=None, amount=0)
        return JsonResponse({'success': True, 'message': 'Transaction number saved; it cannot be used again.'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def delete_cbe_receipt_ref_api(request):
    """Remove a CBE transaction number from CbeReceipt so a deposit with that ref can be accepted again."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        body = json.loads(request.body) if request.body else {}
        tx = (body.get('transaction_number') or body.get('tx') or '').strip()
        if not tx:
            return JsonResponse({'error': 'transaction_number required'}, status=400)
        ref, suffix = _parse_cbe_tx(tx)
        if not ref or not suffix:
            return JsonResponse({'error': 'Invalid CBE transaction format'}, status=400)
        from .models import CbeReceipt
        deleted, _ = CbeReceipt.objects.filter(reference=ref, account_suffix=suffix).delete()
        if not deleted:
            return JsonResponse({'error': 'Transaction number not found'}, status=404)
        return JsonResponse({'success': True, 'message': 'Transaction number removed; it can be used again.'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def add_telebirr_receipt_ref_api(request):
    """Add a Telebirr reference to TelebirrReceipt (block-only: user=null, amount=0) so it cannot be reused."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        body = json.loads(request.body) if request.body else {}
        ref = (body.get('reference') or body.get('transaction_number') or body.get('tx') or '').strip()
        if not ref or len(ref) < 3:
            return JsonResponse({'error': 'reference required (e.g. Telebirr receipt number)'}, status=400)
        from .models import TelebirrReceipt
        if TelebirrReceipt.objects.filter(reference=ref).exists():
            return JsonResponse({'error': 'This reference is already saved'}, status=400)
        TelebirrReceipt.objects.create(reference=ref, user=None, amount=0)
        return JsonResponse({'success': True, 'message': 'Telebirr reference saved; it cannot be used again.'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def delete_telebirr_receipt_ref_api(request):
    """Remove a Telebirr reference from TelebirrReceipt so a deposit with that ref can be accepted again."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        body = json.loads(request.body) if request.body else {}
        ref = (body.get('reference') or body.get('transaction_number') or body.get('tx') or '').strip()
        if not ref:
            return JsonResponse({'error': 'reference required'}, status=400)
        from .models import TelebirrReceipt
        deleted, _ = TelebirrReceipt.objects.filter(reference=ref).delete()
        if not deleted:
            return JsonResponse({'error': 'Reference not found'}, status=404)
        return JsonResponse({'success': True, 'message': 'Telebirr reference removed; it can be used again.'})
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
            
            # Credit user: deposits go to withdrawable_balance
            from decimal import Decimal
            from django.db.models import F
            User.objects.filter(id=deposit.user.id).update(withdrawable_balance=F('withdrawable_balance') + Decimal(str(deposit.amount)))
            deposit.user.refresh_from_db()
            
            # Create transaction
            from .models import Transaction
            Transaction.objects.create(
                user=deposit.user,
                transaction_type='deposit',
                amount=deposit.amount,
                deposit=deposit,
                description=f'Deposit approved - Match ID: {deposit.id}'
            )
            try:
                from .stats_utils import record_deposit
                record_deposit(deposit.amount, deposit.user)
            except Exception:
                pass
            
            # Send notification to user via Telegram bot
            if deposit.user.telegram_id:
                message = (
                    f"✅ ገንዘቡ ገቢ ሆኗል!\n\n"
                    f"መጠን: {deposit.amount} ብር\n"
                    f"አዲስ ሂሳብዎ: {deposit.user.balance} ብር"
                )
                send_notification_sync(deposit.user.telegram_id, message)  # Ignore message_id for non-broadcast
            
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
                send_notification_sync(deposit.user.telegram_id, message)  # Ignore message_id for non-broadcast
            
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


@csrf_exempt
@require_http_methods(["POST"])
def approve_deposit_request_api(request, deposit_id):
    """Approve a deposit request. Optional body: { \"transaction_number\": \"FT...\" } for CBE to prevent reuse."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        deposit_request = DepositRequest.objects.get(id=deposit_id, status='pending')
        body = json.loads(request.body) if request.body else {}
        transaction_number = (body.get('transaction_number') or '').strip()
        if deposit_request.platform == 'CBE':
            if not transaction_number:
                return JsonResponse({'error': 'For CBE deposits, transaction number is required (e.g. FT... from receipt link)'}, status=400)
        if deposit_request.platform == 'CBE' and transaction_number:
            ref, suffix = _parse_cbe_tx(transaction_number)
            if ref and suffix:
                from .models import CbeReceipt
                if CbeReceipt.objects.filter(reference=ref, account_suffix=suffix).exists():
                    return JsonResponse({'error': 'This transaction number was already used'}, status=400)
                CbeReceipt.objects.create(
                    user=deposit_request.user,
                    reference=ref,
                    account_suffix=suffix,
                    amount=deposit_request.amount
                )
                deposit_request.transaction_reference = transaction_number
        deposit_request.status = 'approved'
        deposit_request.processed_at = timezone.now()
        deposit_request.processed_by = request.user if request.user.is_staff else None
        deposit_request.save()
        from django.db.models import F
        User.objects.filter(id=deposit_request.user.id).update(withdrawable_balance=F('withdrawable_balance') + Decimal(str(deposit_request.amount)))
        deposit_request.user.refresh_from_db()
        Transaction.objects.create(
            user=deposit_request.user,
            transaction_type='deposit',
            amount=deposit_request.amount,
            description=f'Deposit approved - {deposit_request.platform} - Request ID: {deposit_request.id}'
        )
        try:
            from .stats_utils import record_deposit
            record_deposit(deposit_request.amount, deposit_request.user)
        except Exception:
            pass
        try:
            from telegram_bot.notifications import send_notification_sync
            send_notification_sync(
                deposit_request.user.telegram_id,
                f"✅ ገንዘቡ ገቢ ሆኗል!\n\n"
                f"💰 መጠን: {deposit_request.amount} ብር\n"
                f"🏦 ወደ: {deposit_request.platform}\n\n"
                f"በሂሳብዎ ላይ ያለውን ለመመልከት /balance ይጫኑ።"
            )
        except Exception:
            pass
        return JsonResponse({'success': True, 'message': 'Deposit approved and credited'})
    except DepositRequest.DoesNotExist:
        return JsonResponse({'error': 'Deposit request not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def reject_deposit_request_api(request, deposit_id):
    """Delete a pending deposit request (no notification)."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        deposit_request = DepositRequest.objects.get(id=deposit_id, status='pending')
        deposit_request.delete()
        return JsonResponse({'success': True, 'message': 'Deposit request deleted'})
    except DepositRequest.DoesNotExist:
        return JsonResponse({'error': 'Deposit request not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def delete_failed_deposit_api(request, failed_id):
    """Delete a failed deposit request record (support cleanup)."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        fd = FailedDepositRequest.objects.get(id=failed_id)
        fd.delete()
        return JsonResponse({'success': True, 'message': 'Failed deposit record deleted'})
    except FailedDepositRequest.DoesNotExist:
        return JsonResponse({'error': 'Failed deposit record not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def approve_failed_deposit_api(request, failed_id):
    """Manually approve a failed deposit: credit user, save ref to CbeReceipt (CBE) or TelebirrReceipt (Telebirr), then delete the failed record. Optional body: transaction_number/reference so the ref is saved and cannot be reused."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        fd = FailedDepositRequest.objects.select_related('user').get(id=failed_id)
        amount = fd.amount
        if amount is None or amount <= 0:
            return JsonResponse({'error': 'Cannot approve: no valid amount on this failed record'}, status=400)
        user = fd.user
        body = json.loads(request.body) if request.body else {}
        transaction_number = (body.get('transaction_number') or body.get('reference') or '').strip()
        from .models import CbeReceipt, TelebirrReceipt
        ref, suffix = None, None
        if fd.platform == 'CBE':
            if transaction_number:
                ref, suffix = _parse_cbe_tx(transaction_number)
            if not ref or not suffix:
                ref, suffix = fd.reference, fd.account_suffix
            if ref and suffix:
                if CbeReceipt.objects.filter(reference=ref, account_suffix=suffix).exists():
                    return JsonResponse({'error': 'This transaction was already used'}, status=400)
                CbeReceipt.objects.create(user=user, reference=ref, account_suffix=suffix, amount=amount)
        elif fd.platform == 'Telebirr':
            tref = transaction_number or fd.reference or ''
            tref = tref.strip()
            if tref:
                if TelebirrReceipt.objects.filter(reference=tref).exists():
                    return JsonResponse({'error': 'This Telebirr reference was already used'}, status=400)
                TelebirrReceipt.objects.create(user=user, reference=tref, amount=amount)
        from django.db.models import F
        User.objects.filter(id=user.id).update(withdrawable_balance=F('withdrawable_balance') + amount)
        user.refresh_from_db()
        Transaction.objects.create(
            user=user,
            transaction_type='deposit',
            amount=amount,
            description=f'Deposit approved from failed record - {fd.platform} - Failed ID: {fd.id}'
        )
        try:
            from .stats_utils import record_deposit
            record_deposit(amount, user)
        except Exception:
            pass
        try:
            from telegram_bot.notifications import send_notification_sync
            send_notification_sync(
                user.telegram_id,
                f"✅ ገንዘቡ ገቢ ሆኗል!\n\n💰 መጠን: {amount} ብር\n🏦 ወደ: {fd.platform}\n\nበሂሳብዎ ላይ ያለውን ለመመልከት /balance ይጫኑ።"
            )
        except Exception:
            pass
        fd.delete()
        return JsonResponse({'success': True, 'message': 'Deposit approved and credited'})
    except FailedDepositRequest.DoesNotExist:
        return JsonResponse({'error': 'Failed deposit record not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def approve_withdraw_request_api(request, withdraw_id):
    """API endpoint to approve a withdraw request"""
    # Check authentication (works for both admin and second admin)
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        withdraw_request = WithdrawRequest.objects.get(id=withdraw_id, status='pending')
        
        # Check withdrawable_balance (only withdrawable can be withdrawn)
        if withdraw_request.user.withdrawable_balance < withdraw_request.amount:
            return JsonResponse({'error': 'Insufficient balance'}, status=400)
        
        withdraw_request.status = 'approved'
        withdraw_request.processed_at = timezone.now()
        withdraw_request.processed_by = request.user if request.user.is_staff else None
        withdraw_request.save()
        
        from django.db.models import F
        User.objects.filter(id=withdraw_request.user.id).update(
            withdrawable_balance=F('withdrawable_balance') - Decimal(str(withdraw_request.amount)),
            last_withdrawal_approved_at=timezone.now()
        )
        withdraw_request.user.refresh_from_db()
        
        # Create transaction
        Transaction.objects.create(
            user=withdraw_request.user,
            transaction_type='withdraw',
            amount=withdraw_request.amount,
            description=f'Withdrawal approved - {withdraw_request.platform} - Request ID: {withdraw_request.id}'
        )
        try:
            from .stats_utils import record_withdrawal
            record_withdrawal(withdraw_request.amount, withdraw_request.user)
        except Exception:
            pass
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


@csrf_exempt
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
@require_http_methods(["POST"])
def delete_withdraw_request_api(request, withdraw_id):
    """Delete a pending withdraw request without notifying the user."""
    if not (request.user.is_staff or request.session.get('second_admin_authenticated')):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        withdraw_request = WithdrawRequest.objects.get(id=withdraw_id, status='pending')
        withdraw_request.delete()
        return JsonResponse({'success': True, 'message': 'Withdraw request deleted'})
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
    
    # Check if this is a second admin (not main admin)
    is_second_admin = request.session.get('second_admin_authenticated') and not request.user.is_staff
    
    if request.method == 'GET':
        response_data = {
            'bid_amount': float(settings.bid_amount),
            'card_selection_timer': settings.card_selection_timer,
            'time_between_calls': settings.time_between_calls,
            'total_cards': settings.total_cards,
            'min_withdraw': float(settings.min_withdraw),
            'max_withdrawal': float(settings.max_withdrawal) if settings.max_withdrawal else None,
            'percentage_cut': float(settings.percentage_cut),
            'automatic_mode_enabled': settings.automatic_mode_enabled,
            'deposit_accounts': settings.deposit_accounts,
            'support_phone': settings.support_phone,
            'instruction_text': getattr(settings, 'instruction_text', '') or '',
            'allow_system_account': settings.allow_system_account,
            'free_play': settings.free_play,
            'system_accounts_min': getattr(settings, 'system_accounts_min', 15),
            'system_accounts_max': getattr(settings, 'system_accounts_max', 30),
            'winning_patterns': getattr(settings, 'winning_patterns', ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']),
            'telebirr_verify_api_key': getattr(settings, 'telebirr_verify_api_key', '') or '',
            'cbe_use_fallback_proxy': getattr(settings, 'cbe_use_fallback_proxy', False),
            'daily_new_start_limit': getattr(settings, 'daily_new_start_limit', 100),
            'disable_bot_start': getattr(settings, 'disable_bot_start', False),
            'disable_bot_register': getattr(settings, 'disable_bot_register', False),
            'disable_bot_transfer': getattr(settings, 'disable_bot_transfer', False),
        }
        try:
            response_data['users_created_today'] = _get_users_created_today_count()
        except Exception:
            response_data['users_created_today'] = 0
        try:
            from .redis_utils import get_new_starts_window_count
            window_data = get_new_starts_window_count()
            count = window_data.get('count', 0)
            window_end_ts = window_data.get('window_end_ts')
            if count == 0 and window_end_ts is None:
                response_data['new_starts_count_in_window'] = response_data.get('users_created_today', 0)
            else:
                response_data['new_starts_count_in_window'] = count
        except Exception:
            response_data['new_starts_count_in_window'] = response_data.get('users_created_today', 0)
        return JsonResponse(response_data)
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        
        try:
            # Get the actual database object (bypass cache for saving)
            # This ensures we're modifying the real database object
            settings_obj, created = GameSettings.objects.get_or_create(pk=1)
            
            if 'bid_amount' in data:
                settings_obj.bid_amount = Decimal(str(data['bid_amount']))
            if 'card_selection_timer' in data:
                settings_obj.card_selection_timer = int(data['card_selection_timer'])
            if 'time_between_calls' in data:
                settings_obj.time_between_calls = int(data['time_between_calls'])
            if 'total_cards' in data:
                settings_obj.total_cards = int(data['total_cards'])
            if 'min_withdraw' in data:
                settings_obj.min_withdraw = Decimal(str(data['min_withdraw']))
            if 'max_withdrawal' in data:
                val = data['max_withdrawal']
                if val is None or val == '' or (isinstance(val, (int, float)) and float(val) <= 0):
                    settings_obj.max_withdrawal = None
                else:
                    settings_obj.max_withdrawal = Decimal(str(val))
            if 'percentage_cut' in data:
                settings_obj.percentage_cut = Decimal(str(data['percentage_cut']))
            if 'automatic_mode_enabled' in data:
                settings_obj.automatic_mode_enabled = bool(data['automatic_mode_enabled'])
            if 'deposit_accounts' in data:
                settings_obj.deposit_accounts = data['deposit_accounts']
            if 'support_phone' in data:
                settings_obj.support_phone = data['support_phone'].strip()
            if 'instruction_text' in data:
                settings_obj.instruction_text = (data['instruction_text'] or '').strip()
            # Allow both main admin and second admin to update system account settings
            if 'allow_system_account' in data:
                settings_obj.allow_system_account = bool(data['allow_system_account'])
            if 'free_play' in data:
                # free_play can only be enabled if allow_system_account is enabled
                if bool(data['free_play']) and not settings_obj.allow_system_account:
                    return JsonResponse({'error': 'Free play can only be enabled when system accounts are allowed'}, status=400)
                settings_obj.free_play = bool(data['free_play'])
            if 'system_accounts_min' in data:
                min_val = int(data['system_accounts_min'])
                if min_val < 1:
                    min_val = 1
                settings_obj.system_accounts_min = min_val
            if 'system_accounts_max' in data:
                max_val = min(100, int(data['system_accounts_max']))  # Cap at 100 (matches FAKE_USER_NAMES count)
                if max_val < settings_obj.system_accounts_min:
                    max_val = settings_obj.system_accounts_min
                settings_obj.system_accounts_max = max_val
            if 'winning_patterns' in data:
                # Validate winning patterns
                valid_patterns = ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']
                patterns = data['winning_patterns']
                if isinstance(patterns, list):
                    # Filter to only valid patterns
                    settings_obj.winning_patterns = [p for p in patterns if p in valid_patterns]
                    # Ensure at least one pattern is enabled
                    if not settings_obj.winning_patterns:
                        settings_obj.winning_patterns = ['horizontal']  # Default to horizontal if none selected
            if 'telebirr_verify_api_key' in data:
                settings_obj.telebirr_verify_api_key = (data['telebirr_verify_api_key'] or '').strip()
            if 'cbe_use_fallback_proxy' in data:
                settings_obj.cbe_use_fallback_proxy = bool(data['cbe_use_fallback_proxy'])
            if 'daily_new_start_limit' in data:
                val = int(data['daily_new_start_limit'])
                settings_obj.daily_new_start_limit = max(0, val)
            if 'disable_bot_start' in data:
                settings_obj.disable_bot_start = bool(data['disable_bot_start'])
            if 'disable_bot_register' in data:
                settings_obj.disable_bot_register = bool(data['disable_bot_register'])
            if 'disable_bot_transfer' in data:
                settings_obj.disable_bot_transfer = bool(data['disable_bot_transfer'])
            
            settings_obj.save()
            
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
    
    # PHASE 3 OPTIMIZATION: Cache dashboard data for 60 seconds
    from django.core.cache import cache
    cache_key = 'admin:second_dashboard:data'
    cached_data = cache.get(cache_key)
    
    if cached_data:
        # Return cached data (much faster)
        return render(request, 'admin/second_admin_dashboard.html', cached_data)
    
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
    
    # Revenue statistics - OPTIMIZED
    settings = GameSettings.get_settings()
    percentage_cut = settings.percentage_cut
    from .models import GameCard
    
    def calculate_revenue(games_queryset):
        """
        Calculate revenue from games, excluding fake users.
        Revenue = (real_users_count * bet_amount) * percentage_cut / 100
        Only counts real users who paid - fake users don't generate revenue
        OPTIMIZED: Uses aggregation instead of per-game queries
        """
        games_with_counts = games_queryset.annotate(
            real_users_count=Count('gamecards', distinct=True)
        ).filter(real_users_count__gt=0)
        
        # Calculate total revenue using aggregation
        # Note: Cannot use .only() with annotations, so we iterate normally
        total = Decimal('0')
        for game in games_with_counts:
            total_collected = Decimal(str(game.real_users_count)) * game.bet_amount
            cut = (total_collected * percentage_cut) / Decimal('100')
            total += cut
        return total
    
    completed_games = Game.objects.filter(status='completed')
    
    # OPTIMIZED: Cache revenue calculations for 5 minutes
    from django.core.cache import cache as revenue_cache
    revenue_cache_key_prefix = 'admin_revenue_'
    
    def get_cached_revenue(key_suffix, queryset):
        cache_key = f'{revenue_cache_key_prefix}{key_suffix}'
        cached = revenue_cache.get(cache_key)
        if cached is not None:
            return cached
        result = calculate_revenue(queryset)
        revenue_cache.set(cache_key, result, 300)  # Cache for 5 minutes
        return result
    
    revenue_today = get_cached_revenue('today', completed_games.filter(completed_at__gte=today_start, completed_at__lte=today_end))
    revenue_yesterday = get_cached_revenue('yesterday', completed_games.filter(completed_at__gte=yesterday_start, completed_at__lt=yesterday_end))
    revenue_week = get_cached_revenue('week', completed_games.filter(completed_at__gte=week_start, completed_at__lte=week_end))
    revenue_last_week = get_cached_revenue('last_week', completed_games.filter(completed_at__gte=last_week_start, completed_at__lte=last_week_end))
    revenue_month = get_cached_revenue('month', completed_games.filter(completed_at__gte=month_start, completed_at__lte=month_end))
    revenue_last_month = get_cached_revenue('last_month', completed_games.filter(completed_at__gte=last_month_start, completed_at__lte=last_month_end))
    revenue_total = get_cached_revenue('total', completed_games)
    
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
    # Ensure new fields exist with defaults (for backward compatibility if migration not run)
    if not hasattr(game_settings, 'system_accounts_min'):
        game_settings.system_accounts_min = 15
    if not hasattr(game_settings, 'system_accounts_max'):
        game_settings.system_accounts_max = 30
    if not hasattr(game_settings, 'winning_patterns') or not game_settings.winning_patterns:
        game_settings.winning_patterns = ['horizontal', 'vertical', 'diagonal', 'corner', 'full_card']
    
    # Get today's games with winner info (limit to 5 for initial display) - OPTIMIZED with annotations
    from .fake_user_manager import get_fake_user_count_for_game
    today_games_all = Game.objects.filter(created_at__gte=today_start).order_by('-created_at')
    today_games_count = today_games_all.count()
    today_games = today_games_all[:5].prefetch_related(
        'gamecards',
        'winners',
        Prefetch('called_numbers', queryset=CalledNumber.objects.all().only('number'))
    ).select_related('winner').annotate(
        fake_user_count=Count('fake_cards', distinct=True)
    )
    
    today_games_data = []
    for game in today_games:
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        # REMOVED: Automatic/manual counting per game (too expensive - JSON parsing for each card)
        
        # Count real and system users - use prefetched gamecards count and annotated fake count
        real_users_count = game.gamecards.count()
        system_users_count = game.fake_user_count or 0
        
        today_games_data.append({
            'game': game,
            'players': game.total_players,
            'bid_amount': game.bet_amount,
            'automatic_count': 0,  # Removed expensive calculation
            'manual_count': 0,  # Removed expensive calculation
            'winner_phones': winner_phones,
            'real_users': real_users_count,
            'system_users': system_users_count,
        })
    
    # Get game details for the game detail section - OPTIMIZED: Limited to 50 most recent games
    all_games_detail = Game.objects.all().order_by('-created_at')[:10].prefetch_related(
        'gamecards',
        'winners',
        Prefetch('called_numbers', queryset=CalledNumber.objects.all().only('number'))
    ).select_related('winner').annotate(
        fake_user_count=Count('fake_cards', distinct=True)
    )
    
    games_detail_data = []
    for game in all_games_detail:
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        # REMOVED: Automatic/manual counting per game (too expensive - JSON parsing for each card)
        
        # Limit called_numbers to last 20 to avoid loading all 75
        called_numbers_list = [cn.number for cn in game.called_numbers.all()[:10]]
        
        games_detail_data.append({
            'game': game,
            'players': game.total_players,
            'bid_amount': game.bet_amount,
            'derash_amount': game.derash_amount,
            'automatic_count': 0,  # Removed expensive calculation
            'manual_count': 0,  # Removed expensive calculation
            'winner_phones': winner_phones,
            'called_numbers': called_numbers_list,
        })
    
    # Get recent transfers
    recent_transfers = Transfer.objects.all().order_by('-created_at')[:10]
    
    # Calculate total automatic and manual games - OPTIMIZED with caching
    from .models import GameCard
    from django.core.cache import cache
    
    # Cache this expensive calculation for 5 minutes
    cache_key = 'admin_total_automatic_manual_games'
    cached_result = cache.get(cache_key)
    
    # PHASE 3 FIX: Validate cached result before unpacking
    if cached_result is not None and isinstance(cached_result, (tuple, list)) and len(cached_result) == 2:
        total_automatic_games, total_manual_games = cached_result
    else:
        # Use only() to limit fields loaded, but regular queryset (no iterator to avoid cursor issues)
        all_cards = GameCard.objects.only('mode_history')
        total_automatic_games = 0
        total_manual_games = 0
        
        for card in all_cards:
            mode_history = card.mode_history or []
            has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
            if has_automatic:
                total_automatic_games += 1
            else:
                total_manual_games += 1
        
        # Cache for 5 minutes (300 seconds)
        cache.set(cache_key, (total_automatic_games, total_manual_games), 300)
    
    # Get registered users (can edit but NOT delete) - OPTIMIZED: Limited to 100 most recent
    registered_users_raw = User.objects.filter(telegram_id__isnull=False).order_by('-created_at')[:20].annotate(
        games_played=Count('gamecards__game', distinct=True),
        wins=Count('won_games', distinct=True),
        user_total_deposits=Sum('transactions__amount', filter=Q(transactions__transaction_type='deposit')),
        user_total_withdrawals=Sum('transactions__amount', filter=Q(transactions__transaction_type='withdraw'))
    )
    
    registered_users = []
    for user in registered_users_raw:
        games_played = user.games_played or 0
        wins = user.wins or 0
        user_total_deposits = user.user_total_deposits or Decimal('0')
        user_total_withdrawals = user.user_total_withdrawals or Decimal('0')
        
        registered_users.append({
            'user': user,
            'games_played': games_played,
            'wins': wins,
            'total_deposits': user_total_deposits,
            'total_withdrawals': user_total_withdrawals,
        })
    
    # Financial statistics - Calculate from ALL registered users (not just the limited display list)
    # Sum deposits and withdrawals from all registered users' transactions
    all_registered_users = User.objects.filter(telegram_id__isnull=False)
    total_deposits = Transaction.objects.filter(
        transaction_type='deposit',
        user__in=all_registered_users
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_withdrawals = Transaction.objects.filter(
        transaction_type='withdraw',
        user__in=all_registered_users
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_balance = User.objects.aggregate(
        total=Sum(F('unwithdrawable_balance') + F('withdrawable_balance'))
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
        'new_starts_count_in_window': _get_new_starts_count_for_context(),
        'users_created_today': _get_users_created_today_count(),
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
        'recent_broadcasts': BroadcastMessage.objects.all().order_by('-created_at')[:5].select_related('sent_by').prefetch_related('recipients'),
    }
    
    # PHASE 3 OPTIMIZATION: Cache the context for 60 seconds
    # Convert QuerySets to lists for caching (QuerySets can't be cached directly)
    cacheable_context = context.copy()
    cacheable_context['pending_deposits'] = list(pending_deposits)
    cacheable_context['pending_withdraws'] = list(pending_withdraws)
    cacheable_context['approved_deposits'] = list(approved_deposits)
    cacheable_context['approved_withdraws'] = list(approved_withdraws)
    cacheable_context['active_games'] = list(active_games)
    cacheable_context['today_games_data'] = today_games_data  # Already a list
    cacheable_context['games_detail_data'] = games_detail_data  # Already a list
    cacheable_context['recent_broadcasts'] = list(context['recent_broadcasts'])
    
    # Cache for 60 seconds
    cache.set(cache_key, cacheable_context, 60)
    
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
    
    # Prefer aggregate tables (survives prune); fallback to live queries
    ag = None
    try:
        from .stats_utils import get_dashboard_aggregates
        ag = get_dashboard_aggregates(periods)
    except Exception:
        pass
    if ag is not None:
        games_today = ag['games_today']
        games_yesterday = ag['games_yesterday']
        games_week = ag['games_week']
        games_last_week = ag['games_last_week']
        games_month = ag['games_month']
        games_last_month = ag['games_last_month']
        games_total = ag['games_total']
        revenue_today = ag['revenue_today']
        revenue_yesterday = ag['revenue_yesterday']
        revenue_week = ag['revenue_week']
        revenue_last_week = ag['revenue_last_week']
        revenue_month = ag['revenue_month']
        revenue_last_month = ag['revenue_last_month']
        revenue_total = ag['revenue_total']
        total_deposits = ag['total_deposits']
        total_withdrawals = ag['total_withdrawals']
        total_balance = ag['total_balance']
    else:
        # Games played statistics (from current records)
        games_today = Game.objects.filter(created_at__gte=today_start, created_at__lte=today_end).count()
        games_yesterday = Game.objects.filter(created_at__gte=yesterday_start, created_at__lt=yesterday_end).count()
        games_week = Game.objects.filter(created_at__gte=week_start, created_at__lte=week_end).count()
        games_last_week = Game.objects.filter(created_at__gte=last_week_start, created_at__lte=last_week_end).count()
        games_month = Game.objects.filter(created_at__gte=month_start, created_at__lte=month_end).count()
        games_last_month = Game.objects.filter(created_at__gte=last_month_start, created_at__lte=last_month_end).count()
        games_total = Game.objects.count()
        settings = GameSettings.get_settings()
        percentage_cut = settings.percentage_cut
        from .models import GameCard
        def calculate_revenue(games_queryset):
            games_with_counts = games_queryset.annotate(
                real_users_count=Count('gamecards', distinct=True)
            ).filter(real_users_count__gt=0)
            total = Decimal('0')
            for game in games_with_counts:
                total_collected = Decimal(str(game.real_users_count)) * game.bet_amount
                cut = (total_collected * percentage_cut) / Decimal('100')
                total += cut
            return total
        completed_games = Game.objects.filter(status='completed')
        from django.core.cache import cache as revenue_cache
        revenue_cache_key_prefix = 'admin_revenue_'
        def get_cached_revenue(key_suffix, queryset):
            cache_key = f'{revenue_cache_key_prefix}{key_suffix}'
            cached = revenue_cache.get(cache_key)
            if cached is not None:
                return cached
            result = calculate_revenue(queryset)
            revenue_cache.set(cache_key, result, 300)
            return result
        revenue_today = get_cached_revenue('today', completed_games.filter(completed_at__gte=today_start, completed_at__lte=today_end))
        revenue_yesterday = get_cached_revenue('yesterday', completed_games.filter(completed_at__gte=yesterday_start, completed_at__lt=yesterday_end))
        revenue_week = get_cached_revenue('week', completed_games.filter(completed_at__gte=week_start, completed_at__lte=week_end))
        revenue_last_week = get_cached_revenue('last_week', completed_games.filter(completed_at__gte=last_week_start, completed_at__lte=last_week_end))
        revenue_month = get_cached_revenue('month', completed_games.filter(completed_at__gte=month_start, completed_at__lte=month_end))
        revenue_last_month = get_cached_revenue('last_month', completed_games.filter(completed_at__gte=last_month_start, completed_at__lte=last_month_end))
        revenue_total = get_cached_revenue('total', completed_games)
        all_registered_users = User.objects.filter(telegram_id__isnull=False)
        total_deposits = Transaction.objects.filter(
            transaction_type='deposit',
            user__in=all_registered_users
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        total_withdrawals = Transaction.objects.filter(
            transaction_type='withdraw',
            user__in=all_registered_users
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        total_balance = User.objects.aggregate(total=Sum(F('unwithdrawable_balance') + F('withdrawable_balance')))['total'] or Decimal('0')
    
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
    try:
        failed_deposits = FailedDepositRequest.objects.select_related('user').order_by('-created_at')[:20]
    except Exception:
        failed_deposits = []
    
    # Count totals for show more functionality
    pending_deposits_count = DepositRequest.objects.filter(status='pending').count()
    pending_withdraws_count = WithdrawRequest.objects.filter(status='pending').count()
    approved_deposits_count = DepositRequest.objects.filter(status='approved').count()
    approved_withdraws_count = WithdrawRequest.objects.filter(status='approved').count()
    
    # Active games
    active_games = Game.objects.filter(status__in=['waiting', 'active']).order_by('-created_at')
    
    # Today's games (limit to 5 for initial display) - OPTIMIZED with annotations
    from .fake_user_manager import get_fake_user_count_for_game
    today_games_all = Game.objects.filter(created_at__gte=today_start).order_by('-created_at')
    today_games_count = today_games_all.count()
    today_games = today_games_all[:5].prefetch_related(
        'gamecards',
        'winners'
    ).select_related('winner').annotate(
        fake_user_count=Count('fake_cards', distinct=True)
    )
    
    today_games_data = []
    for game in today_games:
        # REMOVED: Automatic/manual counting per game (too expensive - JSON parsing for each card)
        
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        # Count real and system users - use prefetched gamecards count and annotated fake count
        real_users_count = game.gamecards.count()
        system_users_count = game.fake_user_count or 0
        
        today_games_data.append({
            'id': game.id,
            'players': game.total_players,
            'bid_amount': float(game.bet_amount),
            'automatic_count': 0,  # Removed expensive calculation
            'manual_count': 0,  # Removed expensive calculation
            'winner_phones': winner_phones,
            'real_users': real_users_count,
            'system_users': system_users_count,
            'status': game.status,
            'created_at': game.created_at.strftime('%H:%M'),
        })
    
    # Registered users - limit and sort from query params
    try:
        users_limit = max(1, min(500, int(request.GET.get('registered_limit', 10))))
    except (ValueError, TypeError):
        users_limit = 10
    sort_param = (request.GET.get('registered_sort') or 'created_at').strip().lower()
    valid_sorts = {'balance', 'wins', 'games_played', 'total_deposits', 'total_withdrawals', 'transfer_in', 'created_at'}
    if sort_param not in valid_sorts:
        sort_param = 'created_at'
    registered_users_count = User.objects.filter(telegram_id__isnull=False).count()
    base_qs = User.objects.filter(telegram_id__isnull=False)
    if sort_param == 'wins':
        registered_users_raw = list(base_qs.order_by('-created_at')[:500])
    else:
        if sort_param == 'transfer_in':
            base_qs = base_qs.annotate(transfer_in_sum=Coalesce(Sum('transfers_received__amount'), Decimal('0')))
            registered_users_raw = list(base_qs.order_by('-transfer_in_sum')[:users_limit])
        elif sort_param == 'balance':
            base_qs = base_qs.annotate(total_bal=F('unwithdrawable_balance') + F('withdrawable_balance'))
            registered_users_raw = list(base_qs.order_by('-total_bal')[:users_limit])
        elif sort_param == 'games_played':
            registered_users_raw = list(base_qs.order_by('-total_games_played')[:users_limit])
        elif sort_param == 'total_deposits':
            registered_users_raw = list(base_qs.order_by('-total_deposits_amount')[:users_limit])
        elif sort_param == 'total_withdrawals':
            registered_users_raw = list(base_qs.order_by('-total_withdrawals_amount')[:users_limit])
        else:
            registered_users_raw = list(base_qs.order_by('-created_at')[:users_limit])
    user_ids = [u.id for u in registered_users_raw]
    # Transfer in (total received) per user
    transfer_in_by_user = dict(
        Transfer.objects.filter(to_user_id__in=user_ids).values('to_user_id').annotate(total=Sum('amount')).values_list('to_user_id', 'total')
    )
    # Compute wins from Game table (winner FK + winners M2M)
    win_count_by_user = {}
    if user_ids:
        for winner_id, game_id in Game.objects.filter(winner_id__in=user_ids).values_list('winner_id', 'id'):
            if winner_id not in win_count_by_user:
                win_count_by_user[winner_id] = set()
            win_count_by_user[winner_id].add(game_id)
        through = Game.winners.through
        for uid, gid in through.objects.filter(user_id__in=user_ids).values_list('user_id', 'game_id'):
            if uid not in win_count_by_user:
                win_count_by_user[uid] = set()
            win_count_by_user[uid].add(gid)
        win_count_by_user = {uid: len(s) for uid, s in win_count_by_user.items()}
    if sort_param == 'wins':
        registered_users_raw.sort(key=lambda u: win_count_by_user.get(u.id, u.total_wins or 0), reverse=True)
        registered_users_raw = registered_users_raw[:users_limit]
    registered_users = []
    for user in registered_users_raw:
        wins = win_count_by_user.get(user.id)
        if wins is None:
            wins = user.total_wins or 0
        transfer_in = transfer_in_by_user.get(user.id) or Decimal('0')
        registered_users.append({
            'id': user.id,
            'username': user.username,
            'telegram_id': user.telegram_id,
            'phone_number': user.phone_number or '-',
            'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or '-',
            'unwithdrawable_balance': float(user.unwithdrawable_balance or 0),
            'withdrawable_balance': float(user.withdrawable_balance or 0),
            'games_played': user.total_games_played or 0,
            'wins': wins,
            'total_deposits': float(user.total_deposits_amount or 0),
            'total_withdrawals': float(user.total_withdrawals_amount or 0),
            'transfer_in': float(transfer_in),
            'withdrawal_approved': user.withdrawal_approved,
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M'),
        })
    
    # (total_deposits, total_withdrawals, total_balance set above from aggregates or fallback)
    
    # Game mode statistics - OPTIMIZED with caching
    from .models import GameCard
    from django.core.cache import cache
    
    # Cache this expensive calculation for 5 minutes
    cache_key = 'admin_total_automatic_manual_games'
    cached_result = cache.get(cache_key)
    
    # PHASE 3 FIX: Validate cached result before unpacking
    if cached_result is not None and isinstance(cached_result, (tuple, list)) and len(cached_result) == 2:
        total_automatic_games, total_manual_games = cached_result
    else:
        # Use only() to limit fields loaded, but regular queryset (no iterator to avoid cursor issues)
        all_cards = GameCard.objects.only('mode_history')
        total_automatic_games = 0
        total_manual_games = 0
        for card in all_cards:
            mode_history = card.mode_history or []
            has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
            if has_automatic:
                total_automatic_games += 1
            else:
                total_manual_games += 1
        
        # Cache for 5 minutes (300 seconds)
        cache.set(cache_key, (total_automatic_games, total_manual_games), 300)
    
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
    
    failed_deposits_data = []
    try:
        for fd in failed_deposits:
            failed_deposits_data.append({
                'id': fd.id,
                'username': fd.user.username,
                'amount': float(fd.amount) if fd.amount else None,
                'platform': fd.platform,
                'deposit_text': (fd.deposit_text or '')[:500],
                'failure_reason': fd.failure_reason,
                'reference': fd.reference,
                'account_suffix': fd.account_suffix,
                'created_at': fd.created_at.strftime('%Y-%m-%d %H:%M'),
            })
    except Exception:
        failed_deposits_data = []
    
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
        'registered_users_count': registered_users_count,
        'pending_deposits': pending_deposits_data,
        'pending_withdraws': pending_withdraws_data,
        'approved_deposits': approved_deposits_data,
        'approved_withdraws': approved_withdraws_data,
        'pending_deposits_count': pending_deposits_count,
        'pending_withdraws_count': pending_withdraws_count,
        'approved_deposits_count': approved_deposits_count,
        'approved_withdraws_count': approved_withdraws_count,
        'failed_deposits': failed_deposits_data,
        'recent_transfers': [
            {
                'id': t.id,
                'from_username': t.from_user.username,
                'from_phone': t.from_user.phone_number or 'N/A',
                'to_username': t.to_user.username,
                'to_phone': t.to_user.phone_number or 'N/A',
                'amount': float(t.amount),
                'created_at': t.created_at.strftime('%Y-%m-%d %H:%M'),
            }
            for t in Transfer.objects.all().order_by('-created_at')[:10].select_related('from_user', 'to_user')
        ],
        'games_detail': [
            {
                'id': g.id,
                'status': g.status,
                'players': g.total_players,
                'bid_amount': float(g.bet_amount),
                'derash_amount': float(g.derash_amount),
                'winner_phones': list({(w.phone_number or 'N/A') for w in [g.winner] + list(g.winners.all()) if w}),
                'called_numbers': [cn.number for cn in g.called_numbers.all()[:10]],
                'created_at': g.created_at.strftime('%Y-%m-%d %H:%M'),
            }
            for g in Game.objects.all().order_by('-created_at')[:10].prefetch_related(
                'winners', Prefetch('called_numbers', queryset=CalledNumber.objects.all().only('number'))
            ).select_related('winner')
        ],
        'recent_broadcasts': [
            {
                'id': b.id,
                'message_text': (b.message_text or '')[:100] + ('…' if len(b.message_text or '') > 100 else ''),
                'amount_added': float(b.amount_added) if b.amount_added else None,
                'sent_by': b.sent_by.username if b.sent_by else 'System',
                'recipients_count': b.recipients.count(),
                'created_at': b.created_at.strftime('%Y-%m-%d %H:%M'),
            }
            for b in BroadcastMessage.objects.all().order_by('-created_at')[:5].select_related('sent_by')
        ],
        'second_admin_username': (SecondAdmin.objects.first().username or '') if SecondAdmin.objects.exists() else '',
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
    from .models import GameCard
    
    def calculate_revenue(games_queryset):
        """
        Calculate revenue from games, excluding fake users.
        Revenue = (real_users_count * bet_amount) * percentage_cut / 100
        Only counts real users who paid - fake users don't generate revenue
        OPTIMIZED: Uses aggregation instead of per-game queries
        """
        games_with_counts = games_queryset.annotate(
            real_users_count=Count('gamecards', distinct=True)
        ).filter(real_users_count__gt=0)
        
        # Calculate total revenue using aggregation
        # Note: Cannot use .only() with annotations, so we iterate normally
        total = Decimal('0')
        for game in games_with_counts:
            total_collected = Decimal(str(game.real_users_count)) * game.bet_amount
            cut = (total_collected * percentage_cut) / Decimal('100')
            total += cut
        return total
    
    completed_games = Game.objects.filter(status='completed')
    
    # OPTIMIZED: Cache revenue calculations for 5 minutes
    from django.core.cache import cache as revenue_cache
    revenue_cache_key_prefix = 'admin_revenue_'
    
    def get_cached_revenue(key_suffix, queryset):
        cache_key = f'{revenue_cache_key_prefix}{key_suffix}'
        cached = revenue_cache.get(cache_key)
        if cached is not None:
            return cached
        result = calculate_revenue(queryset)
        revenue_cache.set(cache_key, result, 300)  # Cache for 5 minutes
        return result
    
    revenue_today = get_cached_revenue('today', completed_games.filter(completed_at__gte=today_start, completed_at__lte=today_end))
    revenue_yesterday = get_cached_revenue('yesterday', completed_games.filter(completed_at__gte=yesterday_start, completed_at__lt=yesterday_end))
    revenue_week = get_cached_revenue('week', completed_games.filter(completed_at__gte=week_start, completed_at__lte=week_end))
    revenue_last_week = get_cached_revenue('last_week', completed_games.filter(completed_at__gte=last_week_start, completed_at__lte=last_week_end))
    revenue_month = get_cached_revenue('month', completed_games.filter(completed_at__gte=month_start, completed_at__lte=month_end))
    revenue_last_month = get_cached_revenue('last_month', completed_games.filter(completed_at__gte=last_month_start, completed_at__lte=last_month_end))
    revenue_total = get_cached_revenue('total', completed_games)
    
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
    
    # Get today's games - check if all games are requested - OPTIMIZED with annotations
    from .fake_user_manager import get_fake_user_count_for_game
    today_games_all = Game.objects.filter(created_at__gte=today_start).order_by('-created_at')
    today_games_count = today_games_all.count()
    # Check if 'all' parameter is passed to return all games
    show_all = request.GET.get('all', 'false').lower() == 'true'
    today_games_queryset = today_games_all if show_all else today_games_all[:5]
    today_games = today_games_queryset.prefetch_related(
        'gamecards',
        'winners'
    ).select_related('winner').annotate(
        fake_user_count=Count('fake_cards', distinct=True)
    )
    
    today_games_data = []
    for game in today_games:
        winner_phones = []
        if game.winner:
            winner_phones.append(game.winner.phone_number or 'N/A')
        for winner in game.winners.all():
            phone = winner.phone_number or 'N/A'
            if phone not in winner_phones:
                winner_phones.append(phone)
        
        # REMOVED: Automatic/manual counting per game (too expensive - JSON parsing for each card)
        
        # Count real and system users - use prefetched gamecards count and annotated fake count
        real_users_count = game.gamecards.count()
        system_users_count = game.fake_user_count or 0
        
        today_games_data.append({
            'id': game.id,
            'players': game.total_players,
            'bid_amount': float(game.bet_amount),
            'automatic_count': 0,  # Removed expensive calculation
            'manual_count': 0,  # Removed expensive calculation
            'winner_phones': winner_phones,
            'real_users': real_users_count,
            'system_users': system_users_count,
            'status': game.status,
            'created_at': game.created_at.strftime('%H:%M'),
        })
    
    # Registered users - OPTIMIZED: Limited to 20 most recent; wins computed from Game (winner + winners M2M)
    registered_users_raw = User.objects.filter(telegram_id__isnull=False).order_by('-created_at')[:20].annotate(
        games_played=Count('gamecards__game', distinct=True),
        user_total_deposits=Sum('transactions__amount', filter=Q(transactions__transaction_type='deposit')),
        user_total_withdrawals=Sum('transactions__amount', filter=Q(transactions__transaction_type='withdraw'))
    )
    sec_user_ids = [u.id for u in registered_users_raw]
    win_count_by_user_sec = {}
    if sec_user_ids:
        for winner_id, game_id in Game.objects.filter(winner_id__in=sec_user_ids).values_list('winner_id', 'id'):
            if winner_id not in win_count_by_user_sec:
                win_count_by_user_sec[winner_id] = set()
            win_count_by_user_sec[winner_id].add(game_id)
        through = Game.winners.through
        for uid, gid in through.objects.filter(user_id__in=sec_user_ids).values_list('user_id', 'game_id'):
            if uid not in win_count_by_user_sec:
                win_count_by_user_sec[uid] = set()
            win_count_by_user_sec[uid].add(gid)
        win_count_by_user_sec = {uid: len(s) for uid, s in win_count_by_user_sec.items()}
    registered_users = []
    for user in registered_users_raw:
        games_played = user.games_played or 0
        wins = win_count_by_user_sec.get(user.id)
        if wins is None:
            wins = user.total_wins or 0
        user_total_deposits = user.user_total_deposits or Decimal('0')
        user_total_withdrawals = user.user_total_withdrawals or Decimal('0')
        
        registered_users.append({
            'id': user.id,
            'username': user.username,
            'telegram_id': user.telegram_id,
            'phone_number': user.phone_number or '-',
            'name': f"{user.first_name or ''} {user.last_name or ''}".strip() or '-',
            'unwithdrawable_balance': float(user.unwithdrawable_balance or 0),
            'withdrawable_balance': float(user.withdrawable_balance or 0),
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
    
    # Financial statistics - Calculate from ALL registered users (not just the limited display list)
    # Sum deposits and withdrawals from all registered users' transactions
    all_registered_users = User.objects.filter(telegram_id__isnull=False)
    total_deposits = Transaction.objects.filter(
        transaction_type='deposit',
        user__in=all_registered_users
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_withdrawals = Transaction.objects.filter(
        transaction_type='withdraw',
        user__in=all_registered_users
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_balance = User.objects.aggregate(
        total=Sum(F('unwithdrawable_balance') + F('withdrawable_balance'))
    )['total'] or Decimal('0')
    
    # Calculate total automatic and manual games - OPTIMIZED with caching
    from .models import GameCard
    from django.core.cache import cache
    
    # Cache this expensive calculation for 5 minutes
    cache_key = 'admin_total_automatic_manual_games'
    cached_result = cache.get(cache_key)
    
    # PHASE 3 FIX: Validate cached result before unpacking
    if cached_result is not None and isinstance(cached_result, (tuple, list)) and len(cached_result) == 2:
        total_automatic_games, total_manual_games = cached_result
    else:
        # Use only() to limit fields loaded, but regular queryset (no iterator to avoid cursor issues)
        all_cards = GameCard.objects.only('mode_history')
        total_automatic_games = 0
        total_manual_games = 0
        for card in all_cards:
            mode_history = card.mode_history or []
            has_automatic = any(entry.get('mode') == 'automatic' for entry in mode_history if isinstance(entry, dict))
            if has_automatic:
                total_automatic_games += 1
            else:
                total_manual_games += 1
        
        # Cache for 5 minutes (300 seconds)
        cache.set(cache_key, (total_automatic_games, total_manual_games), 300)
    
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