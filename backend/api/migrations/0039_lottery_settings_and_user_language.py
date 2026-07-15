from django.db import migrations, models
import api.models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0038_bet_split_and_card_unselect_refund'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='preferred_language',
            field=models.CharField(
                blank=True,
                default='am',
                help_text='User preferred language: am, en, om',
                max_length=5,
            ),
        ),
        migrations.CreateModel(
            name='LotterySettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('brand_name', models.CharField(default='Getachew Fikadu', max_length=120)),
                ('car_name', models.CharField(default='BYD Yuan UP', max_length=120)),
                ('car_color', models.CharField(default='Time Grey', max_length=80)),
                ('car_image', models.ImageField(blank=True, null=True, upload_to='lottery/cars/')),
                ('car_image_url', models.URLField(
                    blank=True,
                    default='https://images.unsplash.com/photo-1619767886558-efdc259cde1a?auto=format&fit=crop&w=900&q=80',
                    help_text='Used when no uploaded image is set',
                )),
                ('display_name', models.CharField(
                    default='Gech EV Makina Ekub',
                    help_text='Name shown on checkout / tickets',
                    max_length=160,
                )),
                ('ticket_price', models.PositiveIntegerField(default=3000)),
                ('total_tickets', models.PositiveIntegerField(default=3500)),
                ('sold_count', models.PositiveIntegerField(default=397)),
                ('countdown_days', models.PositiveIntegerField(default=12)),
                ('countdown_hours', models.PositiveIntegerField(default=10)),
                ('countdown_minutes', models.PositiveIntegerField(default=24)),
                ('countdown_seconds', models.PositiveIntegerField(default=45)),
                ('ends_at', models.DateTimeField(blank=True, null=True)),
                ('payment_accounts', models.JSONField(default=api.models.default_payment_accounts)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Lottery Settings',
                'verbose_name_plural': 'Lottery Settings',
                'db_table': 'lottery_settings',
            },
        ),
    ]
