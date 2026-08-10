from django.db import migrations


class Migration(migrations.Migration):
    """Drop admin_tokens once 0003 has copied its rows into auth_tokens."""

    dependencies = [
        ("accounts", "0003_migrate_tokens_to_authtoken"),
    ]

    operations = [
        migrations.DeleteModel(name="AdminToken"),
    ]
