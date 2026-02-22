# Aggregate stats (TotalStats, DailyStats) and User cached totals.
# Run backfill_stats after applying this migration.

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_user_withdrawal_approved'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='total_games_played',
            field=models.PositiveIntegerField(default=0, help_text='Total games user has played (survives prune)'),
        ),
        migrations.AddField(
            model_name='user',
            name='total_wins',
            field=models.PositiveIntegerField(default=0, help_text='Total games user has won (survives prune)'),
        ),
        migrations.AddField(
            model_name='user',
            name='total_deposits_amount',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Sum of all deposits (survives prune)', max_digits=12, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name='user',
            name='total_withdrawals_amount',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Sum of all withdrawals (survives prune)', max_digits=12, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.CreateModel(
            name='TotalStats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_games', models.PositiveIntegerField(default=0)),
                ('total_revenue', models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(0)])),
                ('total_deposits', models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(0)])),
                ('total_withdrawals', models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(0)])),
                ('total_balance', models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True, default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'total_stats',
                'verbose_name_plural': 'Total stats',
            },
        ),
        migrations.CreateModel(
            name='DailyStats',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(db_index=True, unique=True)),
                ('games_count', models.PositiveIntegerField(default=0)),
                ('revenue', models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(0)])),
                ('deposits', models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(0)])),
                ('withdrawals', models.DecimalField(decimal_places=2, default=0, max_digits=14, validators=[django.core.validators.MinValueValidator(0)])),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'daily_stats',
                'ordering': ['-date'],
                'verbose_name_plural': 'Daily stats',
            },
        ),
    ]
