"""
Helpers for user approval (withdrawal): user must have deposited >= 50 BR and played >= 5 games.
"""
from decimal import Decimal
from django.db.models import Sum, Q, Count


def update_user_withdrawal_approval(user):
    """
    Set user.withdrawal_approved = True if total deposit >= 50 and games_played >= 5.
    Call after deposit transactions or when a game completes (for each player).
    """
    from .models import User, Transaction, GameCard
    if not user or getattr(user, 'id', None) is None:
        return
    total_deposit = (
        Transaction.objects.filter(user=user, transaction_type='deposit')
        .aggregate(s=Sum('amount'))['s'] or Decimal('0')
    )
    games_played = GameCard.objects.filter(user=user).values('game').distinct().count()
    new_approved = (total_deposit >= Decimal('50') and games_played >= 5)
    if user.withdrawal_approved != new_approved:
        User.objects.filter(pk=user.pk).update(withdrawal_approved=new_approved)
