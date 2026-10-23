from django.db import migrations


def restrict_coupons_with_products(apps, schema_editor):
    Promotion = apps.get_model("promotions", "Promotion")
    for promo in Promotion.objects.all():
        if promo.products.exists() and promo.apply_to == "all":
            promo.apply_to = "product"
            promo.save(update_fields=["apply_to"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("promotions", "0002_promotion_description"),
    ]

    operations = [
        migrations.RunPython(restrict_coupons_with_products, noop),
    ]
