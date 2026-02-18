# Migration to set system_accounts_max default to 100 (supports up to 100 fake players)

from django.db import migrations, models


def set_max_to_100(apps, schema_editor):
    """Update existing GameSettings to allow up to 100 fake players"""
    GameSettings = apps.get_model('api', 'GameSettings')
    for settings in GameSettings.objects.all():
        if settings.system_accounts_max < 100:
            settings.system_accounts_max = 100
            settings.save()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_add_user_indexes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gamesettings',
            name='system_accounts_max',
            field=models.IntegerField(default=100, help_text='Maximum number of system accounts to join each game'),
        ),
        migrations.RunPython(set_max_to_100, migrations.RunPython.noop),
    ]
