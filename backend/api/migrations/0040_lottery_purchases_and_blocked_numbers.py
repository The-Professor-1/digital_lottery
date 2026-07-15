from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0039_lottery_settings_and_user_language'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lotterysettings',
            name='car_image_url',
            field=models.CharField(
                blank=True,
                default='https://images.unsplash.com/photo-1619767886558-efdc259cde1a?auto=format&fit=crop&w=900&q=80',
                help_text='Used when no uploaded image is set',
                max_length=500,
            ),
        ),
        migrations.AlterField(
            model_name='lotterysettings',
            name='sold_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='admin_blocked_numbers',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='winner_number',
            field=models.CharField(blank=True, default='', max_length=16),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='winner_message',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='winner_announced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='LotteryPurchase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=160)),
                ('phone', models.CharField(db_index=True, max_length=32)),
                ('numbers', models.JSONField(default=list, help_text='Selected lottery numbers as ints')),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('amount', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('bank_name', models.CharField(blank=True, default='', max_length=120)),
                ('bank_holder', models.CharField(blank=True, default='', max_length=160)),
                ('bank_account', models.CharField(blank=True, default='', max_length=64)),
                ('paid_from_account', models.CharField(blank=True, default='', max_length=64)),
                ('receipt_image', models.ImageField(upload_to='lottery/receipts/')),
                ('receipt_hash', models.CharField(db_index=True, max_length=64, unique=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('verified', 'Verified'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=20)),
                ('admin_note', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lottery_purchases', to=settings.AUTH_USER_MODEL)),
                ('verified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lottery_verifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'lottery_purchases',
                'ordering': ['-created_at'],
            },
        ),
    ]
