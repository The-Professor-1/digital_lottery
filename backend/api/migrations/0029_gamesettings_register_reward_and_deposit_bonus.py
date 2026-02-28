# Give register reward checkbox and deposit bonus percent

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0028_gamesettings_max_withdrawal_user_last_approved'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesettings',
            name='give_register_reward',
            field=models.BooleanField(default=True, help_text='If True, new users get bid_amount as registration bonus (unwithdrawable). If False, no bonus, balance stays 0.'),
        ),
        migrations.AddField(
            model_name='gamesettings',
            name='deposit_bonus_percent',
            field=models.PositiveSmallIntegerField(default=0, help_text='Percent of deposit to add to unwithdrawable (e.g. 10 = 10% of deposit also added as bonus). 0 = no bonus.'),
        ),
    ]
