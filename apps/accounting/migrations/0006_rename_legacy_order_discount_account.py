from django.db import migrations


def rename_legacy_discount_account(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    Account.objects.using(schema_editor.connection.alias).filter(code="4120").update(
        name="Historical Order Discounts"
    )


def restore_legacy_discount_account_name(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    Account.objects.using(schema_editor.connection.alias).filter(code="4120").update(
        name="Coupon Discounts"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0005_remove_other_income"),
    ]

    operations = [
        migrations.RunPython(
            rename_legacy_discount_account,
            restore_legacy_discount_account_name,
        ),
    ]
