from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0042_deleted_lottery_receipts_users'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotterysettings',
            name='hero_title',
            field=models.CharField(
                default='markos digital lottery',
                help_text='Text shown at top of homepage prize section',
                max_length=160,
            ),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='prize_1st',
            field=models.PositiveIntegerField(default=100000, help_text='1st prize amount in Birr'),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='prize_2nd',
            field=models.PositiveIntegerField(default=50000, help_text='2nd prize amount in Birr'),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='prize_3rd',
            field=models.PositiveIntegerField(default=25000, help_text='3rd prize amount in Birr'),
        ),
        migrations.AddField(
            model_name='lotterysettings',
            name='verify_api_key',
            field=models.CharField(
                blank=True,
                default='',
                help_text='API key for Telebirr/CBE receipt verification (verifyapi.leulzenebe.pro)',
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name='lotterysettings',
            name='brand_name',
            field=models.CharField(default='Markos Digital Lottery', max_length=120),
        ),
        migrations.AlterField(
            model_name='lotterysettings',
            name='car_name',
            field=models.CharField(
                default='Cash Prize',
                help_text='Legacy field; prefer hero_title',
                max_length=120,
            ),
        ),
        migrations.AlterField(
            model_name='lotterysettings',
            name='car_color',
            field=models.CharField(blank=True, default='', max_length=80),
        ),
        migrations.AlterField(
            model_name='lotterysettings',
            name='car_image_url',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Legacy image URL (homepage now uses prize text)',
                max_length=500,
            ),
        ),
        migrations.AlterField(
            model_name='lotterysettings',
            name='display_name',
            field=models.CharField(
                default='Markos Digital Lottery',
                help_text='Name shown on checkout / tickets',
                max_length=160,
            ),
        ),
        migrations.AddField(
            model_name='lotterypurchase',
            name='receipt_sms',
            field=models.TextField(blank=True, default='', help_text='Full SMS text pasted by user'),
        ),
        migrations.AddField(
            model_name='lotterypurchase',
            name='payment_provider',
            field=models.CharField(
                blank=True,
                default='',
                help_text='telebirr or cbe',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='lotterypurchase',
            name='transaction_ref',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text='Parsed transaction / receipt reference for dedup',
                max_length=64,
            ),
        ),
        migrations.AlterField(
            model_name='lotterypurchase',
            name='receipt_image',
            field=models.ImageField(blank=True, null=True, upload_to='lottery/receipts/'),
        ),
    ]
