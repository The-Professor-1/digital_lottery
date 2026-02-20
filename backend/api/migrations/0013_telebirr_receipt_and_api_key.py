# Telebirr auto-verify: API key on GameSettings + TelebirrReceipt model

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_gamesettings_system_accounts_max_100'),
    ]

    operations = [
        migrations.AddField(
            model_name='gamesettings',
            name='telebirr_verify_api_key',
            field=models.CharField(blank=True, default='', help_text='API key for verifyapi.leulzenebe.pro to verify Telebirr receipts', max_length=255),
        ),
        migrations.CreateModel(
            name='TelebirrReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(db_index=True, max_length=64, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10, validators=[MinValueValidator(0.01)])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='telebirr_receipts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'telebirr_receipts',
                'ordering': ['-created_at'],
            },
        ),
    ]
