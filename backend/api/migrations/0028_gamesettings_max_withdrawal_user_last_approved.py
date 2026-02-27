# Max withdrawal (per 24h from approval) and user last withdrawal approval time

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0027_gamesettings_disable_bot_transfer'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesettings',
            name='max_withdrawal',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Max withdrawal per 24h (from approval time). Null/0 = no limit.', max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='last_withdrawal_approved_at',
            field=models.DateTimeField(blank=True, help_text="When the user's last withdrawal was approved; 24h cooldown for next request starts here", null=True),
        ),
    ]
