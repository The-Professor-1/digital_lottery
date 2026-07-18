from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0043_money_lottery_sms_verify'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotterysettings',
            name='winner_1st',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='winner_2nd',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='winner_3rd',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='draw_completed',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='LotteryFailedDeposit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(blank=True, default='', max_length=160)),
                ('phone', models.CharField(blank=True, db_index=True, default='', max_length=32)),
                ('numbers', models.JSONField(blank=True, default=list)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('expected_amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('credited_amount', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('payment_provider', models.CharField(blank=True, default='', max_length=20)),
                ('bank_name', models.CharField(blank=True, default='', max_length=120)),
                ('bank_holder', models.CharField(blank=True, default='', max_length=160)),
                ('bank_account', models.CharField(blank=True, default='', max_length=64)),
                ('transaction_ref', models.CharField(blank=True, db_index=True, default='', max_length=64)),
                ('account_suffix', models.CharField(blank=True, default='', max_length=16)),
                ('receipt_sms', models.TextField(blank=True, default='')),
                ('failure_reason', models.CharField(blank=True, default='', max_length=255)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=20)),
                ('admin_txn_no', models.CharField(blank=True, default='', help_text='Txn number confirmed by admin on approve (blocks reuse)', max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lottery_failed_resolutions', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lottery_failed_deposits', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'lottery_failed_deposits',
                'ordering': ['-created_at'],
            },
        ),
    ]
