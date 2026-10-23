from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0004_order_catalog_discount_order_cogs_total_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="unit_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Average cost snapshot at sale time.",
                max_digits=12,
            ),
        ),
    ]
