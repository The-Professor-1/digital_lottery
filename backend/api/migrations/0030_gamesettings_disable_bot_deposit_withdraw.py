# Disable /deposit and /withdraw in bot via game settings

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0029_gamesettings_register_reward_and_deposit_bonus'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesettings',
            name='disable_bot_deposit',
            field=models.BooleanField(default=False, help_text='When enabled, the bot will not process deposit (button or /deposit).'),
        ),
        migrations.AddField(
            model_name='gamesettings',
            name='disable_bot_withdraw',
            field=models.BooleanField(default=False, help_text='When enabled, the bot will not process withdraw (button or /withdraw).'),
        ),
    ]
