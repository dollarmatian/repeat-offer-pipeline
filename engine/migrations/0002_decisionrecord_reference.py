"""Add an opaque public reference. Existing rows are backfilled from their id, which was the
public reference until now, and both forms resolve. See docs/preserving-references.md.
"""

from django.db import migrations, models


def backfill(apps, schema_editor):
    DecisionRecord = apps.get_model("engine", "DecisionRecord")
    for record in DecisionRecord.objects.filter(reference__isnull=True).only("id"):
        record.reference = f"dec_legacy_{record.id}"
        record.save(update_fields=["reference"])


class Migration(migrations.Migration):
    dependencies = [
        ("engine", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="decisionrecord",
            name="reference",
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="decisionrecord",
            name="reference",
            field=models.CharField(max_length=32, unique=True),
        ),
    ]
