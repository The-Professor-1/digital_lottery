from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Transaction, LotteryPurchase


@receiver(post_save, sender=Transaction)
def on_transaction_save(sender, instance, created, **kwargs):
    """When a deposit is recorded, update user's withdrawal_approved if they now qualify."""
    if created and instance.transaction_type == 'deposit' and instance.user_id:
        from .user_utils import update_user_withdrawal_approval
        update_user_withdrawal_approval(instance.user)


@receiver(post_save, sender=LotteryPurchase)
def on_lottery_purchase_save(sender, instance, created, raw=False, **kwargs):
    """Browser-notify subscribed admins when a new pending receipt arrives."""
    if not created or raw or instance.status != 'pending':
        return
    try:
        from .push_notify import notify_admins_new_pending
        notify_admins_new_pending(instance)
    except Exception:
        pass
