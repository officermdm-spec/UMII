from django.db import migrations


def prune_empty_inventory(apps, schema_editor):
    Inventory = apps.get_model("inventory", "Inventory")
    StockTransaction = apps.get_model("inventory", "StockTransaction")
    empty = Inventory.objects.filter(
        current_stock=0,
        reserved_stock=0,
        incoming_stock=0,
        sold_quantity=0,
        returned_quantity=0,
        damaged_quantity=0,
    )
    for inv in empty.iterator():
        if not StockTransaction.objects.filter(
            product_id=inv.product_id, warehouse_id=inv.warehouse_id
        ).exists():
            inv.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0002_inventorycostlayer_costlayerconsumption_and_more"),
    ]

    operations = [
        migrations.RunPython(prune_empty_inventory, migrations.RunPython.noop),
    ]
