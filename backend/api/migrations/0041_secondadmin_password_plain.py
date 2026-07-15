from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0040_lottery_purchases_and_blocked_numbers'),
    ]

    operations = [
        migrations.AddField(
            model_name='secondadmin',
            name='password_plain',
            field=models.CharField(blank=True, default='', max_length=128),
        ),
    ]
