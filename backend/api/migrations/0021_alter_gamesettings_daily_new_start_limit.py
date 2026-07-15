# Placeholder: historical AlterField for daily_new_start_limit (file was missing from repo).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_gamesettings_daily_new_start_limit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gamesettings',
            name='daily_new_start_limit',
            field=models.PositiveIntegerField(
                default=100,
                help_text='Max new /start (new user) registrations per day. Set to 0 for no limit. Set to 1 to test (only one new user per day).',
            ),
        ),
    ]
