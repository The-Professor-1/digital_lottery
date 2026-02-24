# Instruction text for /instruction command (editable from admin dashboard)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_gamesettings_daily_new_start_limit'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesettings',
            name='instruction_text',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Text shown when user sends /instruction in the bot. Leave empty to use default text from bot.'
            ),
        ),
    ]
