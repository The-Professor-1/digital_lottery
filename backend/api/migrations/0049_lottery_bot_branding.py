from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0048_lottery_draw_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotterysettings',
            name='bot_description',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Telegram bot profile description (shown before /start)',
            ),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='bot_short_description',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Telegram bot short description / About line',
                max_length=120,
            ),
        ),
        migrations.AlterField(
            model_name='lotterysettings',
            name='brand_name',
            field=models.CharField(
                default='Digital Lottery',
                help_text='Brand shown in app header, footer, and bot open-app button',
                max_length=120,
            ),
        ),
        migrations.AlterField(
            model_name='lotterysettings',
            name='display_name',
            field=models.CharField(
                default='Digital Lottery',
                help_text='Name shown instead of countdown (sold-out/manual modes), checkout, tickets',
                max_length=160,
            ),
        ),
        migrations.AlterField(
            model_name='lotterysettings',
            name='hero_title',
            field=models.CharField(
                default='Digital Lottery',
                help_text='Text shown at top of homepage prize section',
                max_length=160,
            ),
        ),
    ]
