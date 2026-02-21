from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Transaction


@receiver(post_save, sender=Transaction)
def on_transaction_save(sender, instance, created, **kwargs):
    """When a deposit is recorded, update user's withdrawal_approved if they now qualify."""
    if created and instance.transaction_type == 'deposit' and instance.user_id:
        from .user_utils import update_user_withdrawal_approval
        update_user_withdrawal_approval(instance.user)
