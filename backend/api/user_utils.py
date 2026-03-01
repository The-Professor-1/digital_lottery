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
    from .models import User, Transaction
    if not user or getattr(user, 'id', None) is None:
        return
    total_deposit = (
        Transaction.objects.filter(user=user, transaction_type='deposit')
        .aggregate(s=Sum('amount'))['s'] or Decimal('0')
    )
    # Use cached total_games_played (survives prune)
    games_played = getattr(user, 'total_games_played', None) or 0
    new_approved = (total_deposit >= Decimal('50') and games_played >= 5)
    if user.withdrawal_approved != new_approved:
        User.objects.filter(pk=user.pk).update(withdrawal_approved=new_approved)
