# User.withdrawal_approved: True when deposit >= 50 BR and games_played >= 5 (allows withdrawal)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_cbereceipt'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='withdrawal_approved',
            field=models.BooleanField(default=False, help_text='True when user has deposited at least 50 BR and played at least 5 games (allows withdrawal)'),
        ),
    ]
