# Generated manually for bet split tracking and unselect idempotency

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0037_gamesettings_free_play_policy'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='bet_from_unwithdrawable',
            field=models.DecimalField(
                blank=True, decimal_places=2, help_text='Portion of this bet deducted from unwithdrawable_balance',
                max_digits=10, null=True,
            ),
        ),
        migrations.AddField(
            model_name='transaction',
            name='bet_from_withdrawable',
            field=models.DecimalField(
                blank=True, decimal_places=2, help_text='Portion of this bet deducted from withdrawable_balance',
                max_digits=10, null=True,
            ),
        ),
        migrations.CreateModel(
            name='CardUnselectRefund',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('card_number', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('game', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='card_unselect_refunds', to='api.game')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='card_unselect_refunds', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'card_unselect_refunds',
            },
        ),
        migrations.AddConstraint(
            model_name='cardunselectrefund',
            constraint=models.UniqueConstraint(fields=('user', 'game'), name='uniq_card_unselect_refund_user_game'),
        ),
        migrations.AddIndex(
            model_name='cardunselectrefund',
            index=models.Index(fields=['user', 'game'], name='card_unselect_refunds_user_game_idx'),
        ),
    ]
