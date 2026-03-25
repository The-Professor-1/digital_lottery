from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0034_gamesettings_test_co_win_next_game'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesettings',
            name='anti_abuse_filter_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Enable anti-abuse filtering for users with free_play_allowed=False (avoid-list delayed numbers).',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='first_win',
            field=models.BooleanField(default=False, help_text='True if user won on their first played game.'),
        ),
        migrations.AddField(
            model_name='user',
            name='free_play_allowed',
            field=models.BooleanField(default=True, help_text='True=fair play. False=restricted call-order filtering for anti-abuse.'),
        ),
        migrations.AddField(
            model_name='user',
            name='number_of_deposits',
            field=models.PositiveIntegerField(default=0, help_text='Approved deposit count used for anti-abuse trust transitions.'),
        ),
    ]
