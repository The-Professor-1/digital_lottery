# User: replace balance with unwithdrawable_balance and withdrawable_balance

from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import migrations, models


def migrate_balance_to_two_fields(apps, schema_editor):
    User = apps.get_model('api', 'User')
    for u in User.objects.all():
        bal = getattr(u, 'balance', None)
        if bal is None:
            bal = Decimal('0')
        else:
            bal = Decimal(str(bal))
        total_dep = getattr(u, 'total_deposits_amount', None)
        if total_dep is not None and (total_dep or Decimal('0')) > 0:
            u.withdrawable_balance = bal
            u.unwithdrawable_balance = Decimal('0')
        else:
            u.unwithdrawable_balance = bal
            u.withdrawable_balance = Decimal('0')
        u.save(update_fields=['unwithdrawable_balance', 'withdrawable_balance'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0025_gamesettings_disable_bot_start_disable_bot_register'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='unwithdrawable_balance',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Balance for gameplay only (bonus, registration reward, wins before deposit)', max_digits=10, validators=[MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name='user',
            name='withdrawable_balance',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Balance that can be withdrawn (deposits + wins after deposit >= min)', max_digits=10, validators=[MinValueValidator(0)]),
        ),
        migrations.RunPython(migrate_balance_to_two_fields, noop_reverse),
        migrations.RemoveField(
            model_name='user',
            name='balance',
        ),
    ]
