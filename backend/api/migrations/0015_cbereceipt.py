# CBE auto-verify: CbeReceipt model

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_merge_telebirr_and_gamesettings'),
    ]

    operations = [
        migrations.CreateModel(
            name='CbeReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(db_index=True, max_length=64)),
                ('account_suffix', models.CharField(db_index=True, max_length=16)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10, validators=[MinValueValidator(0.01)])),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cbe_receipts', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'cbe_receipts',
                'ordering': ['-created_at'],
                'unique_together': {('reference', 'account_suffix')},
            },
        ),
    ]
