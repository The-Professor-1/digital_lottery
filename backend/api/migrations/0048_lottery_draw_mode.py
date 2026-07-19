from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0047_automatic_announcement'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotterysettings',
            name='draw_mode',
            field=models.CharField(
                choices=[
                    ('date', 'Date deadline'),
                    ('sold_out', 'When all tickets sold'),
                    ('manual', 'Admin starts draw'),
                ],
                default='date',
                help_text='How the draw is triggered: date countdown, sold out, or admin start',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='draw_timer_seconds',
            field=models.PositiveIntegerField(
                default=60,
                help_text='Default pre-draw countdown seconds when admin clicks Start Draw',
            ),
        ),
    ]
