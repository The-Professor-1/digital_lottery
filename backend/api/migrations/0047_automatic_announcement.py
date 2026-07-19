from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0046_winner_reveal_and_notify'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotterysettings',
            name='automatic_announcement',
            field=models.BooleanField(
                default=True,
                help_text='If True, run in-app shuffle/reveal. If False, show manual announcement message.',
            ),
        ),
    ]
