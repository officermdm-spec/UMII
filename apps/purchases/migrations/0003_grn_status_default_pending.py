from django.db import migrations, models


def drafts_to_pending(apps, schema_editor):
    GRN = apps.get_model("purchases", "GRN")
    GRN.objects.filter(status="draft").update(status="pending")


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0002_remove_grnitem_mrp"),
    ]

    operations = [
        migrations.RunPython(drafts_to_pending, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="grn",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("pending", "Pending"),
                    ("approved", "Approved"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
