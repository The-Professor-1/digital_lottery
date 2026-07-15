# Creates FailedDepositRequest (was referenced by merge 0018 but file was missing from repo).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_user_withdrawal_approved'),
    ]

    operations = [
        migrations.CreateModel(
            name='FailedDepositRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('platform', models.CharField(max_length=20)),
                ('deposit_text', models.TextField(blank=True)),
                ('failure_reason', models.CharField(blank=True, max_length=255)),
                ('reference', models.CharField(blank=True, db_index=True, max_length=64)),
                ('account_suffix', models.CharField(blank=True, db_index=True, max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='failed_deposit_requests',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'failed_deposit_requests',
                'ordering': ['-created_at'],
            },
        ),
    ]
