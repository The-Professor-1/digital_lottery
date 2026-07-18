from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0045_next_round_timer'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotterysettings',
            name='winner_reveal_seconds',
            field=models.PositiveIntegerField(
                default=6,
                help_text='Seconds to show each place (1st/2nd/3rd) during live announce',
            ),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='winners_notified',
            field=models.BooleanField(
                default=False,
                help_text='True after Telegram winner DMs have been sent (after live announce)',
            ),
        ),
    ]
