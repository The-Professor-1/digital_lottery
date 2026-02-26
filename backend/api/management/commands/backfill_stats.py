"""
Backfill TotalStats, DailyStats, and User cached totals from current Game/Transaction data.
Run once after adding the aggregate tables and User cache fields, and after migrations.
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum, Count, Q
from decimal import Decimal


class Command(BaseCommand):
    help = 'Backfill TotalStats, DailyStats, and User total_games_played/total_wins/total_deposits_amount/total_withdrawals_amount from current data'

    def handle(self, *args, **options):
        from api.models import (
            Game, GameCard, Transaction, User,
            TotalStats, DailyStats, GameSettings,
        )
        from api.stats_utils import sync_total_balance_from_users

        self.stdout.write('Backfilling aggregate stats and user caches...')

        # 1) TotalStats from current data
        completed = Game.objects.filter(status='completed')
        total_games = completed.count()
        settings = GameSettings.get_settings()
        pct = getattr(settings, 'percentage_cut', Decimal('10')) or Decimal('10')
        total_revenue = Decimal('0')
        for game in completed.annotate(real_count=Count('gamecards', distinct=True)).filter(real_count__gt=0):
            total_revenue += (Decimal(str(game.real_count)) * game.bet_amount * pct) / Decimal('100')
        all_reg = User.objects.filter(telegram_id__isnull=False)
        total_deposits = Transaction.objects.filter(
            transaction_type='deposit', user__in=all_reg
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        total_withdrawals = Transaction.objects.filter(
            transaction_type='withdraw', user__in=all_reg
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0')
        from django.db.models import F
        total_balance = User.objects.aggregate(s=Sum(F('unwithdrawable_balance') + F('withdrawable_balance')))['s'] or Decimal('0')

        t, _ = TotalStats.objects.get_or_create(pk=1, defaults={
            'total_games': 0, 'total_revenue': 0, 'total_deposits': 0,
            'total_withdrawals': 0, 'total_balance': 0,
        })
        t.total_games = total_games
        t.total_revenue = total_revenue
        t.total_deposits = total_deposits
        t.total_withdrawals = total_withdrawals
        t.total_balance = total_balance
        t.save()
        self.stdout.write(self.style.SUCCESS(f'   TotalStats: games={total_games}, revenue={total_revenue}, deposits={total_deposits}, withdrawals={total_withdrawals}, balance={total_balance}'))

        # 2) DailyStats: one row per day from completed games and transactions
        from collections import defaultdict
        day_games = defaultdict(int)
        day_revenue = defaultdict(lambda: Decimal('0'))
        day_deposits = defaultdict(lambda: Decimal('0'))
        day_withdrawals = defaultdict(lambda: Decimal('0'))
        for game in completed.annotate(real_count=Count('gamecards', distinct=True)).filter(real_count__gt=0):
            d = (game.completed_at or game.created_at).date()
            day_games[d] += 1
            day_revenue[d] += (Decimal(str(game.real_count)) * game.bet_amount * pct) / Decimal('100')
        for tx in Transaction.objects.filter(transaction_type='deposit', user__telegram_id__isnull=False).only('amount', 'created_at'):
            day_deposits[tx.created_at.date()] += tx.amount
        for tx in Transaction.objects.filter(transaction_type='withdraw', user__telegram_id__isnull=False).only('amount', 'created_at'):
            day_withdrawals[tx.created_at.date()] += tx.amount
        all_dates = set(day_games) | set(day_deposits) | set(day_withdrawals)
        for d in all_dates:
            DailyStats.objects.update_or_create(
                date=d,
                defaults={
                    'games_count': day_games[d],
                    'revenue': day_revenue[d],
                    'deposits': day_deposits[d],
                    'withdrawals': day_withdrawals[d],
                }
            )
        self.stdout.write(self.style.SUCCESS(f'   DailyStats: {len(all_dates)} days'))

        # 3) User cache: total_games_played, total_wins, total_deposits_amount, total_withdrawals_amount
        for user in User.objects.filter(telegram_id__isnull=False).only('id'):
            gp = Game.objects.filter(gamecards__user=user).distinct().count()
            w = Game.objects.filter(Q(winner=user) | Q(winners=user)).distinct().count()
            dep = Transaction.objects.filter(user=user, transaction_type='deposit').aggregate(s=Sum('amount'))['s'] or Decimal('0')
            wit = Transaction.objects.filter(user=user, transaction_type='withdraw').aggregate(s=Sum('amount'))['s'] or Decimal('0')
            User.objects.filter(id=user.id).update(
                total_games_played=gp,
                total_wins=w,
                total_deposits_amount=dep,
                total_withdrawals_amount=wit,
            )
        self.stdout.write(self.style.SUCCESS(f'   User cache: updated {User.objects.filter(telegram_id__isnull=False).count()} users'))

        sync_total_balance_from_users()
        self.stdout.write(self.style.SUCCESS('Backfill complete. Dashboard and user search will use aggregates and cached user fields.'))
