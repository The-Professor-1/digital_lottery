from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0044_failed_deposits_and_draw_winners'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotterysettings',
            name='next_round_minutes',
            field=models.PositiveIntegerField(
                default=10,
                help_text='Minutes to wait after draw before starting a new round (clears tickets)',
            ),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='next_round_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When the next round auto-starts after a draw',
                null=True,
            ),
        ),
    ]
