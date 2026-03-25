"""
Update TotalStats, DailyStats, and User cached totals when games complete or deposits/withdrawals happen.
Use these so the dashboard and user search still show correct totals after pruning old records.
"""
from decimal import Decimal
from django.utils import timezone
from django.db.models import F


def _total_stats():
    from .models import TotalStats
    return TotalStats.get_singleton()


def _daily_for_date(d):
    from .models import DailyStats
    return DailyStats.get_or_create_for_date(d)


def record_game_completed(game, revenue_amount, winner_type=None):
    """Call when a game is completed. revenue_amount = (real_players * bet_amount) * percentage_cut / 100.
    winner_type: 'real' | 'fake' | None (auto-detect from game.winner/winners vs FakeUserGameCard is_winner).
    Records total_real_wins / total_fake_wins and per-level (0,1,2) stats in TotalStats."""
    if revenue_amount is None:
        revenue_amount = Decimal('0')
    d = timezone.now().date()
    # TotalStats
    t = _total_stats()
    t.total_games = (t.total_games or 0) + 1
    t.total_revenue = (t.total_revenue or Decimal('0')) + Decimal(str(revenue_amount))
    # Win stats: detect real vs fake if not provided
    if winner_type is None:
        has_real = bool(game.winner_id) or game.winners.exists()
        from .models import FakeUserGameCard
        has_fake = FakeUserGameCard.objects.filter(game=game, is_winner=True).exists()
        winner_type = 'real' if has_real else ('fake' if has_fake else 'fake')  # Redis-only winner = fake
    level = getattr(game, 'fake_win_preference_snapshot', None)
    level = 0 if level is None else max(0, min(2, int(level)))
    if winner_type == 'real':
        t.total_real_wins = (t.total_real_wins or 0) + 1
        if level == 0:
            t.real_wins_level_0 = (t.real_wins_level_0 or 0) + 1
        elif level == 1:
            t.real_wins_level_1 = (t.real_wins_level_1 or 0) + 1
        else:
            t.real_wins_level_2 = (t.real_wins_level_2 or 0) + 1
    else:
        t.total_fake_wins = (t.total_fake_wins or 0) + 1
        if level == 0:
            t.fake_wins_level_0 = (t.fake_wins_level_0 or 0) + 1
        elif level == 1:
            t.fake_wins_level_1 = (t.fake_wins_level_1 or 0) + 1
        else:
            t.fake_wins_level_2 = (t.fake_wins_level_2 or 0) + 1
    update_fields = ['total_games', 'total_revenue', 'total_real_wins', 'total_fake_wins',
                     'real_wins_level_0', 'real_wins_level_1', 'real_wins_level_2',
                     'fake_wins_level_0', 'fake_wins_level_1', 'fake_wins_level_2', 'updated_at']
    t.save(update_fields=update_fields)
    # DailyStats
    daily = _daily_for_date(d)
    daily.games_count = (daily.games_count or 0) + 1
    daily.revenue = (daily.revenue or Decimal('0')) + Decimal(str(revenue_amount))
    daily.save(update_fields=['games_count', 'revenue', 'updated_at'])
    # User stats: games_played for every user who had a card; total_wins for winners
    from .models import GameCard, User
    user_ids_played = set(GameCard.objects.filter(game=game).values_list('user_id', flat=True))
    # Capture pre-increment state for first-win detection
    pre_users = {}
    if user_ids_played:
        for u in User.objects.filter(id__in=user_ids_played).only('id', 'total_games_played', 'total_wins', 'first_win', 'free_play_allowed'):
            pre_users[u.id] = {
                'games': int(getattr(u, 'total_games_played', 0) or 0),
                'wins': int(getattr(u, 'total_wins', 0) or 0),
            }
    if user_ids_played:
        User.objects.filter(id__in=user_ids_played).update(total_games_played=F('total_games_played') + 1)
    winner_ids = set()
    if game.winner_id:
        winner_ids.add(game.winner_id)
    for u in game.winners.all():
        winner_ids.add(u.id)
    if winner_ids:
        User.objects.filter(id__in=winner_ids).update(total_wins=F('total_wins') + 1)
        # Anti-abuse transition: user won on first played game => first_win=True and free_play_allowed=False
        first_win_user_ids = []
        for uid in winner_ids:
            st = pre_users.get(uid)
            if st and st['games'] == 0 and st['wins'] == 0:
                first_win_user_ids.append(uid)
        if first_win_user_ids:
            User.objects.filter(id__in=first_win_user_ids).update(first_win=True, free_play_allowed=False)


def record_deposit(amount, user, at_date=None):
    """Call when a deposit is credited (Transaction created). Updates User.total_deposits_amount
    so has_withdrawable_active() is correct and future wins go to withdrawable_balance when appropriate."""
    if at_date is None:
        at_date = timezone.now().date()
    amount = Decimal(str(amount))
    t = _total_stats()
    t.total_deposits = (t.total_deposits or Decimal('0')) + amount
    t.total_balance = (t.total_balance or Decimal('0')) + amount
    t.save(update_fields=['total_deposits', 'total_balance', 'updated_at'])
    daily = _daily_for_date(at_date)
    daily.deposits = (daily.deposits or Decimal('0')) + amount
    daily.save(update_fields=['deposits', 'updated_at'])
    if user_id := getattr(user, 'id', None):
        from .models import User
        User.objects.filter(id=user_id).update(total_deposits_amount=F('total_deposits_amount') + amount)
        # Anti-abuse trust transition:
        # deposit #1 => free_play_allowed=False, deposit #2+ => free_play_allowed=True
        u = User.objects.filter(id=user_id).only('id', 'number_of_deposits').first()
        if u:
            next_count = int(getattr(u, 'number_of_deposits', 0) or 0) + 1
            allow = next_count >= 2
            User.objects.filter(id=user_id).update(number_of_deposits=next_count, free_play_allowed=allow)


def credit_deposit(amount, user, at_date=None):
    """Credit a deposit: add amount to withdrawable_balance, add deposit_bonus_percent of amount to unwithdrawable_balance, then record_deposit."""
    from .models import User, GameSettings
    amount = Decimal(str(amount))
    user_id = getattr(user, 'id', None)
    if not user_id:
        return
    settings = GameSettings.get_settings()
    percent = getattr(settings, 'deposit_bonus_percent', 0) or 0
    bonus = (amount * Decimal(percent)) / Decimal(100) if percent else Decimal('0')
    User.objects.filter(id=user_id).update(withdrawable_balance=F('withdrawable_balance') + amount)
    if bonus > 0:
        User.objects.filter(id=user_id).update(unwithdrawable_balance=F('unwithdrawable_balance') + bonus)
    record_deposit(amount, user, at_date)


def record_withdrawal(amount, user, at_date=None):
    """Call when a withdrawal is processed (Transaction created)."""
    if at_date is None:
        at_date = timezone.now().date()
    amount = Decimal(str(amount))
    t = _total_stats()
    t.total_withdrawals = (t.total_withdrawals or Decimal('0')) + amount
    t.total_balance = (t.total_balance or Decimal('0')) - amount
    t.save(update_fields=['total_withdrawals', 'total_balance', 'updated_at'])
    daily = _daily_for_date(at_date)
    daily.withdrawals = (daily.withdrawals or Decimal('0')) + amount
    daily.save(update_fields=['withdrawals', 'updated_at'])
    if user_id := getattr(user, 'id', None):
        from .models import User
        User.objects.filter(id=user_id).update(total_withdrawals_amount=F('total_withdrawals_amount') + amount)


def sync_total_balance_from_users():
    """Recalc total_balance from User unwithdrawable_balance + withdrawable_balance."""
    from .models import User
    from django.db.models import Sum, F
    total = User.objects.aggregate(s=Sum(F('unwithdrawable_balance') + F('withdrawable_balance')))['s'] or Decimal('0')
    t = _total_stats()
    t.total_balance = total
    t.save(update_fields=['total_balance', 'updated_at'])


def get_dashboard_aggregates(periods):
    """
    Return dict of dashboard numbers from TotalStats and DailyStats.
    periods: from get_calendar_periods(now). Keys: today_start, yesterday_start, week_start, etc.
    Returns None if aggregate tables are not populated (caller can fall back to live queries).
    """
    from .models import TotalStats, DailyStats
    from django.db.models import Sum
    try:
        t = TotalStats.get_singleton()
    except Exception:
        return None
    today = periods['today_start'].date() if hasattr(periods['today_start'], 'date') else periods['today_start']
    yesterday = periods['yesterday_start'].date() if hasattr(periods['yesterday_start'], 'date') else periods['yesterday_start']
    try:
        daily_today = DailyStats.objects.filter(date=today).first()
        daily_yesterday = DailyStats.objects.filter(date=yesterday).first()
        week_days = DailyStats.objects.filter(
            date__gte=periods['week_start'],
            date__lte=periods['week_end']
        ).aggregate(g=Sum('games_count'), r=Sum('revenue'), d=Sum('deposits'), w=Sum('withdrawals'))
        last_week_days = DailyStats.objects.filter(
            date__gte=periods['last_week_start'],
            date__lte=periods['last_week_end']
        ).aggregate(g=Sum('games_count'), r=Sum('revenue'), d=Sum('deposits'), w=Sum('withdrawals'))
        month_days = DailyStats.objects.filter(
            date__gte=periods['month_start'],
            date__lte=periods['month_end']
        ).aggregate(g=Sum('games_count'), r=Sum('revenue'), d=Sum('deposits'), w=Sum('withdrawals'))
        last_month_days = DailyStats.objects.filter(
            date__gte=periods['last_month_start'],
            date__lte=periods['last_month_end']
        ).aggregate(g=Sum('games_count'), r=Sum('revenue'), d=Sum('deposits'), w=Sum('withdrawals'))
    except Exception:
        return None
    return {
        'games_today': (daily_today.games_count or 0) if daily_today else 0,
        'games_yesterday': (daily_yesterday.games_count or 0) if daily_yesterday else 0,
        'games_week': week_days.get('g') or 0,
        'games_last_week': last_week_days.get('g') or 0,
        'games_month': month_days.get('g') or 0,
        'games_last_month': last_month_days.get('g') or 0,
        'games_total': t.total_games or 0,
        'revenue_today': (daily_today.revenue or Decimal('0')) if daily_today else Decimal('0'),
        'revenue_yesterday': (daily_yesterday.revenue or Decimal('0')) if daily_yesterday else Decimal('0'),
        'revenue_week': week_days.get('r') or Decimal('0'),
        'revenue_last_week': last_week_days.get('r') or Decimal('0'),
        'revenue_month': month_days.get('r') or Decimal('0'),
        'revenue_last_month': last_month_days.get('r') or Decimal('0'),
        'revenue_total': t.total_revenue or Decimal('0'),
        'total_deposits': t.total_deposits or Decimal('0'),
        'total_withdrawals': t.total_withdrawals or Decimal('0'),
        'total_balance': t.total_balance or Decimal('0'),
    }
