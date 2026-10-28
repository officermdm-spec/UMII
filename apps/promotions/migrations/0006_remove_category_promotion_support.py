from django.db import migrations, models


def disable_category_promotions(apps, schema_editor):
    Promotion = apps.get_model("promotions", "Promotion")
    database = schema_editor.connection.alias
    Promotion.objects.using(database).filter(apply_to="category").update(
        apply_to="all", is_active=False
    )


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0005_rename_promotions__is_acti_offer_idx_promotions__is_acti_77bda6_idx"),
    ]

    operations = [
        migrations.RunPython(disable_category_promotions, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="promotion",
            name="categories",
        ),
        migrations.AlterField(
            model_name="promotion",
            name="apply_to",
            field=models.CharField(
                choices=[("all", "Entire Order"), ("product", "Specific Products")],
                default="all",
                max_length=20,
            ),
        ),
    ]
