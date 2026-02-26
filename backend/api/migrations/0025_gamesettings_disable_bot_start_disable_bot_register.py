# GameSettings: disable /start and /register bot menus

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0024_telebirrreceipt_block_only'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesettings',
            name='disable_bot_start',
            field=models.BooleanField(default=False, help_text='When enabled, the Telegram bot will not respond to /start (no welcome, no menu).'),
        ),
        migrations.AddField(
            model_name='gamesettings',
            name='disable_bot_register',
            field=models.BooleanField(default=False, help_text='When enabled, the bot will not respond to /register or contact share (no new registrations).'),
        ),
    ]
