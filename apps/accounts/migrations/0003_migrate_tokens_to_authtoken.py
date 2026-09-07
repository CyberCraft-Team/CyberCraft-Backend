"""Copy the three legacy token tables into auth_tokens.

Tokens are ephemeral, so losing them would only force a re-login. Copying
them anyway keeps existing launcher and website sessions alive across the
upgrade, which matters while the project is still being tested by hand.

Raw SQL rather than historical models: launcher_tokens and ws_tokens belong
to another app, and reaching across apps through the migration state for a
one-shot copy is more fragile than reading the tables directly.
"""

from django.db import migrations

SOURCES = [
    ("admin_tokens", "admin"),
    ("launcher_tokens", "launcher"),
    ("ws_tokens", "ws"),
]

# admin_tokens and launcher_tokens allow a NULL expires_at; auth_tokens does
# not. Those rows had no meaningful expiry, so give them the scope default
# measured from creation.
DEFAULT_EXPIRY_SQL = {
    "admin": "datetime(created_at, '+1 day')",
    "launcher": "datetime(created_at, '+30 day')",
    "ws": "datetime(created_at, '+10 minute')",
}

POSTGRES_EXPIRY_SQL = {
    "admin": "created_at + interval '1 day'",
    "launcher": "created_at + interval '30 day'",
    "ws": "created_at + interval '10 minute'",
}


def table_exists(schema_editor, name):
    return name in schema_editor.connection.introspection.table_names()


def forwards(apps, schema_editor):
    connection = schema_editor.connection
    is_postgres = connection.vendor == "postgresql"
    expiry = POSTGRES_EXPIRY_SQL if is_postgres else DEFAULT_EXPIRY_SQL

    with connection.cursor() as cursor:
        for table, scope in SOURCES:
            if not table_exists(schema_editor, table):
                continue
            cursor.execute(
                f"""
                INSERT INTO auth_tokens (key, user_id, scope, created_at, expires_at, last_used_at)
                SELECT key, user_id, %s, created_at,
                       COALESCE(expires_at, {expiry[scope]}), NULL
                FROM {table}
                WHERE key NOT IN (SELECT key FROM auth_tokens)
                """,
                [scope],
            )


def backwards(apps, schema_editor):
    """Drop the copied rows. The legacy tables are untouched by forwards()."""
    AuthToken = apps.get_model("accounts", "AuthToken")
    AuthToken.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_authtoken"),
        ("launcher", "0003_wstoken"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
