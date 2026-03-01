# Game.fake_win_preference_snapshot + TotalStats win stats (real/fake by level 0,1,2)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0031_gamesettings_fake_win_preference'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='fake_win_preference_snapshot',
            field=models.PositiveSmallIntegerField(blank=True, default=0, help_text='Fake win preference level at game start (0/1/2) for win stats.', null=True),
        ),
        migrations.AddField(
            model_name='totalstats',
            name='total_real_wins',
            field=models.PositiveIntegerField(default=0, help_text='Games won by real users'),
        ),
        migrations.AddField(
            model_name='totalstats',
            name='total_fake_wins',
            field=models.PositiveIntegerField(default=0, help_text='Games won by system/fake users'),
        ),
        migrations.AddField(
            model_name='totalstats',
            name='real_wins_level_0',
            field=models.PositiveIntegerField(default=0, help_text='Real wins when fake_win_preference=0'),
        ),
        migrations.AddField(
            model_name='totalstats',
            name='real_wins_level_1',
            field=models.PositiveIntegerField(default=0, help_text='Real wins when fake_win_preference=1'),
        ),
        migrations.AddField(
            model_name='totalstats',
            name='real_wins_level_2',
            field=models.PositiveIntegerField(default=0, help_text='Real wins when fake_win_preference=2'),
        ),
        migrations.AddField(
            model_name='totalstats',
            name='fake_wins_level_0',
            field=models.PositiveIntegerField(default=0, help_text='Fake wins when fake_win_preference=0'),
        ),
        migrations.AddField(
            model_name='totalstats',
            name='fake_wins_level_1',
            field=models.PositiveIntegerField(default=0, help_text='Fake wins when fake_win_preference=1'),
        ),
        migrations.AddField(
            model_name='totalstats',
            name='fake_wins_level_2',
            field=models.PositiveIntegerField(default=0, help_text='Fake wins when fake_win_preference=2'),
        ),
    ]
