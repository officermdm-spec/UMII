from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0003_grn_status_default_pending"),
    ]

    operations = [
        migrations.AddField(
            model_name="grnitem",
            name="average_cost_after",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Product weighted-average cost after this line was approved.",
                max_digits=12,
            ),
        ),
    ]
