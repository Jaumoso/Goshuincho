from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations

NAME_EXPR = "(coalesce(name_ja,'') || ' ' || coalesce(name_romaji,'') || ' ' || coalesce(name_en,''))"


class Migration(migrations.Migration):
    dependencies = [("places", "0001_initial")]

    operations = [
        TrigramExtension(),
        migrations.RunSQL(
            f"CREATE INDEX places_name_trgm ON places USING gin ({NAME_EXPR} gin_trgm_ops);",
            "DROP INDEX places_name_trgm;",
        ),
    ]
