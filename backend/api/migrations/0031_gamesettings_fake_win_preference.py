# Fake win preference level: 0=current, 1=prefer fake wins, 2=stronger (multi-fake, fallback)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0030_gamesettings_disable_bot_deposit_withdraw'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesettings',
            name='fake_win_preference',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='0=default (current). 1=prefer fake wins when safe. 2=stronger preference (multi-fake, fallback). Only applies when system accounts on and not free play.'
            ),
        ),
    ]
