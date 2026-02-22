# Merge migration: resolve conflict between 0017_aggregate_stats_and_user_cache
# and 0017_faileddepositrequest_and_more (from remote).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_aggregate_stats_and_user_cache'),
        ('api', '0017_faileddepositrequest_and_more'),
    ]

    operations = []
