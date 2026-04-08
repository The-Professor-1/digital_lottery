# Generated manually for free-play policy fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0036_game_spectator_count_avoid_list_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesettings',
            name='default_free_play_for_new_users',
            field=models.BooleanField(
                default=True,
                help_text='If True, first-time phone registration sets user free_play_allowed=True. If False, sets free_play_allowed=False.',
            ),
        ),
        migrations.AddField(
            model_name='gamesettings',
            name='allow_free_play_after_real_win',
            field=models.BooleanField(
                default=True,
                help_text='If True, real wins do not change free_play_allowed (first_win flag still updated). If False, every real win sets free_play_allowed=False.',
            ),
        ),
    ]
