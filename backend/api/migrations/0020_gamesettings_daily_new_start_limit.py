# Bot: max new /start (new user) registrations per day; configurable in admin

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_gamesettings_cbe_use_fallback_proxy'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesettings',
            name='daily_new_start_limit',
            field=models.PositiveIntegerField(
                default=100,
                help_text='Max new /start (new user) registrations per day. Set to 0 for no limit. Set to 1 to test.'
            ),
        ),
    ]
