# Placeholder for a branch that never landed in this repo.
# Kept so merge 0014 stays valid on fresh databases.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_gamesettings_system_accounts_max_100'),
    ]

    operations = []
